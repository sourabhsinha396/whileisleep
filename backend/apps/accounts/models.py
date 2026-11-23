import secrets

from django.conf import settings
from django.db import models


def new_token() -> str:
    return "at_" + secrets.token_urlsafe(24)


class AuthToken(models.Model):
    """Bearer token for the dashboard. One per login; deleting it logs that session out."""

    key = models.CharField(max_length=64, unique=True, default=new_token)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_tokens")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"token for {self.user}"
