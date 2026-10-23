
"""URL configuration for SplitMate Friends APIs."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import FriendRequestViewSet, FriendsViewSet


# Friend request endpoints
request_router = SimpleRouter()
request_router.register(
    "requests",
    FriendRequestViewSet,
    basename="friend-requests",
)

# Friends list, search, and remove endpoints
friends_router = SimpleRouter()
friends_router.register(
    "",
    FriendsViewSet,
    basename="friends",
)

urlpatterns = [
    path("", include(request_router.urls)),
    path("", include(friends_router.urls)),
]


# Method	Endpoint	Purpose
# GET	/api/friends/search/?query=surya	Search users
# POST	/api/friends/requests/	Send a request
# GET	/api/friends/requests/received/	View received requests
# GET	/api/friends/requests/sent/	View sent requests
# POST	/api/friends/requests/{id}/accept/	Accept request
# POST	/api/friends/requests/{id}/reject/	Reject request
# POST	/api/friends/requests/{id}/cancel/	Cancel request
# GET	/api/friends/	List friends
# DELETE	/api/friends/{user_id}/	Remove friend