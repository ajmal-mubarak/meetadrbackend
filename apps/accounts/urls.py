"""Accounts and Authentication URL Patterns."""
from django.urls import path
from apps.accounts.views import (
    LoginView,
    RegisterView,
    RefreshTokenView,
    LogoutView,
    CurrentUserView
)

app_name = 'accounts'

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('token/refresh/', RefreshTokenView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', CurrentUserView.as_view(), name='current_user'),
]
