from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.views import LogoutView, MeView

urlpatterns = [
    # Obtain access + refresh token pair
    path("login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    # Refresh an access token using a valid refresh token
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Blacklist the refresh token (logout)
    path("logout/", LogoutView.as_view(), name="auth_logout"),
    # Return the authenticated user's profile and roles
    path("me/", MeView.as_view(), name="auth_me"),
]
