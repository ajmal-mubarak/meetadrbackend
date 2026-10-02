"""Notifications App URL Patterns."""
from django.urls import path
from apps.notifications.views import (
    NotificationListView,
    NotificationUnreadCountView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    NotificationDeleteView,
    NotificationClearAllView,
)

app_name = 'notifications'

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('<uuid:pk>/read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('read-all/', NotificationMarkAllReadView.as_view(), name='notification-read-all'),
    path('clear-all/', NotificationClearAllView.as_view(), name='notification-clear-all'),
    path('<uuid:pk>/', NotificationDeleteView.as_view(), name='notification-delete'),
]

