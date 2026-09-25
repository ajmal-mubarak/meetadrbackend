"""Provider Onboarding Application and Invitation Token Models."""
import uuid
from django.db import models
from django.conf import settings

class ProviderType(models.TextChoices):
    HOSPITAL = 'hospital', 'Hospital'
    CLINIC = 'clinic', 'Clinic'

class RequestStatus(models.TextChoices):
    PENDING = 'pending', 'Pending Review'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'

class ProviderRequest(models.Model):
    """External partnership application submitted by a healthcare facility."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider_type = models.CharField(
        max_length=16,
        choices=ProviderType.choices,
        db_index=True
    )
    name = models.CharField(max_length=255)
    name_ar = models.CharField(max_length=255, blank=True)
    contact_person = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=32)
    email = models.EmailField()
    country = models.CharField(max_length=64, default='United Arab Emirates')
    location = models.CharField(max_length=128)
    address = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=RequestStatus.choices,
        default=RequestStatus.PENDING,
        db_index=True
    )
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_provider_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meetadr_provider_requests'
        verbose_name = 'Provider Request'
        verbose_name_plural = 'Provider Requests'

    def __str__(self):
        return f"{self.name} ({self.provider_type}) - {self.status}"

class ProviderInvitationToken(models.Model):
    """Cryptographic single-use token for newly provisioned facility administrators."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='invitation_token'
    )
    token_hash = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'meetadr_provider_invitation_tokens'
        verbose_name = 'Provider Invitation Token'
        verbose_name_plural = 'Provider Invitation Tokens'

    def __str__(self):
        return f"Invite Token for {self.user.email} (Used: {self.is_used})"
