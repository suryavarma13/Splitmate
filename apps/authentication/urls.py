
from rest_framework.routers import SimpleRouter
from .views import UserViewSet

router = SimpleRouter()
router.register("", UserViewSet, basename="auth-user")

urlpatterns = router.urls


# SplitMate Authentication APIs
#
# POST  /api/v1/auth/register/              Register user
# POST  /api/v1/auth/login/                 Login
# POST  /api/v1/auth/logout/                Logout
# GET   /api/v1/auth/verify-email/          Verify email using link
# POST  /api/v1/auth/resend-verification/   Resend verification link
# POST  /api/v1/auth/forgot-password/       Send password reset link
# GET   /api/v1/auth/reset-password/        Open new-password form
# POST  /api/v1/auth/reset-password/        Save new password
# GET   /api/v1/auth/profile/               Get user profile
