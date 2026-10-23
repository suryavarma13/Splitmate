"""MongoDB persistence functions using PyMongo."""

"""
SplitMate expense repository.

Responsibilities:
- Save expenses in MongoDB.
- Retrieve expenses by ID.
- List expenses for a group.
- Update expenses created by the requesting user.
- Soft-delete expenses created by the requesting user.

This file uses PyMongo, not Django ORM.
"""

from datetime import datetime, timezone
from pymongo import DESCENDING, ReturnDocument
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING


class ExpenseRepository:
    """Database operations for SplitMate expenses."""

    EDITABLE_FIELDS = {
        "title",
        "notes",
        "category",
        "expense_date",
    }

    def __init__(self, expenses_collection):
        # Pass your existing MongoDB expenses collection here.
        self.collection = expenses_collection

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    @staticmethod
    def _valid_object_id(expense_id):
        """Convert a valid MongoDB ID to ObjectId."""
        try:
            return ObjectId(str(expense_id))
        except (InvalidId, TypeError, ValueError):
            return None

    @staticmethod
    def _serialize(document):
        """Convert MongoDB-specific values for JSON/API responses."""
        if not document:
            return None

        document["id"] = str(document.pop("_id"))

        for field in ("created_at", "updated_at", "deleted_at"):
            value = document.get(field)
            if isinstance(value, datetime):
                document[field] = value.isoformat()

        return document

    @staticmethod
    def _build_shares(validated_data):
        """Use the shares calculated by ExpenseCreateSerializer."""
        shares = validated_data.get("calculated_shares", [])

        return [
            {
                "user_id": str(share["user_id"]),
                "amount_minor": int(share["amount_minor"]),
            }
            for share in shares
        ]

    def create(self, validated_data, created_by):
        """Create an expense document in MongoDB."""
        participant_ids = [
            str(user_id)
            for user_id in validated_data["participant_ids"]
        ]

        payer_id = str(validated_data["paid_by_user_id"])
        total_minor = int(validated_data["total_amount_minor"])
        shares = self._build_shares(validated_data)

        # Final consistency checks before writing to the database.
        share_ids = [share["user_id"] for share in shares]

        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("Duplicate participants are not allowed.")

        if payer_id not in participant_ids:
            raise ValueError("The payer must be a participant.")

        if set(share_ids) != set(participant_ids):
            raise ValueError("Shares must match selected participants.")

        if sum(share["amount_minor"] for share in shares) != total_minor:
            raise ValueError("Participant shares must equal the total.")

        now = self._now()

        document = {
            "group_id": str(validated_data["group_id"]),
            "title": validated_data["title"],
            "total_amount_minor": total_minor,
            "currency": validated_data.get("currency", "INR"),
            "paid_by_user_id": payer_id,
            "participant_ids": participant_ids,
            "split_method": validated_data["split_method"],
            "shares": shares,
            "category": validated_data.get("category", "Other"),
            "expense_date": validated_data["expense_date"].isoformat(),
            "notes": validated_data.get("notes", ""),
            "receipt_url": validated_data.get("receipt_url", ""),
            "created_by": str(created_by),
            "created_at": now,
            "updated_at": now,
            "is_deleted": False,
            "deleted_at": None,
        }

        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id

        return self._serialize(document)

    def get_by_id(self, expense_id):
        """Get one active expense by its MongoDB ID."""
        object_id = self._valid_object_id(expense_id)

        if object_id is None:
            return None

        document = self.collection.find_one({
            "_id": object_id,
            "is_deleted": False,
        })

        return self._serialize(document)

    def list_by_group(self, group_id, limit=50, skip=0):
        """Return active expenses for a group, newest first."""
        limit = max(1, min(int(limit), 100))
        skip = max(0, int(skip))

        cursor = (
            self.collection.find({
                "group_id": str(group_id),
                "is_deleted": False,
            })
            .sort([
                ("expense_date", DESCENDING),
                ("created_at", DESCENDING),
            ])
            .skip(skip)
            .limit(limit)
        )

        return [
            self._serialize(document)
            for document in cursor
        ]

    
    def update_by_creator(self, expense_id, user_id, updates):
        """
        Update an expense only if the logged-in user created it.
        Return the updated document or None if not found or unauthorized.
        """
        object_id = self._valid_object_id(expense_id)

        if object_id is None:
            return None

        safe_updates = {
            key: value
            for key, value in updates.items()
            if key in self.EDITABLE_FIELDS
        }

        if not safe_updates:
            raise ValueError("No permitted fields were provided.")

        # Convert date values into ISO strings for MongoDB.
        if "expense_date" in safe_updates:
            date_value = safe_updates["expense_date"]
            safe_updates["expense_date"] = (
                date_value.isoformat()
                if hasattr(date_value, "isoformat")
                else str(date_value)
            )

        safe_updates["updated_at"] = self._now()

        document = self.collection.find_one_and_update(
            {
                "_id": object_id,
                "created_by": str(user_id),
                "is_deleted": False,
            },
            {"$set": safe_updates},
            return_document=ReturnDocument.AFTER,
        )

        return self._serialize(document)


    def soft_delete_by_creator(self, expense_id, user_id):
        """
        Mark an expense deleted without permanently removing it.
        Only its creator can delete it.

        Returns True if deleted; otherwise False.
        """
        object_id = self._valid_object_id(expense_id)

        if object_id is None:
            return False

        now = self._now()

        result = self.collection.update_one(
            {
                "_id": object_id,
                "created_by": str(user_id),
                "is_deleted": False,
            },
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now,
                    "updated_at": now,
                }
            },
        )

        return result.modified_count == 1
