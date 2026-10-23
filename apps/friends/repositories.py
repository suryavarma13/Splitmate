
"""MongoDB persistence functions for the SplitMate Friends module."""

import logging
import re
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ASCENDING, ReturnDocument

from apps.authentication.repositories import users

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# MongoDB collections
# ---------------------------------------------------------

def _db():
    """Use the same MongoDB database as Authentication."""
    return users().database


def requests_collection():
    return _db()["friend_requests"]


def friendships_collection():
    return _db()["friendships"]


def notifications_collection():
    return _db()["notifications"]


# ---------------------------------------------------------
# Common helpers
# ---------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _object_id(value):
    """Convert a valid ID to ObjectId; return None for invalid IDs."""
    try:
        return ObjectId(str(value))
    except (TypeError, ValueError):
        return None


def user_id_string(user_id):
    return str(user_id)


def get_user(user_id):
    """Find a registered user by MongoDB ObjectId."""
    oid = _object_id(user_id)
    if oid is None:
        return None

    return users().find_one({"_id": oid})


def _public_user(user):
    """Return only safe public user fields."""
    if not user:
        return None

    return {
        "id": str(user["_id"]),
        "full_name": user.get("full_name", ""),
        "email": user.get("email", ""),
    }


def _notify(user_id, notification_type, message, request_id):
    """Store a notification without exposing notification internals."""
    try:
        notifications_collection().insert_one({
            "user_id": str(user_id),
            "type": notification_type,
            "message": message,
            "friend_request_id": str(request_id),
            "is_read": False,
            "created_at": _now(),
        })
    except Exception:
        # Notification failure should not hide a completed request action.
        logger.exception(
            "Failed to create notification for user_id=%s",
            user_id,
        )


def _friendship_filter(user_a, user_b):
    """Friendship IDs are stored as a consistently sorted pair."""
    first, second = sorted([str(user_a), str(user_b)])
    return {"user_ids": [first, second]}


def _has_accepted_friendship(user_a, user_b):
    return friendships_collection().find_one(
        _friendship_filter(user_a, user_b)
    ) is not None


# ---------------------------------------------------------
# Search registered users
# ---------------------------------------------------------

def search_users(query, current_user_id, limit=20):
    query = (query or "").strip()

    current_oid = _object_id(current_user_id)
    if not query or current_oid is None:
        return []

    pattern = re.escape(query)

    cursor = users().find(
        {
            "_id": {"$ne": current_oid},
            "is_active": {"$ne": False},
            "$or": [
                {
                    "full_name": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
                {
                    "email": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
            ],
        },
        {
            "_id": 1,
            "full_name": 1,
            "email": 1,
        },
    ).limit(max(1, min(int(limit), 50)))

    return [_public_user(user) for user in cursor]


# ---------------------------------------------------------
# Send friend request
# ---------------------------------------------------------

def create_friend_request(sender_id, recipient_id):
    sender_oid = _object_id(sender_id)
    recipient_oid = _object_id(recipient_id)

    if sender_oid is None or recipient_oid is None:
        return None, "Invalid sender or recipient ID."

    if sender_oid == recipient_oid:
        return None, "You cannot send a friend request to yourself."

    sender = get_user(sender_oid)
    recipient = get_user(recipient_oid)

    if not sender or not sender.get("is_active", True):
        return None, "Sender account not found or inactive."

    if not recipient or not recipient.get("is_active", True):
        return None, "Recipient account not found or inactive."

    sender_key = str(sender_oid)
    recipient_key = str(recipient_oid)

    if _has_accepted_friendship(sender_key, recipient_key):
        return None, "You are already friends."

    collection = requests_collection()

    # Check both directions to prevent duplicate pending requests.
    existing = list(collection.find({
        "$or": [
            {
                "sender_id": sender_key,
                "recipient_id": recipient_key,
            },
            {
                "sender_id": recipient_key,
                "recipient_id": sender_key,
            },
        ]
    }).sort("created_at", -1))

    for request in existing:
        if request.get("status") == "accepted":
            return None, "You are already friends."

        if (
            request.get("sender_id") == recipient_key
            and request.get("recipient_id") == sender_key
            and request.get("status") == "pending"
        ):
            return None, "This user has already sent you a request."

        if (
            request.get("sender_id") == sender_key
            and request.get("recipient_id") == recipient_key
            and request.get("status") == "pending"
        ):
            return None, "A pending request already exists."

    now = _now()

    # Reuse a previous request in the same direction when possible.
    previous = next(
        (
            item for item in existing
            if item.get("sender_id") == sender_key
            and item.get("recipient_id") == recipient_key
            and item.get("status") in {
                "rejected", "cancelled", "removed"
            }
        ),
        None,
    )

    if previous:
        # Conditional update avoids overwriting a concurrently processed
        # request that is no longer in the previous status.
        old_status = previous["status"]
        document = collection.find_one_and_update(
            {
                "_id": previous["_id"],
                "status": old_status,
            },
            {
                "$set": {
                    "status": "pending",
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        if not document:
            return None, "Request changed concurrently. Please try again."
    else:
        document = {
            "sender_id": sender_key,
            "recipient_id": recipient_key,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = collection.insert_one(document)
            document["_id"] = result.inserted_id
        except Exception:
            logger.exception("Failed to create friend request")
            return None, "Unable to create friend request."

    _notify(
        recipient_key,
        "friend_request_received",
        "You received a friend request.",
        document["_id"],
    )

    return document, None


# ---------------------------------------------------------
# List received or sent pending requests
# ---------------------------------------------------------

def list_requests(user_id, direction):
    if direction not in ("received", "sent"):
        return []

    uid = str(user_id)
    field = "recipient_id" if direction == "received" else "sender_id"
    other_field = "sender_id" if direction == "received" else "recipient_id"

    cursor = requests_collection().find({
        field: uid,
        "status": "pending",
    }).sort("created_at", -1)

    results = []

    for document in cursor:
        other = get_user(document.get(other_field))

        item = dict(document)
        item["id"] = str(item.pop("_id"))
        item["user"] = _public_user(other)
        results.append(item)

    return results


# ---------------------------------------------------------
# Accept, reject, or cancel a request
# ---------------------------------------------------------

def update_request(request_id, user_id, action_name):
    oid = _object_id(request_id)
    uid = str(user_id)

    if oid is None:
        return None, "Invalid request ID.", 400

    actions = {
        "accept": ("accepted", "recipient_id"),
        "reject": ("rejected", "recipient_id"),
        "cancel": ("cancelled", "sender_id"),
    }

    if action_name not in actions:
        return None, "Invalid action.", 400

    new_status, authorized_field = actions[action_name]
    collection = requests_collection()

    document = collection.find_one({"_id": oid})

    if not document:
        return None, "Friend request not found.", 404

    if document.get("status") != "pending":
        return None, "This request is no longer pending.", 409

    if document.get(authorized_field) != uid:
        return None, "You are not allowed to perform this action.", 403

    now = _now()

    updated = collection.find_one_and_update(
        {
            "_id": oid,
            "status": "pending",
            authorized_field: uid,
        },
        {
            "$set": {
                "status": new_status,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        return None, "Request was already processed. Please refresh.", 409

    if action_name == "accept":
        sender_id = document["sender_id"]
        recipient_id = document["recipient_id"]

        try:
            friendships_collection().update_one(
                _friendship_filter(sender_id, recipient_id),
                {
                    "$setOnInsert": {
                        "user_ids": sorted([sender_id, recipient_id]),
                        "created_at": now,
                    }
                },
                upsert=True,
            )
        except Exception:
            # Restore pending status if creating the friendship fails.
            collection.update_one(
                {
                    "_id": oid,
                    "status": "accepted",
                },
                {
                    "$set": {
                        "status": "pending",
                        "updated_at": _now(),
                    }
                },
            )
            logger.exception("Failed to create friendship")
            return None, "Unable to accept request. Please retry.", 500

        _notify(
            sender_id,
            "friend_request_accepted",
            "Your friend request was accepted.",
            oid,
        )

    return {
        "id": str(updated["_id"]),
        "sender_id": updated["sender_id"],
        "recipient_id": updated["recipient_id"],
        "status": updated["status"],
    }, None, 200


# ---------------------------------------------------------
# List accepted friends
# ---------------------------------------------------------

def list_friends(user_id):
    uid = str(user_id)
    cursor = friendships_collection().find({"user_ids": uid})

    results = []

    for friendship in cursor:
        other_ids = [
            value
            for value in friendship.get("user_ids", [])
            if value != uid
        ]

        if not other_ids:
            continue

        other = get_user(other_ids[0])

        if other and other.get("is_active", True):
            results.append(_public_user(other))

    return results


# ---------------------------------------------------------
# Remove accepted friendship
# ---------------------------------------------------------

def remove_friend(user_id, other_id):
    current_oid = _object_id(user_id)
    other_oid = _object_id(other_id)

    if current_oid is None or other_oid is None:
        return False

    if current_oid == other_oid:
        return False

    current_key = str(current_oid)
    other_key = str(other_oid)

    result = friendships_collection().delete_one(
        _friendship_filter(current_key, other_key)
    )

    if result.deleted_count == 0:
        return False

    # Retain historical request records; only mark the accepted request
    # as removed so the users can send a new request later.
    requests_collection().update_many(
        {
            "$or": [
                {
                    "sender_id": current_key,
                    "recipient_id": other_key,
                },
                {
                    "sender_id": other_key,
                    "recipient_id": current_key,
                },
            ],
            "status": "accepted",
        },
        {
            "$set": {
                "status": "removed",
                "updated_at": _now(),
            }
        },
    )

    logger.info("Friendship removed between %s and %s", current_key, other_key)
    return True


# ---------------------------------------------------------
# Optional MongoDB indexes
# ---------------------------------------------------------

def ensure_indexes():
    """
    Call once during controlled application startup or a deployment
    migration—not on every API request.
    """
    requests = requests_collection()
    friendships = friendships_collection()
    notifications = notifications_collection()

    requests.create_index([
        ("sender_id", ASCENDING),
        ("recipient_id", ASCENDING),
        ("status", ASCENDING),
    ])

    requests.create_index([
        ("recipient_id", ASCENDING),
        ("status", ASCENDING),
        ("created_at", ASCENDING),
    ])

    requests.create_index([
        ("sender_id", ASCENDING),
        ("status", ASCENDING),
        ("created_at", ASCENDING),
    ])

    friendships.create_index(
        [("user_ids", ASCENDING)],
        unique=True,
    )

    notifications.create_index([
        ("user_id", ASCENDING),
        ("is_read", ASCENDING),
        ("created_at", ASCENDING),
    ])
