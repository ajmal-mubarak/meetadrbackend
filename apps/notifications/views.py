"""User Notifications Views."""
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


class NotificationPagination(PageNumberPagination):
    """Page-number pagination for user notifications."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


class NotificationListView(ListAPIView):
    """
    Lists the authenticated user's notifications.
    Strictly scoped to request.user.
    Supports ?unread=true filtering.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        unread_param = self.request.query_params.get('unread')
        if unread_param and unread_param.lower() in ('true', '1'):
            qs = qs.filter(is_read=False)
        return qs.order_by('-created_at')


class NotificationUnreadCountView(APIView):
    """
    Returns the real-time unread notification count for the authenticated user.
    Executes a single direct SQL COUNT query without instantiating model rows.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'unreadCount': count}, status=status.HTTP_200_OK)


class NotificationMarkReadView(APIView):
    """
    Marks a single notification as read for the authenticated user.
    Strictly scoped to request.user; another user's UUID returns 404.
    Operation is idempotent.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        notification = get_object_or_404(Notification, id=pk, user=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        serializer = NotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationMarkAllReadView(APIView):
    """
    Bulk marks all unread notifications as read for the authenticated user.
    Executes an atomic database UPDATE without affecting other users.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True)

        return Response(
            {
                'markedReadCount': updated_count,
                'unreadCount': 0
            },
            status=status.HTTP_200_OK
        )
