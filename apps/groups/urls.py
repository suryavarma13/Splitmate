
import logging

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import GroupsViewSet

logger = logging.getLogger(__name__)

router = SimpleRouter()
router.register(
    prefix="",
    viewset=GroupsViewSet,
    basename="groups",
)

urlpatterns = [
    path("", include(router.urls)),
]
logger.info("SplitMate Groups URL routes configured.")


# roups API endpoints
# Method	Endpoint	Purpose
# POST	/api/v1/groups/	Create group
# GET	/api/v1/groups/	List user's groups
# GET	/api/v1/groups/{id}/	Group details
# PUT / PATCH	/api/v1/groups/{id}/	Update group
# GET	/api/v1/groups/{id}/members/	List members
# POST	/api/v1/groups/{id}/members/	Add members
# DELETE	/api/v1/groups/{id}/members/{user_id}/	Remove member
# POST	/api/v1/groups/{id}/invitations/	Invite by email
# GET	/api/v1/groups/invitations/	View invitations
# POST	/api/v1/groups/invitations/accept/	Accept invitation using token
# POST	/api/v1/groups/invitations/{invitation_id}/decline/	Decline invitation
# POST	/api/v1/groups/invitations/{invitation_id}/cancel/	Cancel invitation
# POST	/api/v1/groups/invitations/{invitation_id}/resend/	Resend invitation email