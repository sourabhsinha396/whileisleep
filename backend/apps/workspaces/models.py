import secrets

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

from whileisleep.fields import EncryptedTextField


def new_public_key() -> str:
    return "ws_" + secrets.token_urlsafe(12)


def new_identity_secret() -> str:
    return "is_" + secrets.token_urlsafe(32)


class Organization(models.Model):
    """The account that owns workspaces and pays for the LLM. Its owner sets the OpenRouter key
    and model in the dashboard; every workspace in the organization's bot uses them."""

    name = models.CharField(max_length=120)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization")
    # Secret: encrypted in the database, and the API never returns it, only whether it is set
    # and its last characters.
    openrouter_api_key = EncryptedTextField(blank=True)
    # An OpenRouter model id (see openrouter.ai/models) that supports tool calling.
    llm_model = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def llm_ready(self) -> bool:
        return bool(self.openrouter_api_key and self.llm_model)

    @property
    def key_hint(self) -> str:
        key = self.openrouter_api_key
        return f"…{key[-4:]}" if len(key) > 8 else ""


workspace_slug = RegexValidator(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "Lowercase letters and digits, with single hyphens between words."
)
MAX_SLUG = 60


def unique_slug(name: str, exclude_pk: int | None = None) -> str:
    """A slug for `name` that no other workspace has: "examgrill", then "examgrill-2"..."""
    base = slugify(name)[: MAX_SLUG - 6].strip("-") or "workspace"
    slug, number = base, 2
    while Workspace.objects.filter(slug=slug).exclude(pk=exclude_pk).exists():
        slug = f"{base}-{number}"
        number += 1
    return slug


class Workspace(models.Model):
    """One website or product. Visitors, conversations and articles belong to a workspace."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="workspaces")
    name = models.CharField(max_length=120)
    # How the workspace appears in dashboard URLs: /w/examgrill/inbox. Made from the name
    # when left empty; owners can change it.
    slug = models.SlugField(max_length=MAX_SLUG, unique=True, blank=True, validators=[workspace_slug])
    # Goes in the widget snippet on the customer's site, so it is public.
    public_key = models.CharField(max_length=64, unique=True, default=new_public_key)
    website = models.URLField(blank=True)
    # The site's server signs identity tokens with this (apps.conversations.identity). Shown
    # to owners only, and encrypted in the database.
    identity_secret = EncryptedTextField(default=new_identity_secret)
    color = models.CharField(max_length=16, default="#2563eb")
    greeting = models.CharField(max_length=300, default="Hi! How can we help?")
    # An IANA name ("Europe/Berlin"). Rules read the local hour and weekday in it.
    timezone = models.CharField(max_length=64, default="UTC")
    ai_enabled = models.BooleanField(default=True)
    # Extra instructions for the AI agent: tone, scope, product facts.
    ai_instructions = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self.name, self.pk)
        super().save(*args, **kwargs)


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner"
        AGENT = "agent"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AGENT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "workspace"], name="one_membership_per_workspace")]

    def __str__(self):
        return f"{self.user} in {self.workspace} ({self.role})"
