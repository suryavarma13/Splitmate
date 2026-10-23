
"""MongoDB repository for SplitMate Groups."""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import ASCENDING, ReturnDocument

from apps.authentication.repositories import users

logger = logging.getLogger(__name__)

INVITATION_EXPIRY_DAYS = 7


# ---------------------------------------------------------
# DATABASE COLLECTIONS
# ---------------------------------------------------------

def _db():
    """Use the same MongoDB database as authentication."""
    return users().database


def groups_collection():
    return _db()["groups"]


def invitations_collection():
    return _db()["group_invitations"]


def notifications_collection():
    return _db()["notifications"]


def _now():
    return datetime.now(timezone.utc)


def _id(value):
    """Convert a valid MongoDB ID string to ObjectId."""
    if isinstance(value, ObjectId):
        return value

    if not isinstance(value, str) or not ObjectId.is_valid(value):
        return None

    return ObjectId(value)


def _public_group(group):
    if not group:
        return None

    result = dict(group)
    result["id"] = str(result.pop("_id"))
    result["created_by"] = str(result["created_by"])

    for member in result.get("members", []):
        member["user_id"] = str(member["user_id"])

    result["created_at"] = result["created_at"].isoformat()
    result["updated_at"] = result["updated_at"].isoformat()

    return result


def _public_invitation(invitation):
    if not invitation:
        return None

    result = dict(invitation)
    result["id"] = str(result.pop("_id"))
    result["group_id"] = str(result["group_id"])
    result["invited_by"] = str(result["invited_by"])

    for field in ("expires_at", "created_at", "updated_at"):
        if result.get(field):
            result[field] = result[field].isoformat()

    # Never return the secret token in ordinary invitation listings.
    result.pop("token", None)

    return result


def _find_group(group_id):
    group_object_id = _id(group_id)

    if not group_object_id:
        return None

    return groups_collection().find_one({"_id": group_object_id})


def _find_member(group, user_id):
    user_object_id = _id(user_id)

    if not group or not user_object_id:
        return None

    return next(
        (
            member
            for member in group.get("members", [])
            if member["user_id"] == user_object_id
        ),
        None,
    )


def _is_admin(group, user_id):
    member = _find_member(group, user_id)

    return bool(member and member.get("role") == "admin")


def _friendship_exists(first_user_id, second_user_id):
    """Check an accepted friendship in the Friends module collection."""
    first_id = _id(first_user_id)
    second_id = _id(second_user_id)

    if not first_id or not second_id or first_id == second_id:
        return False

    ids = sorted([str(first_id), str(second_id)])

    return _db()["friendships"].find_one(
        {"user_ids": ids}
    ) is not None


# ---------------------------------------------------------
# INDEXES
# ---------------------------------------------------------

def ensure_indexes():
    """Call once during application startup or a management command."""
    groups = groups_collection()
    invitations = invitations_collection()

    groups.create_index(
        [("members.user_id", ASCENDING)],
        name="group_members_lookup",
    )
    groups.create_index(
        [("created_by", ASCENDING), ("created_at", ASCENDING)],
        name="group_creator_lookup",
    )
    invitations.create_index(
        [("token", ASCENDING)],
        unique=True,
        name="invitation_token_unique",
    )
    invitations.create_index(
        [
            ("group_id", ASCENDING),
            ("email", ASCENDING),
            ("status", ASCENDING),
        ],
        name="invitation_lookup",
    )
    invitations.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="invitation_expiry_ttl",
    )


# ---------------------------------------------------------
# CREATE AND LIST GROUPS
# ---------------------------------------------------------

def create_group(creator_id, name, description="", image_url=None):
    creator_object_id = _id(creator_id)

    if not creator_object_id:
        return None, "Invalid user ID.", 400

    name = (name or "").strip()
    description = (description or "").strip()

    if not name:
        return None, "Group name is required.", 400

    if len(name) > 100:
        return None, "Group name cannot exceed 100 characters.", 400

    if len(description) > 1000:
        return None, "Description cannot exceed 1000 characters.", 400

    if not users().find_one({"_id": creator_object_id}):
        return None, "Creator account was not found.", 404

    now = _now()

    document = {
        "name": name,
        "description": description,
        "image_url": image_url,
        "created_by": creator_object_id,
        "members": [
            {
                "user_id": creator_object_id,
                "role": "admin",
                "joined_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
        "is_active": True,
    }

    result = groups_collection().insert_one(document)
    document["_id"] = result.inserted_id

    logger.info("Group created: group_id=%s", result.inserted_id)

    return _public_group(document), None, 201


def list_user_groups(user_id):
    user_object_id = _id(user_id)

    if not user_object_id:
        return []

    documents = groups_collection().find(
        {
            "members.user_id": user_object_id,
            "is_active": True,
        }
    ).sort("updated_at", -1)

    return [_public_group(group) for group in documents]


def get_group_details(group_id, user_id):
    group = _find_group(group_id)

    if not group or not _find_member(group, user_id):
        return None, "Group not found.", 404

    return _public_group(group), None, 200


# ---------------------------------------------------------
# UPDATE GROUP
# ---------------------------------------------------------

def update_group(
    group_id,
    user_id,
    name=None,
    description=None,
    image_url=None,
):
    group = _find_group(group_id)

    if not group or not group.get("is_active", True):
        return None, "Group not found.", 404

    if not _is_admin(group, user_id):
        return None, "Only group admins can edit this group.", 403

    updates = {}

    if name is not None:
        name = name.strip()

        if not name:
            return None, "Group name is required.", 400

        if len(name) > 100:
            return None, "Group name cannot exceed 100 characters.", 400

        updates["name"] = name

    if description is not None:
        description = description.strip()

        if len(description) > 1000:
            return None, "Description cannot exceed 1000 characters.", 400

        updates["description"] = description

    if image_url is not None:
        updates["image_url"] = image_url

    if not updates:
        return _public_group(group), None, 200

    updates["updated_at"] = _now()

    updated = groups_collection().find_one_and_update(
        {
            "_id": group["_id"],
            "members": {
                "$elemMatch": {
                    "user_id": _id(user_id),
                    "role": "admin",
                }
            },
        },
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        return None, "Group update failed.", 409

    logger.info("Group updated: group_id=%s", group_id)

    return _public_group(updated), None, 200


# ---------------------------------------------------------
# ADD AND REMOVE MEMBERS
# ---------------------------------------------------------

def add_group_members(group_id, admin_id, member_ids):
    group = _find_group(group_id)

    if not group or not group.get("is_active", True):
        return None, "Group not found.", 404

    if not _is_admin(group, admin_id):
        return None, "Only group admins can add members.", 403

    if not isinstance(member_ids, list) or not member_ids:
        return None, "Provide at least one member ID.", 400

    converted_ids = []

    for member_id in member_ids:
        converted = _id(member_id)

        if not converted:
            return None, "One or more member IDs are invalid.", 400

        if converted not in converted_ids:
            converted_ids.append(converted)

    admin_object_id = _id(admin_id)

    if admin_object_id in converted_ids:
        return None, "You are already a member of this group.", 400

    existing_ids = {
        member["user_id"]
        for member in group.get("members", [])
    }

    additions = []

    for member_object_id in converted_ids:
        if member_object_id in existing_ids:
            continue

        if not users().find_one({"_id": member_object_id}):
            return None, "A selected user was not found.", 404

        if not _friendship_exists(admin_object_id, member_object_id):
            return None, "You can only add accepted friends.", 403

        additions.append({
            "user_id": member_object_id,
            "role": "member",
            "joined_at": _now(),
        })

    if additions:
        updated = groups_collection().update_one(
            {
                "_id": group["_id"],
                "members.user_id": {"$ne": additions[0]["user_id"]},
            },
            {
                "$push": {"members": {"$each": additions}},
                "$set": {"updated_at": _now()},
            },
        )

        # The conditional above protects against the first member being
        # added concurrently. Always reread to return the actual group.
        if not updated.modified_count:
            refreshed = _find_group(group_id)

            if refreshed and all(
                _find_member(refreshed, item["user_id"])
                for item in additions
            ):
                return _public_group(refreshed), None, 200

            return None, "Group membership changed. Please retry.", 409

    refreshed = _find_group(group_id)

    logger.info("Group members processed: group_id=%s", group_id)

    return _public_group(refreshed), None, 200


def remove_group_member(group_id, admin_id, member_id):
    group = _find_group(group_id)

    if not group or not group.get("is_active", True):
        return False, "Group not found.", 404

    if not _is_admin(group, admin_id):
        return False, "Only group admins can remove members.", 403

    member_object_id = _id(member_id)

    if not member_object_id:
        return False, "Invalid member ID.", 400

    if member_object_id == group["created_by"]:
        return False, "The group creator cannot be removed.", 400

    if not _find_member(group, member_object_id):
        return False, "Group member not found.", 404

    groups_collection().update_one(
        {"_id": group["_id"]},
        {
            "$pull": {"members": {"user_id": member_object_id}},
            "$set": {"updated_at": _now()},
        },
    )

    logger.info("Group member removed: group_id=%s", group_id)

    return True, None, 200


# ---------------------------------------------------------
# CREATE AND LIST EMAIL INVITATIONS
# ---------------------------------------------------------

def create_invitation(group_id, inviter_id, email):
    group = _find_group(group_id)

    if not group or not group.get("is_active", True):
        return None, "Group not found.", 404

    if not _is_admin(group, inviter_id):
        return None, "Only group admins can invite members.", 403

    email = (email or "").strip().lower()

    if not email or "@" not in email:
        return None, "Enter a valid email address.", 400

    inviter_object_id = _id(inviter_id)

    # Do not create an invitation for someone already in the group.
    invitee = users().find_one({"email": email})

    if invitee and _find_member(group, invitee["_id"]):
        return None, "This user is already a group member.", 409

    pending = invitations_collection().find_one({
        "group_id": group["_id"],
        "email": email,
        "status": "pending",
        "expires_at": {"$gt": _now()},
    })

    if pending:
        return None, "A pending invitation already exists for this email.", 409

    now = _now()

    document = {
        "group_id": group["_id"],
        "group_name": group["name"],
        "email": email,
        "invited_by": inviter_object_id,
        "token": secrets.token_urlsafe(32),
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=INVITATION_EXPIRY_DAYS),
        "accepted_at": None,
    }

    result = invitations_collection().insert_one(document)
    document["_id"] = result.inserted_id

    logger.info("Group invitation created: invitation_id=%s", result.inserted_id)

    # Email delivery is deliberately handled by the service layer.
    return {
        **_public_invitation(document),
        "token": document["token"],
    }, None, 201


def list_invitations(user_email):
    email = (user_email or "").strip().lower()

    documents = invitations_collection().find({
        "email": email,
        "status": "pending",
        "expires_at": {"$gt": _now()},
    }).sort("created_at", -1)

    return [_public_invitation(item) for item in documents]


# ---------------------------------------------------------
# ACCEPT, DECLINE, RESEND, CANCEL INVITATIONS
# ---------------------------------------------------------

def accept_invitation(token, user_id, user_email):
    invitation = invitations_collection().find_one({
        "token": token,
        "status": "pending",
        "expires_at": {"$gt": _now()},
    })

    if not invitation:
        return None, "Invitation is invalid, expired, or already used.", 404

    if invitation["email"].lower() != (user_email or "").strip().lower():
        return None, "This invitation belongs to a different email address.", 403

    user_object_id = _id(user_id)

    if not user_object_id:
        return None, "Invalid user ID.", 400

    if not users().find_one({"_id": user_object_id}):
        return None, "User account not found.", 404

    # Atomically claim the invitation so it cannot be accepted twice.
    claimed = invitations_collection().find_one_and_update(
        {
            "_id": invitation["_id"],
            "status": "pending",
            "expires_at": {"$gt": _now()},
        },
        {
            "$set": {
                "status": "accepted",
                "accepted_at": _now(),
                "updated_at": _now(),
                "accepted_by": user_object_id,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not claimed:
        return None, "Invitation has already been processed.", 409

    group = _find_group(invitation["group_id"])

    if not group or not group.get("is_active", True):
        invitations_collection().update_one(
            {"_id": invitation["_id"]},
            {"$set": {"status": "pending"}},
        )
        return None, "Group not found.", 404

    if not _find_member(group, user_object_id):
        groups_collection().update_one(
            {
                "_id": group["_id"],
                "members.user_id": {"$ne": user_object_id},
            },
            {
                "$push": {
                    "members": {
                        "user_id": user_object_id,
                        "role": "member",
                        "joined_at": _now(),
                    }
                },
                "$set": {"updated_at": _now()},
            },
        )

    logger.info("Group invitation accepted: group_id=%s", group["_id"])

    return _public_group(_find_group(group["_id"])), None, 200


def update_invitation(invitation_id, user_email, action):
    invitation_object_id = _id(invitation_id)

    if not invitation_object_id:
        return None, "Invalid invitation ID.", 400

    invitation = invitations_collection().find_one({
        "_id": invitation_object_id,
        "email": (user_email or "").strip().lower(),
    })

    if not invitation:
        return None, "Invitation not found.", 404

    if invitation["status"] != "pending":
        return None, "Invitation is no longer pending.", 409

    if action not in ("declined", "cancelled"):
        return None, "Invalid invitation action.", 400

    updated = invitations_collection().find_one_and_update(
        {
            "_id": invitation_object_id,
            "status": "pending",
        },
        {
            "$set": {
                "status": action,
                "updated_at": _now(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        return None, "Invitation has already been processed.", 409

    return _public_invitation(updated), None, 200


def resend_invitation(invitation_id, inviter_id):
    """Generate a fresh link for an invitation that has not been accepted."""

    invitation_object_id = _id(invitation_id)
    inviter_object_id = _id(inviter_id)

    if not invitation_object_id or not inviter_object_id:
        return None, "Invalid invitation or user ID.", 400

    invitation = invitations_collection().find_one({
        "_id": invitation_object_id,
    })

    if not invitation:
        return None, "Invitation not found.", 404

    if invitation.get("status") != "pending":
        return None, "Only pending invitations can be resent.", 409

    group = _find_group(invitation["group_id"])

    if not group or not group.get("is_active", True):
        return None, "Group not found or inactive.", 404

    if not _is_admin(group, inviter_object_id):
        return None, "Only group admins can resend invitations.", 403

    now = _now()
    new_token = secrets.token_urlsafe(32)

    updated = invitations_collection().find_one_and_update(
        {
            "_id": invitation_object_id,
            "status": "pending",
        },
        {
            "$set": {
                "token": new_token,
                "expires_at": now + timedelta(
                    days=INVITATION_EXPIRY_DAYS
                ),
                "updated_at": now,
                "last_sent_at": now,
            },
            "$inc": {"resend_count": 1},
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        return None, "Invitation was already processed.", 409

    logger.info(
        "Group invitation link renewed: invitation_id=%s",
        invitation_object_id,
    )

    result = _public_invitation(updated)
    result["token"] = new_token

    return result, None, 200
