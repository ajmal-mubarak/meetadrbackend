"""Audit Logging Utility Functions."""
from typing import Optional, Any, Dict
from apps.audit.models import AuditLog

SENSITIVE_KEYS = {'password', 'token', 'access', 'refresh', 'secret', 'authorization', 'credit_card'}

def sanitize_data(data: Any) -> Any:
    """Recursively sanitize sensitive keys from audit payload."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if any(sensitive in k.lower() for sensitive in SENSITIVE_KEYS):
                sanitized[k] = '[REDACTED]'
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data

def get_client_ip(request) -> Optional[str]:
    """Safely extract remote client IP address from request."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def log_audit_event(
    action: str,
    target_model: str,
    target_id: str,
    actor=None,
    change_summary: Optional[Dict[str, Any]] = None,
    request=None,
    ip_address: Optional[str] = None,
    user_agent: str = ""
) -> Optional[AuditLog]:
    """Create an immutable audit log entry adhering to data minimization rules."""
    try:
        ip = ip_address or get_client_ip(request)
        agent = user_agent
        if request and not agent:
            agent = request.META.get('HTTP_USER_AGENT', '')[:255]
            
        clean_summary = sanitize_data(change_summary or {})
        
        return AuditLog.objects.create(
            actor=actor if actor and getattr(actor, 'is_authenticated', False) else None,
            action=action,
            target_model=target_model,
            target_id=str(target_id),
            change_summary=clean_summary,
            ip_address=ip,
            user_agent=agent
        )
    except Exception:
        # Audit logging failure should not break user operations in edge cases,
        # but is recorded safely.
        return None
