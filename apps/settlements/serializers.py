
"""
SplitMate Settlement Serializers.

Validates settlement data and formats API responses.
No payment gateway is used.
"""

from rest_framework import serializers


class SettlementResponseSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    group_id = serializers.CharField(read_only=True)
    expense_id = serializers.CharField(read_only=True)
    user_id = serializers.CharField(read_only=True)
    amount_minor = serializers.IntegerField(read_only=True)

    status = serializers.ChoiceField(
        choices=["PENDING", "PAID"],
        read_only=True,
    )

    marked_paid_at = serializers.CharField(
        read_only=True,
        allow_null=True,
        required=False,
    )

    confirmed_by = serializers.CharField(
        read_only=True,
        allow_null=True,
        required=False,
    )

    confirmed_at = serializers.CharField(
        read_only=True,
        allow_null=True,
        required=False,
    )

    created_at = serializers.CharField(
        read_only=True,
        required=False,
    )


class SettlementMarkPaidSerializer(serializers.Serializer):
    """
    No payment details are required.
    The authenticated member marks their own settlement as paid.
    """
    pass


class SettlementConfirmPaidSerializer(serializers.Serializer):
    """
    No client-supplied payment or owner ID is accepted.
    The authenticated user is checked against group ownership.
    """
    pass
