
import html
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    ResendVerificationSerializer,
    ForgotPasswordSerializer,
)
from .repositories import (
    create_user,
    get_user_by_email,
    check_user_password,
    save_code,
    verify_code,
    mark_email_verified,
    update_password,
)

logger = logging.getLogger(__name__)


def issue_token(user):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user["_id"]),
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def send_verification_link(email, token):
    base_url = settings.EMAIL_VERIFICATION_URL
    query = urlencode({"email": email, "token": token})
    link = f"{base_url}?{query}"

    send_mail(
        subject="Verify your SplitMate account",
        message=(
            "Welcome to SplitMate!\n\n"
            "Open this link to verify your email:\n\n"
            f"{link}\n\n"
            "This link expires in 15 minutes and can be used once."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def send_password_reset_link(email, token):
    base_url = settings.PASSWORD_RESET_URL
    query = urlencode({"email": email, "token": token})
    link = f"{base_url}?{query}"

    send_mail(
        subject="Reset your SplitMate password",
        message=(
            "We received a request to reset your SplitMate password.\n\n"
            "Open this link to choose a new password:\n\n"
            f"{link}\n\n"
            "This link expires in 15 minutes and can be used once.\n"
            "If you did not request this, ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


class UserViewSet(viewsets.ViewSet):

    
    # REGISTER
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path="register",
    )
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        email = data["email"].strip().lower()

        existing_user = get_user_by_email(email)

        # Existing verified account
        if existing_user:
            if existing_user.get("is_email_verified", False):
                return Response(
                    {"message": "Email already registered. Please log in."},
                    status=status.HTTP_409_CONFLICT,
                )

            # Existing account is unverified: send a fresh link
            token = secrets.token_urlsafe(32)
            save_code(
                email,
                token,
                "email_verification",
                datetime.now(timezone.utc) + timedelta(minutes=5),
            )

            try:
                send_verification_link(email, token)
            except Exception:
                logger.exception("Verification email delivery failed")
                return Response(
                    {"message": "Unable to send verification email."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            return Response(
                {"message": "A new verification link has been sent."},
                status=status.HTTP_200_OK,
            )

        # Create a new account
        user = create_user(
            data["full_name"],
            email,
            data["password"],
        )

        if not user:
            return Response(
                {"message": "Unable to create account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = secrets.token_urlsafe(32)
        save_code(
            email,
            token,
            "email_verification",
            datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        try:
            send_verification_link(email, token)
        except Exception:
            logger.exception("Verification email delivery failed")
            return Response(
                {
                    "message": (
                        "Account created, but email delivery failed. "
                        "Please request a new verification link."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "message": (
                    "Account created. Check your email for the "
                    "verification link."
                )
            },
            status=status.HTTP_201_CREATED,
        )


    # LOGIN
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path="login",
    )
    def login(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]
        user = get_user_by_email(email)

        if not check_user_password(user, password):
            return Response(
                {"message": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.get("is_email_verified", False):
            return Response(
                {"message": "Please verify your email first."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "message": "Login successful.",
                "access_token": issue_token(user),
                "token_type": "Bearer",
                "expires_in": 3600,
                "user": {
                    "id": str(user["_id"]),
                    "full_name": user["full_name"],
                    "email": user["email"],
                },
            }
        )

    # VERIFY EMAIL THROUGH EMAIL LINK
    @action(
        detail=False,
        methods=["get"],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path="verify-email",
    )
    def verify_email(self, request):
        email = request.query_params.get("email", "").strip().lower()
        token = request.query_params.get("token", "")

        if not email or not token:
            return Response(
                {"message": "Verification link is incomplete."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = get_user_by_email(email)
        if not user:
            return Response(
                {"message": "Invalid or expired verification link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.get("is_email_verified", False):
            return Response({"message": "Email is already verified."})

        if not verify_code(email, token, "email_verification"):
            return Response(
                {"message": "Invalid or expired verification link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mark_email_verified(email)
        return Response(
            {"message": "Email verified successfully. You can now log in."}
        )

    # RESEND VERIFICATION LINK
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path="resend-verification",
    )
    def resend_verification(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = get_user_by_email(email)

        # Return the same message to avoid revealing registered accounts.
        if user and not user.get("is_email_verified", False):
            token = secrets.token_urlsafe(32)
            save_code(
                email,
                token,
                "email_verification",
                datetime.now(timezone.utc) + timedelta(minutes=5),
            )
            try:
                send_verification_link(email, token)
            except Exception:
                logger.exception("Resend verification email failed")
                return Response(
                    {"message": "Unable to send verification email."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response(
            {"message": "If verification is needed, a new link will be sent."}
        )

    
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path="reset-password",
    )
    def reset_password(self, request):
        email = request.data.get("email", "").strip().lower()
        token = request.data.get("token", "")
        new_password = request.data.get("new_password", "")
        confirm_password = request.data.get("confirm_password", "")

        if not all([email, token, new_password, confirm_password]):
            return Response(
                {
                    "message": (
                        "Email, token, new password, and confirm password "
                        "are required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {"message": "Password must contain at least 8 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != confirm_password:
            return Response(
                {"message": "New password and confirm password do not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = get_user_by_email(email)

        if not user or not user.get("is_active", True):
            return Response(
                {"message": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not verify_code(email, token, "password_reset"):
            return Response(
                {"message": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        update_password(email, new_password)

        return Response(
            {"message": "Password reset successfully. You can now log in."},
            status=status.HTTP_200_OK,
        )
    
    # FORGOT PASSWORD
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[AllowAny],
        authentication_classes=[],
        url_path="forgot-password",
    )
    def forgot_password(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        user = get_user_by_email(email)

        # Use the same response whether the account exists or not
        if user and user.get("is_active", True):
            token = secrets.token_urlsafe(32)

            save_code(
                email,
                token,
                "password_reset",
                datetime.now(timezone.utc) + timedelta(minutes=5),
            )

            try:
                send_password_reset_link(email, token)
            except Exception:
                logger.exception("Password reset email delivery failed")
                return Response(
                    {"message": "Unable to send password reset email."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response(
            {
                "message": (
                    "If the account exists, a password reset link "
                    "will be sent to its email address."
                )
            },
            status=status.HTTP_200_OK,
        )


    # LOGOUT
    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        url_path="logout",
    )
    def logout(self, request):
        # JWT is not revoked server-side here. Clear it in the app.
        return Response(
            {"message": "Logged out. Clear the access token in the app."}
        )

    # GET PROFILE
    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAuthenticated],
        url_path="profile",
    )
    def profile(self, request):
        return Response(
            {
                "id": request.user.id,
                "full_name": request.user.full_name,
                "email": request.user.email,
            }
        )
