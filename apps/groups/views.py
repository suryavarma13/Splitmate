"""API views and request handling."""

"""API views for SplitMate Groups."""

import logging

from bson import ObjectId
from django.conf import settings
from django.core.mail import send_mail
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import JSONParser,MultiPartParser, FormParser
from django.core.files.storage import default_storage


from .serializers import (
    CreateGroupSerializer,
    UpdateGroupSerializer,
    AddGroupMembersSerializer,
    CreateGroupInvitationSerializer,
    AcceptGroupInvitationSerializer,
)
from . import repositories as repo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# STANDARD API RESPONSES
# ---------------------------------------------------------

def success_response(message, data=None, http_status=status.HTTP_200_OK):
    return Response(
        {
            "success": True,
            "message": message,
            "data": data,
        },
        status=http_status,
    )


def error_response(
    message,
    http_status=status.HTTP_400_BAD_REQUEST,
    errors=None,
):
    body = {
        "success": False,
        "message": message,
    }

    if errors is not None:
        body["errors"] = errors

    return Response(body, status=http_status)


def unexpected_error(operation):
    logger.exception("Unexpected Groups API error: %s", operation)

    return error_response(
        "An unexpected server error occurred. Please try again later.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def get_user_id(request):
    """Support the custom JWT authentication user representation."""
    user = request.user

    if isinstance(user, dict):
        value = user.get("id") or user.get("_id")
    else:
        value = (
            getattr(user, "id", None)
            or getattr(user, "_id", None)
        )

    if isinstance(value, ObjectId):
        return str(value)

    return str(value) if value else None


def get_user_email(request):
    user = request.user

    if isinstance(user, dict):
        email = user.get("email")
    else:
        email = getattr(user, "email", None)

    return email.strip().lower() if isinstance(email, str) else ""


def validate_serializer(serializer):
    if serializer.is_valid():
        return None

    logger.warning(
        "Groups API validation failed. Fields: %s",
        ", ".join(serializer.errors.keys()),
    )

    return error_response(
        "Request validation failed.",
        status.HTTP_400_BAD_REQUEST,
        serializer.errors,
    )


def repository_response(result, error, code):
    if error:
        return error_response(error, code)

    return success_response(
        "Operation completed successfully.",
        result,
        code,
    )


# ---------------------------------------------------------
# GROUPS: CREATE, LIST, DETAILS, UPDATE
# ---------------------------------------------------------

class GroupsViewSet(viewsets.ViewSet):
    """Create and manage groups and their members."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser,MultiPartParser, FormParser]

    
    
    def create(self, request):
        """POST /api/v1/groups/"""
        logger.info("Group creation requested.")

        user_id = get_user_id(request)

        if not user_id:
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = CreateGroupSerializer(data=request.data)
        invalid = validate_serializer(serializer)

        if invalid:
            return invalid

        saved_path = None

        try:
            data = serializer.validated_data
            uploaded_image = data.get("image")
            image_url = data.get("image_url")

            # Save an uploaded image to Django media storage.
            if uploaded_image:
                saved_path = default_storage.save(
                    f"groups/{uploaded_image.name}",
                    uploaded_image,
                )
                image_url = default_storage.url(saved_path)

            result, error, code = repo.create_group(
                creator_id=user_id,
                name=data["name"],
                description=data.get("description", ""),
                image_url=image_url,
            )

            if error:
                # Remove the newly uploaded file if group creation failed.
                if saved_path:
                    default_storage.delete(saved_path)
                return error_response(error, code)

            creator = request.user
            if isinstance(creator, dict):
                creator_name = (
                    creator.get("name")
                    or creator.get("full_name")
                    or creator.get("username")
                    or ""
                )
            else:
                creator_name = (
                    getattr(creator, "name", None)
                    or getattr(creator, "full_name", None)
                    or getattr(creator, "username", None)
                    or ""
                )

            result["created_by_name"] = creator_name

            logger.info(
                "Group created successfully. group_id=%s image_uploaded=%s",
                result.get("id"),
                bool(saved_path),
            )

            return success_response(
                "Group created successfully.",
                result,
                status.HTTP_201_CREATED,
            )

        except Exception:
            if saved_path:
                try:
                    default_storage.delete(saved_path)
                except Exception:
                    logger.exception("Failed to clean up uploaded group image.")

            logger.exception("Unexpected error while creating group.")
            return unexpected_error("create group")


    def list(self, request):
        """GET /api/v1/groups/"""
        logger.info("User groups requested.")

        user_id = get_user_id(request)

        if not user_id:
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        try:
            groups = repo.list_user_groups(user_id)

            return success_response(
                "Groups retrieved successfully.",
                groups,
            )

        except Exception:
            return unexpected_error("list groups")

    def retrieve(self, request, pk=None):
        """GET /api/v1/groups/{id}/"""
        user_id = get_user_id(request)

        if not user_id:
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        try:
            result, error, code = repo.get_group_details(pk, user_id)

            if error:
                return error_response(error, code)

            return success_response(
                "Group details retrieved successfully.",
                result,
            )

        except Exception:
            return unexpected_error("retrieve group")

    def update(self, request, pk=None):
        """PUT /api/v1/groups/{id}/"""
        return self._update_group(request, pk)

    def partial_update(self, request, pk=None):
        """PATCH /api/v1/groups/{id}/"""
        return self._update_group(request, pk)

    def _update_group(self, request, pk):
        user_id = get_user_id(request)

        if not user_id:
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = UpdateGroupSerializer(data=request.data)
        invalid = validate_serializer(serializer)

        if invalid:
            return invalid

        try:
            result, error, code = repo.update_group(
                group_id=pk,
                user_id=user_id,
                **serializer.validated_data,
            )

            if error:
                return error_response(error, code)

            return success_response(
                "Group updated successfully.",
                result,
            )

        except Exception:
            return unexpected_error("update group")

    # -----------------------------------------------------
    # GROUP MEMBERS
    # -----------------------------------------------------

    @action(detail=True, methods=["post"], url_path="members")
    def add_members(self, request, pk=None):
        """POST /api/v1/groups/{id}/members/"""
        user_id = get_user_id(request)

        if not user_id:
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = AddGroupMembersSerializer(data=request.data)
        invalid = validate_serializer(serializer)

        if invalid:
            return invalid

        try:
            result, error, code = repo.add_group_members(
                group_id=pk,
                admin_id=user_id,
                member_ids=serializer.validated_data["member_ids"],
            )

            if error:
                return error_response(error, code)

            return success_response(
                "Group members added successfully.",
                result,
            )

        except Exception:
            return unexpected_error("add group members")

    @action(
        detail=True,
        methods=["get"],
        url_path="members",
        url_name="members-list",
    )
    def members(self, request, pk=None):
        """GET /api/v1/groups/{id}/members/"""
        user_id = get_user_id(request)

        if not user_id:
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        try:
            group, error, code = repo.get_group_details(pk, user_id)

            if error:
                return error_response(error, code)

            return success_response(
                "Group members retrieved successfully.",
                group.get("members", []),
            )

        except Exception:
            return unexpected_error("list group members")

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"members/(?P<user_id>[0-9a-fA-F]{24})",
    )
    def remove_member(self, request, pk=None, user_id=None):
        """DELETE /api/v1/groups/{id}/members/{user_id}/"""
        admin_id = get_user_id(request)

        if not admin_id:
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        try:
            removed, error, code = repo.remove_group_member(
                group_id=pk,
                admin_id=admin_id,
                member_id=user_id,
            )

            if error:
                return error_response(error, code)

            return success_response(
                "Group member removed successfully.",
                {"user_id": user_id},
            )

        except Exception:
            return unexpected_error("remove group member")

    # -----------------------------------------------------
    # CREATE INVITATION AND SEND EMAIL
    # -----------------------------------------------------

    @action(detail=True, methods=["post"], url_path="invitations")
    def invite(self, request, pk=None):
        """POST /api/v1/groups/{id}/invitations/"""
        inviter_id = get_user_id(request)

        if not inviter_id:
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = CreateGroupInvitationSerializer(data=request.data)
        invalid = validate_serializer(serializer)

        if invalid:
            return invalid

        try:
            invitation, error, code = repo.create_invitation(
                group_id=pk,
                inviter_id=inviter_id,
                email=serializer.validated_data["email"],
            )

            if error:
                return error_response(error, code)

            # Do not report a successful email invitation unless the
            # configured email service actually sends the message.
            token = invitation.get("token")

            frontend_url = getattr(
                settings,
                "SPLITMATE_FRONTEND_URL",
                "",
            ).rstrip("/")

            if not frontend_url or not token:
                logger.error(
                    "Invitation created but email configuration is missing."
                )
                return error_response(
                    "Invitation was created, but email configuration is incomplete. "
                    "Configure SPLITMATE_FRONTEND_URL and email settings.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            invitation_url = (
                f"{frontend_url}/accept-invitation"
                f"?token={token}"
            )

            try:
                send_mail(
                    subject=f"You're invited to join {invitation['group_name']} on SplitMate",
                    message=(
                        f"You have been invited to join "
                        f"{invitation['group_name']} on SplitMate.\n\n"
                        f"Open this link to continue:\n{invitation_url}\n\n"
                        "This invitation expires in 7 days."
                    ),
                    from_email=getattr(
                        settings,
                        "DEFAULT_FROM_EMAIL",
                        None,
                    ),
                    recipient_list=[invitation["email"]],
                    fail_silently=False,
                )

            except Exception:
                logger.exception("Failed to send group invitation email.")

                return error_response(
                    "Invitation was created, but the email could not be sent. "
                    "Please retry after checking email configuration.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # Never return the invitation token in the API response.
            invitation.pop("token", None)

            return success_response(
                "Invitation created and email sent successfully.",
                invitation,
                status.HTTP_201_CREATED,
            )

        except Exception:
            return unexpected_error("create group invitation")

    # -----------------------------------------------------
    # VIEW INVITATIONS FOR CURRENT USER
    # -----------------------------------------------------

    @action(
        detail=False,
        methods=["get"],
        url_path="invitations",
    )
    def invitations(self, request):
        """GET /api/v1/groups/invitations/"""
        email = get_user_email(request)

        if not email:
            return error_response(
                "Authenticated user's email was not found.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            invitations = repo.list_invitations(email)

            return success_response(
                "Invitations retrieved successfully.",
                invitations,
            )

        except Exception:
            return unexpected_error("list invitations")

    # -----------------------------------------------------
    # ACCEPT INVITATION BY SECURE TOKEN
    # -----------------------------------------------------

    @action(
        detail=False,
        methods=["post"],
        url_path="invitations/accept",
    )
    def accept_invitation(self, request):
        """POST /api/v1/groups/invitations/accept/"""
        user_id = get_user_id(request)
        email = get_user_email(request)

        if not user_id or not email:
            return error_response(
                "Authenticated user ID and email are required.",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = AcceptGroupInvitationSerializer(data=request.data)
        invalid = validate_serializer(serializer)

        if invalid:
            return invalid

        try:
            result, error, code = repo.accept_invitation(
                token=serializer.validated_data["token"],
                user_id=user_id,
                user_email=email,
            )

            if error:
                return error_response(error, code)

            return success_response(
                "You joined the group successfully.",
                result,
            )

        except Exception:
            return unexpected_error("accept group invitation")

    # -----------------------------------------------------
    # DECLINE INVITATION
    # -----------------------------------------------------

    @action(
        detail=False,
        methods=["post"],
        url_path=r"invitations/(?P<invitation_id>[0-9a-fA-F]{24})/decline",
    )
    def decline_invitation(self, request, invitation_id=None):
        """POST /api/v1/groups/invitations/{id}/decline/"""
        email = get_user_email(request)

        if not email:
            return error_response(
                "Authenticated user's email was not found.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            result, error, code = repo.update_invitation(
                invitation_id=invitation_id,
                user_email=email,
                action="declined",
            )

            if error:
                return error_response(error, code)

            return success_response(
                "Invitation declined successfully.",
                result,
            )

        except Exception:
            return unexpected_error("decline group invitation")

    # -----------------------------------------------------
    # CANCEL INVITATION
    # -----------------------------------------------------

    @action(
        detail=False,
        methods=["post"],
        url_path=r"invitations/(?P<invitation_id>[0-9a-fA-F]{24})/cancel",
    )
    def cancel_invitation(self, request, invitation_id=None):
        """POST /api/v1/groups/invitations/{id}/cancel/"""
        email = get_user_email(request)

        if not email:
            return error_response(
                "Authenticated user's email was not found.",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            result, error, code = repo.update_invitation(
                invitation_id=invitation_id,
                user_email=email,
                action="cancelled",
            )

            if error:
                return error_response(error, code)

            return success_response(
                "Invitation cancelled successfully.",
                result,
            )

        except Exception:
            return unexpected_error("cancel group invitation")

    # -----------------------------------------------------
    # RESEND INVITATION EMAIL
    # -----------------------------------------------------

    @action(
        detail=False,
        methods=["post"],
        url_path=r"invitations/(?P<invitation_id>[0-9a-fA-F]{24})/resend",
    )
    def resend_invitation(self, request, invitation_id=None):
        """
        POST /api/v1/groups/invitations/{invitation_id}/resend/

        The repository must verify that the caller is a group admin,
        the invitation is pending, and the invitation has not been revoked.
        It should rotate the token and return the raw token only for email use.
        """
        inviter_id = get_user_id(request)

        if not inviter_id:
            logger.warning(
                "Invitation resend denied: authenticated user ID missing."
            )
            return error_response(
                "Authenticated user ID was not found.",
                status.HTTP_401_UNAUTHORIZED,
            )

        logger.info(
            "Invitation resend requested. invitation_id=%s",
            invitation_id,
        )

        try:
            invitation, error, code = repo.resend_invitation(
                invitation_id=invitation_id,
                inviter_id=inviter_id,
            )

            if error:
                logger.warning(
                    "Invitation resend rejected. invitation_id=%s status=%s",
                    invitation_id,
                    code,
                )
                return error_response(error, code)

            # The repository's public representation normally removes token.
            # The resend method must explicitly return it for this email send.
            token = invitation.pop("token", None)
            frontend_url = getattr(
                settings,
                "SPLITMATE_FRONTEND_URL",
                "",
            )
            frontend_url = (
                frontend_url.rstrip("/")
                if isinstance(frontend_url, str)
                else ""
            )

            if not frontend_url or not token:
                logger.error(
                    "Invitation resend configuration/token missing. invitation_id=%s",
                    invitation_id,
                )
                return error_response(
                    "Invitation could not be emailed because configuration is incomplete.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            recipient = invitation.get("email")
            group_name = invitation.get("group_name") or "a SplitMate group"

            if not recipient:
                logger.error(
                    "Invitation resend recipient missing. invitation_id=%s",
                    invitation_id,
                )
                return error_response(
                    "Invitation recipient is missing.",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            invitation_url = (
                f"{frontend_url}/accept-invitation?token={token}"
            )

            try:
                sent_count = send_mail(
                    subject=f"You're invited to join {group_name} on SplitMate",
                    message=(
                        f"You have been invited to join {group_name} on SplitMate.\n\n"
                        f"Open this link to continue:\n{invitation_url}\n\n"
                        "This invitation expires in 7 days."
                    ),
                    from_email=getattr(
                        settings,
                        "DEFAULT_FROM_EMAIL",
                        None,
                    ),
                    recipient_list=[recipient],
                    fail_silently=False,
                )

                if sent_count != 1:
                    raise RuntimeError(
                        "Email backend did not confirm that one message was sent."
                    )

            except Exception:
                # Never log the email body, invitation URL, or token.
                logger.exception(
                    "Invitation email send failed. invitation_id=%s",
                    invitation_id,
                )
                return error_response(
                    "The invitation link was refreshed, but the email could not be sent. "
                    "Please contact support or retry after checking email settings.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            logger.info(
                "Invitation email accepted by email backend. invitation_id=%s",
                invitation_id,
            )

            # Do not expose the token to the API caller.
            return success_response(
                "Invitation email resent successfully.",
                invitation,
                status.HTTP_200_OK,
            )

        except Exception:
            return unexpected_error("resend group invitation")

