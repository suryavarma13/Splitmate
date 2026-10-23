
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.authentication.urls")),
    path("api/v1/friends/", include("apps.friends.urls")),
    path("api/v1/groups/", include("apps.groups.urls")),
    path("api/v1/expenses/", include("apps.expenses.urls")),
    path("api/v1/balances/", include("apps.balances.urls")),
    path("api/v1/settlements/", include("apps.settlements.urls")),
    path("api/v1/payments/", include("apps.payments.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/receipts/", include("apps.receipts.urls")),
    path("api/v1/reports/", include("apps.reports.urls")),
    path("api/v1/profile/", include("apps.profiles.urls")),
]

# Serve uploaded media during local development only.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
