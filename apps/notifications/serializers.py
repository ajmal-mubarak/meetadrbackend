"""User Notifications Serializers."""
from rest_framework import serializers
from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer mapping Notification model to frontend PatientNotification contract."""
    notificationType = serializers.CharField(source='notification_type', read_only=True)
    type = serializers.CharField(source='notification_type', read_only=True)
    isRead = serializers.BooleanField(source='is_read', read_only=True)
    unread = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', format='iso-8601', read_only=True)
    time = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id',
            'title',
            'description',
            'notificationType',
            'type',
            'link',
            'isRead',
            'unread',
            'createdAt',
            'time',
        ]
        read_only_fields = fields

    def get_unread(self, obj) -> bool:
        return not obj.is_read

    def get_time(self, obj) -> str:
        return obj.created_at.isoformat()
