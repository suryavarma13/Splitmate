"""API views and request handling."""

# apps/friends/views.py

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import APIException

from .repositories import (
    search_users,
    create_friend_request,
    list_requests,
    update_request,
    list_friends,
    remove_friend,
)

logger = logging.getLogger("apps.friends")


def api_error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"message": message}, status=code)


def current_user_id(request):
    """Return the authenticated MongoDB user ID."""
    user_id = getattr(request.user, "id", None)
    if not user_id:
        raise APIException("Authenticated user ID is unavailable.")
    return str(user_id)


def log_action(action_name, user_id):
    # Never log passwords, JWTs, email verification tokens, or request bodies.
    logger.info(
        "Friends API action=%s user_id=%s",
        action_name,
        user_id,
    )


class FriendRequestViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def create(self, request):
        user_id = current_user_id(request)
        recipient_id = request.data.get("recipient_id")

        if not isinstance(recipient_id, str) or not recipient_id.strip():
            return api_error(
                "recipient_id must be a non-empty string."
            )

        recipient_id = recipient_id.strip()

        try:
            doc, error = create_friend_request(
                user_id,
                recipient_id,
            )

            if error:
                message = error.lower()

                if "not found" in message:
                    code = status.HTTP_404_NOT_FOUND
                elif "already exists" in message or "already friends" in message:
                    code = status.HTTP_409_CONFLICT
                elif "already sent you" in message:
                    code = status.HTTP_409_CONFLICT
                elif "yourself" in message:
                    code = status.HTTP_400_BAD_REQUEST
                else:
                    code = status.HTTP_400_BAD_REQUEST

                logger.warning(
                    "Friend request rejected user_id=%s reason=%s",
                    user_id,
                    error,
                )
                return api_error(error, code)

            log_action("request_created", user_id)

            return Response(
                {
                    "message": "Friend request sent.",
                    "request_id": str(doc["_id"]),
                    "status": doc["status"],
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception(
                "Failed to create friend request user_id=%s",
                user_id,
            )
            return api_error(
                "Unable to send friend request right now.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="received")
    def received(self, request):
        return self._list_requests(request, "received")

    @action(detail=False, methods=["get"], url_path="sent")
    def sent(self, request):
        return self._list_requests(request, "sent")

    def _list_requests(self, request, direction):
        user_id = current_user_id(request)

        try:
            results = list_requests(user_id, direction)
            log_action(f"requests_{direction}", user_id)
            return Response(results, status=status.HTTP_200_OK)

        except Exception:
            logger.exception(
                "Failed to list %s requests user_id=%s",
                direction,
                user_id,
            )
            return api_error(
                "Unable to retrieve friend requests.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _process_request(self, request, pk, action_name):
        user_id = current_user_id(request)

        try:
            result, error, code = update_request(
                pk,
                user_id,
                action_name,
            )

            if error:
                logger.warning(
                    "Friend request action rejected action=%s user_id=%s",
                    action_name,
                    user_id,
                )
                return api_error(error, code)

            log_action(f"request_{action_name}", user_id)

            messages = {
                "accept": "Friend request accepted.",
                "reject": "Friend request rejected.",
                "cancel": "Friend request cancelled.",
            }

            return Response(
                {
                    "message": messages[action_name],
                    "request": result,
                },
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception(
                "Failed to %s friend request user_id=%s",
                action_name,
                user_id,
            )
            return api_error(
                "Unable to process friend request right now.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        return self._process_request(request, pk, "accept")

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        return self._process_request(request, pk, "reject")

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        return self._process_request(request, pk, "cancel")


class FriendsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        user_id = current_user_id(request)
        query = request.query_params.get("query", "").strip()

        if not query:
            return api_error(
                "The query parameter is required."
            )

        if len(query) > 100:
            return api_error(
                "Search query cannot exceed 100 characters."
            )

        try:
            results = search_users(query, user_id)
            log_action("search_users", user_id)
            return Response(results, status=status.HTTP_200_OK)

        except Exception:
            logger.exception(
                "User search failed user_id=%s",
                user_id,
            )
            return api_error(
                "Unable to search users right now.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def list(self, request):
        user_id = current_user_id(request)

        try:
            results = list_friends(user_id)
            log_action("list_friends", user_id)
            return Response(results, status=status.HTTP_200_OK)

        except Exception:
            logger.exception(
                "Failed to list friends user_id=%s",
                user_id,
            )
            return api_error(
                "Unable to retrieve friends.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def destroy(self, request, pk=None):
        user_id = current_user_id(request)

        if not pk:
            return api_error("Friend ID is required.")

        try:
            removed = remove_friend(user_id, pk)

            if not removed:
                return api_error(
                    "Friendship not found.",
                    status.HTTP_404_NOT_FOUND,
                )

            log_action("friend_removed", user_id)
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception:
            logger.exception(
                "Failed to remove friend user_id=%s",
                user_id,
            )
            return api_error(
                "Unable to remove friend right now.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
