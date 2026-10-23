
"""
Professional expense serializers for SplitMate.

Responsibilities:
- Validate expense creation requests.
- Validate selected participants and split inputs.
- Calculate shares using the existing calculators.py.
- Validate expense update requests.

MongoDB reads/writes and group membership checks belong in
services.py and repositories.py.
"""

import re
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .calculators import (
    split_equally,
    split_by_percentage,
    split_custom,
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

SPLIT_METHODS = (
    ("equal", "Equal split"),
    ("exact", "Exact amount split"),
    ("percentage", "Percentage split"),
)

EXPENSE_CATEGORIES = (
    ("Food", "Food"),
    ("Travel", "Travel"),
    ("Rent", "Rent"),
    ("Shopping", "Shopping"),
    ("Utilities", "Utilities"),
    ("Transport", "Transport"),
    ("Entertainment", "Entertainment"),
    ("Health", "Health"),
    ("Groceries", "Groceries"),
    ("Other", "Other"),
)

MAX_PARTICIPANTS = 100
MAX_EXPENSE_PAISE = 100_000_000_000


# ---------------------------------------------------------
# Money and ID helpers
# ---------------------------------------------------------

def normalize_id(value):
    """Normalize a user or group ID for comparisons."""
    return str(value).strip()


def amount_to_paise(amount, allow_zero=False):
    """Convert a decimal monetary amount to integer paise."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid monetary amount.")

    if not value.is_finite():
        raise ValueError("Amount must be finite.")

    if value < 0:
        raise ValueError("Amount cannot be negative.")

    if value == 0 and not allow_zero:
        raise ValueError("Amount must be greater than zero.")

    paise = value * 100

    if paise != paise.to_integral_value():
        raise ValueError(
            "Amount cannot have more than two decimal places."
        )

    return int(paise)


# ---------------------------------------------------------
# Participant share serializer
# ---------------------------------------------------------

class SplitShareInputSerializer(serializers.Serializer):
    """Input for one participant in an exact or percentage split."""

    user_id = serializers.CharField(
        max_length=128,
        trim_whitespace=True,
    )

    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
    )

    percentage = serializers.DecimalField(
        max_digits=7,
        decimal_places=4,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        required=False,
    )

    def validate_user_id(self, value):
        value = normalize_id(value)

        if not value:
            raise serializers.ValidationError(
                "Participant ID cannot be empty."
            )

        return value

    def validate(self, attrs):
        if "amount" in attrs and "percentage" in attrs:
            raise serializers.ValidationError(
                "Provide either amount or percentage, not both."
            )

        return attrs


# ---------------------------------------------------------
# Create expense serializer
# ---------------------------------------------------------

class ExpenseCreateSerializer(serializers.Serializer):
    """Validate expense data and calculate final participant shares."""

    group_id = serializers.CharField(
        max_length=128,
        trim_whitespace=True,
    )

    title = serializers.CharField(
        max_length=200,
        trim_whitespace=True,
    )

    total_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    currency = serializers.CharField(
        max_length=3,
        default="INR",
    )

    paid_by_user_id = serializers.CharField(
        max_length=128,
        trim_whitespace=True,
    )

    participant_ids = serializers.ListField(
        child=serializers.CharField(
            max_length=128,
            trim_whitespace=True,
        ),
        allow_empty=False,
        max_length=MAX_PARTICIPANTS,
    )

    split_method = serializers.ChoiceField(
        choices=SPLIT_METHODS,
        default="equal",
    )

    shares = SplitShareInputSerializer(
        many=True,
        required=False,
        allow_empty=True,
    )

    category = serializers.ChoiceField(
        choices=EXPENSE_CATEGORIES,
        default="Other",
    )

    expense_date = serializers.DateField()

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        default="",
        trim_whitespace=True,
    )

    receipt_url = serializers.URLField(
        required=False,
        allow_blank=True,
        max_length=2048,
    )

    # -----------------------------------------------------
    # Field-level validation
    # -----------------------------------------------------

    def validate_group_id(self, value):
        value = normalize_id(value)

        if not value:
            raise serializers.ValidationError(
                "Group ID is required."
            )

        return value

    def validate_title(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Expense title is required."
            )

        return value

    def validate_currency(self, value):
        value = value.strip().upper()

        if not re.fullmatch(r"[A-Z]{3}", value):
            raise serializers.ValidationError(
                "Use a three-letter currency code, such as INR."
            )

        return value

    def validate_paid_by_user_id(self, value):
        value = normalize_id(value)

        if not value:
            raise serializers.ValidationError(
                "Payer ID is required."
            )

        return value

    def validate_participant_ids(self, value):
        participant_ids = [
            normalize_id(user_id)
            for user_id in value
        ]

        if any(not user_id for user_id in participant_ids):
            raise serializers.ValidationError(
                "Participant IDs cannot be empty."
            )

        if len(participant_ids) != len(set(participant_ids)):
            raise serializers.ValidationError(
                "Duplicate participants are not allowed."
            )

        if len(participant_ids) > MAX_PARTICIPANTS:
            raise serializers.ValidationError(
                f"Select no more than {MAX_PARTICIPANTS} participants."
            )

        return participant_ids

    def validate_shares(self, value):
        share_ids = [item["user_id"] for item in value]

        if len(share_ids) != len(set(share_ids)):
            raise serializers.ValidationError(
                "Duplicate share entries are not allowed."
            )

        return value

    # -----------------------------------------------------
    # Cross-field validation and calculation
    # -----------------------------------------------------

    def validate(self, attrs):
        participant_ids = attrs["participant_ids"]
        payer_id = attrs["paid_by_user_id"]
        split_method = attrs["split_method"]
        shares = attrs.get("shares", [])

        # Convert the total into integer paise.
        try:
            total_paise = amount_to_paise(
                attrs["total_amount"]
            )
        except ValueError as exc:
            raise serializers.ValidationError({
                "total_amount": str(exc)
            })

        if total_paise > MAX_EXPENSE_PAISE:
            raise serializers.ValidationError({
                "total_amount": "The expense exceeds the allowed limit."
            })

        # The payer must be part of this expense's participant list.
        # Group membership must also be checked by the service.
        if payer_id not in participant_ids:
            raise serializers.ValidationError({
                "paid_by_user_id": (
                    "The payer must be included in participant_ids."
                )
            })

        # Equal split
        if split_method == "equal":
            if shares:
                raise serializers.ValidationError({
                    "shares": (
                        "Do not provide individual shares for an equal split."
                    )
                })

            calculated = split_equally(
                total_paise,
                participant_ids,
            )

        # Exact amount or percentage split
        else:
            if not shares:
                raise serializers.ValidationError({
                    "shares": (
                        "Provide a share entry for every selected participant."
                    )
                })

            supplied_ids = [item["user_id"] for item in shares]

            if set(supplied_ids) != set(participant_ids):
                raise serializers.ValidationError({
                    "shares": (
                        "Share entries must match the selected participants "
                        "exactly."
                    )
                })

            shares_by_user = {
                item["user_id"]: item
                for item in shares
            }

            ordered_shares = [
                shares_by_user[user_id]
                for user_id in participant_ids
            ]

            # Exact amount split
            if split_method == "exact":
                amounts = {}

                for item in ordered_shares:
                    if "amount" not in item:
                        raise serializers.ValidationError({
                            "shares": (
                                "Every participant needs an exact amount."
                            )
                        })

                    try:
                        amounts[item["user_id"]] = amount_to_paise(
                            item["amount"],
                            allow_zero=True,
                        )
                    except ValueError as exc:
                        raise serializers.ValidationError({
                            "shares": str(exc)
                        })

                try:
                    calculated = split_custom(
                        total_paise,
                        amounts,
                    )
                except ValueError as exc:
                    raise serializers.ValidationError({
                        "shares": str(exc)
                    })

            # Percentage split
            else:
                percentages = {}

                for item in ordered_shares:
                    if "percentage" not in item:
                        raise serializers.ValidationError({
                            "shares": (
                                "Every participant needs a percentage."
                            )
                        })

                    percentages[item["user_id"]] = item["percentage"]

                try:
                    calculated = split_by_percentage(
                        total_paise,
                        percentages,
                    )
                except ValueError as exc:
                    raise serializers.ValidationError({
                        "shares": str(exc)
                    })

        # Ensure calculated shares cover exactly the selected participants.
        if set(calculated) != set(participant_ids):
            raise serializers.ValidationError({
                "shares": (
                    "Calculated shares do not match the selected participants."
                )
            })

        if any(
            not isinstance(amount, int) or amount < 0
            for amount in calculated.values()
        ):
            raise serializers.ValidationError({
                "shares": "Shares must be non-negative integer paise."
            })

        if sum(calculated.values()) != total_paise:
            raise serializers.ValidationError({
                "shares": (
                    "The sum of participant shares must equal the expense total."
                )
            })

        # Add server-calculated values for the service/repository layer.
        attrs["total_amount_minor"] = total_paise

        attrs["calculated_shares"] = [
            {
                "user_id": user_id,
                "amount_minor": calculated[user_id],
            }
            for user_id in participant_ids
        ]

        return attrs


# ---------------------------------------------------------
# Update expense serializer
# ---------------------------------------------------------

class ExpenseUpdateSerializer(serializers.Serializer):
    """Validate editable expense metadata."""

    title = serializers.CharField(
        max_length=200,
        required=False,
        trim_whitespace=True,
    )

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        trim_whitespace=True,
    )

    category = serializers.ChoiceField(
        choices=EXPENSE_CATEGORIES,
        required=False,
    )

    expense_date = serializers.DateField(
        required=False,
    )

    def validate_title(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Expense title is required."
            )

        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Provide at least one field to update."
            )

        return attrs


# ---------------------------------------------------------
# Expense response serializer
# ---------------------------------------------------------

class ExpenseResponseSerializer(serializers.Serializer):
    """Serialize the public fields returned by the expense API."""

    id = serializers.CharField()
    group_id = serializers.CharField()
    title = serializers.CharField()
    total_amount_minor = serializers.IntegerField()
    currency = serializers.CharField()
    paid_by_user_id = serializers.CharField()
    participant_ids = serializers.ListField(
        child=serializers.CharField()
    )
    split_method = serializers.CharField()
    shares = serializers.ListField(
        child=serializers.DictField()
    )
    category = serializers.CharField()
    expense_date = serializers.CharField()
    notes = serializers.CharField()
    created_by = serializers.CharField()
