"""User Notifications Models."""
import uuid
from django.db import models
from django.conf import settings

class NotificationType(models.TextChoices):
    APPOINTMENT = 'appointment', 'Appointment'
    PRESCRIPTION = 'prescription', 'Prescription'
    REMINDER = 'reminder', 'Reminder'
    SYSTEM = 'system', 'System'

class Notification(models.Model):
    """User in-app notification message."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    notification_type = models.CharField(
        max_length=32,
        choices=NotificationType.choices,
        default=NotificationType.APPOINTMENT
    )
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meetadr_notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.email}: {self.title}"
