"""Request/response validation."""

"""Validation serializers for SplitMate Groups."""

import re

from rest_framework import serializers


OBJECT_ID_REGEX = re.compile(r"^[0-9a-fA-F]{24}$")


# ---------------------------------------------------------
# COMMON FIELDS
# ---------------------------------------------------------

class MongoObjectIdField(serializers.CharField):
    """Validate a MongoDB ObjectId represented as a string."""

    def __init__(self, **kwargs):
        kwargs.setdefault("min_length", 24)
        kwargs.setdefault("max_length", 24)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)

        if not OBJECT_ID_REGEX.fullmatch(value):
            raise serializers.ValidationError(
                "Enter a valid MongoDB ID."
            )

        return value


class GroupImageURLField(serializers.URLField):
    """Accept an optional HTTP(S) image URL."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)

        if not value.lower().startswith(("http://", "https://")):
            raise serializers.ValidationError(
                "Image URL must use HTTP or HTTPS."
            )

        return value


# ---------------------------------------------------------
# CREATE GROUP
# ---------------------------------------------------------

from rest_framework import serializers


class CreateGroupSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=True,
        min_length=1,
        max_length=100,
        trim_whitespace=True,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        default="",
        trim_whitespace=True,
    )

    image = serializers.ImageField(
        required=False,
        allow_null=True,
        write_only=True,
    )

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Group name cannot be empty."
            )
        return value.strip()


# ---------------------------------------------------------
# UPDATE GROUP
# ---------------------------------------------------------

class UpdateGroupSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=False,
        min_length=1,
        max_length=100,
        trim_whitespace=True,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
        trim_whitespace=True,
    )

    image_url = GroupImageURLField(
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "Provide at least one field to update."
            )
        return attrs

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Group name cannot be empty."
            )
        return value.strip()


# ---------------------------------------------------------
# ADD GROUP MEMBERS
# ---------------------------------------------------------

class AddGroupMembersSerializer(serializers.Serializer):
    member_ids = serializers.ListField(
        child=MongoObjectIdField(),
        required=True,
        min_length=1,
        max_length=100,
    )

    def validate_member_ids(self, value):
        # Remove repeated IDs from the same request.
        unique_ids = list(dict.fromkeys(value))

        if not unique_ids:
            raise serializers.ValidationError(
                "Provide at least one unique member ID."
            )

        return unique_ids


# ---------------------------------------------------------
# REMOVE GROUP MEMBER
# ---------------------------------------------------------

class RemoveGroupMemberSerializer(serializers.Serializer):
    user_id = MongoObjectIdField(required=True)


# ---------------------------------------------------------
# INVITATION EMAIL
# ---------------------------------------------------------

class CreateGroupInvitationSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True,
        max_length=254,
    )

    def validate_email(self, value):
        return value.strip().lower()


# ---------------------------------------------------------
# ACCEPT INVITATION
# ---------------------------------------------------------

class AcceptGroupInvitationSerializer(serializers.Serializer):
    token = serializers.CharField(
        required=True,
        min_length=20,
        max_length=200,
        trim_whitespace=True,
        write_only=True,
    )


# ---------------------------------------------------------
# INVITATION ACTIONS
# ---------------------------------------------------------

class GroupInvitationActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=("accept", "decline", "cancel", "resend"),
        required=True,
    )


class GroupInvitationIdSerializer(serializers.Serializer):
    invitation_id = MongoObjectIdField(required=True)


# ---------------------------------------------------------
# RESPONSE SERIALIZERS
# ---------------------------------------------------------

class GroupMemberSerializer(serializers.Serializer):
    user_id = serializers.CharField(read_only=True)
    role = serializers.ChoiceField(
        choices=("admin", "member"),
        read_only=True,
    )
    joined_at = serializers.DateTimeField(read_only=True)


class GroupResponseSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(
        read_only=True,
        allow_blank=True,
    )
    image_url = serializers.URLField(
        read_only=True,
        allow_null=True,
    )
    created_by = serializers.CharField(read_only=True)
    members = GroupMemberSerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


class GroupInvitationResponseSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    group_id = serializers.CharField(read_only=True)
    group_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    invited_by = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
