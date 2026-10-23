"""API views and request handling."""

"""
SplitMate Expense API Views.

Endpoints:
- POST   /api/v1/expenses/
- GET    /api/v1/groups/<group_id>/expenses/
- GET    /api/v1/expenses/<expense_id>/
- PATCH  /api/v1/expenses/<expense_id>/
- DELETE /api/v1/expenses/<expense_id>/

Architecture:
Views -> Serializers -> Services -> MongoDB Repositories

Features:
- Structured console logging
- Request ID tracking
- Validation and permission error handling
- Consistent JSON error responses
- Safe handling of unexpected exceptions
"""

import logging
import time
import uuid

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    ExpenseCreateSerializer,
    ExpenseUpdateSerializer,
    ExpenseResponseSerializer,
)
from .dependencies import get_expense_service


logger = logging.getLogger("splitmate.expenses")


class BaseExpenseAPIView(APIView):
    """Common logging and error handling for expense endpoints."""

    permission_classes = [IsAuthenticated]

    def dispatch(self, request, *args, **kwargs):
        request_id = request.headers.get("X-Request-ID")

        # Do not allow arbitrarily long request IDs in logs.
        if not request_id or len(request_id) > 100:
            request_id = str(uuid.uuid4())

        request.request_id = request_id
        start_time = time.perf_counter()

        logger.info(
            "Expense API request started | request_id=%s | method=%s | path=%s",
            request_id,
            request.method,
            request.path,
        )

        response = super().dispatch(request, *args, **kwargs)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response["X-Request-ID"] = request_id

        logger.info(
            "Expense API request completed | request_id=%s | method=%s "
            "| status=%s | duration_ms=%s",
            request_id,
            request.method,
            response.status_code,
            duration_ms,
        )

        return response

    def handle_exception(self, exc):
        request_id = getattr(self.request, "request_id", "unknown")

        if isinstance(exc, APIException):
            status_code = exc.status_code

            if status_code >= 500:
                logger.error(
                    "Expense API server error | request_id=%s | status=%s",
                    request_id,
                    status_code,
                )
            else:
                logger.warning(
                    "Expense API request rejected | request_id=%s "
                    "| status=%s | error_type=%s",
                    request_id,
                    status_code,
                    type(exc).__name__,
                )

            detail = exc.detail

        else:
            # Include traceback in server console, not in the API response.
            logger.exception(
                "Unexpected expense API exception | request_id=%s",
                request_id,
            )

            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            detail = "An unexpected server error occurred."

        return Response(
            {
                "success": False,
                "request_id": request_id,
                "error": detail,
            },
            status=status_code,
        )


class ExpenseCreateListView(BaseExpenseAPIView):
    """Create a new group expense."""

    def post(self, request):
        logger.info(
            "Creating expense | request_id=%s",
            request.request_id,
        )

        serializer = ExpenseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = get_expense_service()

        expense = service.create_expense(
            validated_data=serializer.validated_data,
            user=request.user,
        )

        logger.info(
            "Expense created | request_id=%s | expense_id=%s | group_id=%s",
            request.request_id,
            expense.get("id"),
            expense.get("group_id"),
        )

        return Response(
            {
                "success": True,
                "request_id": request.request_id,
                "message": "Expense created successfully.",
                "data": ExpenseResponseSerializer(expense).data,
            },
            status=status.HTTP_201_CREATED,
        )


class GroupExpenseListView(BaseExpenseAPIView):
    """List expenses for a group member."""

    def get(self, request, group_id):
        logger.info(
            "Listing group expenses | request_id=%s | group_id=%s",
            request.request_id,
            group_id,
        )

        try:
            limit = int(request.query_params.get("limit", 50))
            skip = int(request.query_params.get("skip", 0))
        except (TypeError, ValueError):
            return Response(
                {
                    "success": False,
                    "request_id": request.request_id,
                    "error": "limit and skip must be integers.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if limit < 1 or skip < 0:
            return Response(
                {
                    "success": False,
                    "request_id": request.request_id,
                    "error": (
                        "limit must be positive and skip "
                        "cannot be negative."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = get_expense_service()

        expenses = service.list_group_expenses(
            group_id=group_id,
            user=request.user,
            limit=min(limit, 100),
            skip=skip,
        )

        logger.info(
            "Group expenses retrieved | request_id=%s | group_id=%s "
            "| returned_count=%s",
            request.request_id,
            group_id,
            len(expenses),
        )

        return Response(
            {
                "success": True,
                "request_id": request.request_id,
                "count": len(expenses),
                "data": ExpenseResponseSerializer(
                    expenses, many=True
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class ExpenseDetailView(BaseExpenseAPIView):
    """Retrieve, edit, or soft-delete an expense."""

    def get(self, request, expense_id):
        logger.info(
            "Retrieving expense | request_id=%s | expense_id=%s",
            request.request_id,
            expense_id,
        )

        service = get_expense_service()

        expense = service.get_expense(
            expense_id=expense_id,
            user=request.user,
        )

        return Response(
            {
                "success": True,
                "request_id": request.request_id,
                "data": ExpenseResponseSerializer(expense).data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, expense_id):
        logger.info(
            "Updating expense | request_id=%s | expense_id=%s",
            request.request_id,
            expense_id,
        )

        serializer = ExpenseUpdateSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        service = get_expense_service()

        expense = service.update_expense(
            expense_id=expense_id,
            updates=serializer.validated_data,
            user=request.user,
        )

        logger.info(
            "Expense updated | request_id=%s | expense_id=%s",
            request.request_id,
            expense_id,
        )

        return Response(
            {
                "success": True,
                "request_id": request.request_id,
                "message": "Expense updated successfully.",
                "data": ExpenseResponseSerializer(expense).data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, expense_id):
        logger.info(
            "Deleting expense | request_id=%s | expense_id=%s",
            request.request_id,
            expense_id,
        )

        service = get_expense_service()

        result = service.delete_expense(
            expense_id=expense_id,
            user=request.user,
        )

        logger.info(
            "Expense soft-deleted | request_id=%s | expense_id=%s",
            request.request_id,
            expense_id,
        )

        return Response(
            {
                "success": True,
                "request_id": request.request_id,
                **result,
            },
            status=status.HTTP_200_OK,
        )
