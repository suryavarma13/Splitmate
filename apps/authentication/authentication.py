from types import SimpleNamespace
import jwt

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .repositories import get_user_by_id


class MongoJWTAuthentication(BaseAuthentication):

    def authenticate(self, request):
        print("DEBUG: MongoJWTAuthentication started")

        header = request.headers.get("Authorization", "")

        if not header:
            print("DEBUG: Authorization header missing")
            return None

        print("DEBUG: Authorization header received")

        parts = header.split()

        if len(parts) != 2 or parts[0].lower() != "bearer":
            print("DEBUG: Invalid authorization header format")
            raise AuthenticationFailed("Invalid authorization header.")

        try:
            payload = jwt.decode(
                parts[1],
                settings.SECRET_KEY,
                algorithms=["HS256"],
            )
            print("DEBUG: JWT token decoded successfully")

        except jwt.InvalidTokenError:
            print("DEBUG: Invalid or expired JWT token")
            raise AuthenticationFailed("Invalid or expired token.")

        user_id = payload.get("sub", "")
        print(f"DEBUG: Token user ID: {user_id}")

        user = get_user_by_id(user_id)

        if not user or not user.get("is_active", True):
            print("DEBUG: User not found or inactive")
            raise AuthenticationFailed("User not found or inactive.")

        if not user.get("is_email_verified", False):
            print("DEBUG: User email is not verified")
            raise AuthenticationFailed("Please verify your email.")

        request_user = SimpleNamespace(
            id=str(user["_id"]),
            email=user["email"],
            full_name=user["full_name"],
            is_authenticated=True,
        )

        print(f"DEBUG: Authentication successful for {request_user.email}")

        return request_user, parts[1]