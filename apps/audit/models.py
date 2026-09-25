"""System Audit Logging and Compliance Models."""
from django.db import models
from django.conf import settings

class AuditLog(models.Model):
    """Immutable audit ledger for administrative operations and security state changes.
    
    Data Minimization Rule: Never store passwords, raw JWT tokens, invitation tokens,
    clinical notes, diagnoses, or unnecessary patient PII.
    """
    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions'
    )
    action = models.CharField(max_length=64, db_index=True)
    target_model = models.CharField(max_length=64)
    target_id = models.CharField(max_length=64)
    change_summary = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'meetadr_audit_logs'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-created_at']

    def __str__(self):
        actor_email = self.actor.email if self.actor else 'System'
        return f"[{self.created_at}] {actor_email} -> {self.action} on {self.target_model}:{self.target_id}"
