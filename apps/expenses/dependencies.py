
"""
Dependency factory for SplitMate expenses.

Connect this to your existing MongoDB connection
and group membership repository.
"""

from .repositories import ExpenseRepository
from .services import ExpenseService


def get_expense_service():
    """
    Build the expense service using the application's
    existing MongoDB collection and group membership logic.

    Replace the imports and calls below with your actual
    project implementations.
    """

    # TODO: Import your existing MongoDB expenses collection.
    # Example:
    # from apps.core.database import db
    # expenses_collection = db["expenses"]

    # TODO: Import your existing group membership checker.
    # It must accept (group_id, user_id) and return True/False.
    # Example:
    # from apps.groups.repositories import is_group_member

    raise NotImplementedError(
        "Connect get_expense_service() to your existing "
        "MongoDB expenses collection and group membership repository."
    )
