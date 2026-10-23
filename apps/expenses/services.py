"""Business logic and orchestration."""

"""
SplitMate expense business logic.

Responsibilities:
- Check group membership.
- Validate expense participants.
- Coordinate serializers and repositories.
- Restrict editing and deletion to the expense creator.
"""

from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)

from .repositories import ExpenseRepository


class ExpenseService:
    """Business logic for SplitMate expenses."""

    def __init__(self, repository, is_group_member):
        """
        repository:
            An ExpenseRepository instance.

        is_group_member:
            A callable with this signature:
            is_group_member(group_id, user_id) -> bool

            It must use your existing MongoDB group structure.
        """
        self.repository = repository
        self.is_group_member = is_group_member

    @staticmethod
    def _user_id(user):
        """Get the authenticated user's ID."""
        if isinstance(user, dict):
            user_id = user.get("_id") or user.get("id")
        else:
            user_id = getattr(user, "id", None)

            if user_id is None:
                user_id = getattr(user, "_id", None)

        if user_id is None:
            raise PermissionDenied("Authenticated user ID is missing.")

        return str(user_id)

    def _require_group_member(self, group_id, user_id):
        """Reject users who are not members of the group."""
        if not self.is_group_member(str(group_id), str(user_id)):
            raise PermissionDenied(
                "You must be a member of this group."
            )

    def create_expense(self, validated_data, user):
        """Create an expense after validating group membership."""
        creator_id = self._user_id(user)
        group_id = str(validated_data["group_id"])

        self._require_group_member(group_id, creator_id)

        # The payer must belong to the group.
        payer_id = str(validated_data["paid_by_user_id"])
        self._require_group_member(group_id, payer_id)

        # Only selected participants are charged for this expense.
        participant_ids = validated_data["participant_ids"]

        for participant_id in participant_ids:
            self._require_group_member(group_id, participant_id)

        # The repository stores the expense and calculated shares.
        try:
            return self.repository.create(
                validated_data=validated_data,
                created_by=creator_id,
            )
        except ValueError as exc:
            raise ValidationError({"expense": str(exc)})

    def get_expense(self, expense_id, user):
        """Return an expense only to a member of its group."""
        user_id = self._user_id(user)

        expense = self.repository.get_by_id(expense_id)

        if expense is None:
            raise NotFound("Expense not found.")

        self._require_group_member(expense["group_id"], user_id)

        return expense

    def list_group_expenses(self, group_id, user, limit=50, skip=0):
        """List expenses after checking group membership."""
        user_id = self._user_id(user)

        self._require_group_member(group_id, user_id)

        return self.repository.list_by_group(
            group_id=group_id,
            limit=limit,
            skip=skip,
        )

    def update_expense(self, expense_id, updates, user):
        """Update permitted fields only for the expense creator."""
        user_id = self._user_id(user)

        # First ensure the expense exists and the user can view it.
        expense = self.get_expense(expense_id, user)

        if expense["created_by"] != user_id:
            raise PermissionDenied(
                "Only the expense creator can edit this expense."
            )

        try:
            updated = self.repository.update_by_creator(
                expense_id=expense_id,
                user_id=user_id,
                updates=updates,
            )
        except ValueError as exc:
            raise ValidationError({"expense": str(exc)})

        if updated is None:
            raise NotFound(
                "Expense not found or is no longer available."
            )

        return updated

    def delete_expense(self, expense_id, user):
        """Soft-delete an expense only for its creator."""
        user_id = self._user_id(user)

        # Check existence and group access before deletion.
        expense = self.get_expense(expense_id, user)

        if expense["created_by"] != user_id:
            raise PermissionDenied(
                "Only the expense creator can delete this expense."
            )

        deleted = self.repository.soft_delete_by_creator(
            expense_id=expense_id,
            user_id=user_id,
        )

        if not deleted:
            raise NotFound(
                "Expense not found or is already deleted."
            )

        return {
            "message": "Expense deleted successfully."
        }
