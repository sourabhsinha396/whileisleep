import secrets

from django.conf import settings
from django.db import models

from whileisleep.folders import user_photo


def new_token() -> str:
    return "at_" + secrets.token_urlsafe(24)


class AuthToken(models.Model):
    """Bearer token for the dashboard. One per login; deleting it logs that session out."""

    key = models.CharField(max_length=64, unique=True, default=new_token)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_tokens")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"token for {self.user}"


class Profile(models.Model):
    """What we keep about a person beyond Django's user. Made on first use, so it may be absent."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    # Visitors see it next to this person's replies, in every workspace they belong to.
    photo = models.FileField(upload_to=user_photo, max_length=200, blank=True)

    def __str__(self):
        return f"profile of {self.user}"


def photo_url(user) -> str:
    """Load `profile` with select_related before calling this for many users."""
    profile = getattr(user, "profile", None)
    return profile.photo.url if profile and profile.photo else ""
