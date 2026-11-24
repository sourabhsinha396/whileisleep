import secrets
from dataclasses import dataclass, field

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

from whileisleep.fields import EncryptedJSONField, EncryptedTextField
from whileisleep.folders import workspace_logo


def new_public_key() -> str:
    return "ws_" + secrets.token_urlsafe(12)


def new_identity_secret() -> str:
    return "is_" + secrets.token_urlsafe(32)


class Provider(models.TextChoices):
    """Who answers the AI's calls (apps.agent.providers has a client for each)."""

    OPENAI = "openai", "OpenAI"
    ANTHROPIC = "anthropic", "Anthropic"
    GOOGLE = "google", "Google Gemini"
    OPENROUTER = "openrouter", "OpenRouter"


@dataclass(frozen=True)
class LlmChoice:
    """A model the organization chose, with the key to call it."""

    provider: str
    model: str
    api_key: str = field(repr=False)

    @property
    def label(self) -> str:
        return f"{Provider(self.provider).label} {self.model}"

    @property
    def slug(self) -> str:
        """How a Turn records the model, the way OpenRouter names them: "openai/gpt-..."."""
        return self.model if self.provider == Provider.OPENROUTER else f"{self.provider}/{self.model}"


class Organization(models.Model):
    """The account that owns workspaces and pays for the LLM. Its owner sets the provider keys,
    the model and its fallback in the dashboard; every workspace's bot uses them."""

    name = models.CharField(max_length=120)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organization")
    # {"openai": "sk-..."}, a key per provider. Secret: encrypted in the database, and the API
    # never returns one, only whether it is set and its last characters.
    provider_keys = EncryptedJSONField(blank=True)
    # The model that answers: the provider's own id for it. It must support tool calling.
    llm_provider = models.CharField(max_length=20, choices=Provider, default=Provider.OPENROUTER)
    llm_model = models.CharField(max_length=200, blank=True)
    # The model that takes over a reply when that one fails (apps.agent.llm). Empty: none.
    fallback_provider = models.CharField(max_length=20, choices=Provider, blank=True)
    fallback_model = models.CharField(max_length=200, blank=True)
    # AI replies a day in all workspaces together, besides each workspace's own caps. Empty: no cap.
    ai_replies_per_day = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def llm_choices(self) -> list[LlmChoice]:
        """The models that can be called, in the order to ask them: the main one, then the
        fallback. One without a key or a model is left out."""
        chosen = ((self.llm_provider, self.llm_model), (self.fallback_provider, self.fallback_model))
        return [
            LlmChoice(provider, model, self.provider_keys[provider])
            for provider, model in chosen
            if model and self.provider_keys.get(provider)
        ]

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_choices)

    def key_hint(self, provider: str) -> str:
        key = self.provider_keys.get(provider, "")
        return f"…{key[-4:]}" if len(key) > 8 else ""

    @property
    def storage_bucket(self) -> "Bucket | None":
        """The bucket the organization connected, if any."""
        return getattr(self, "bucket", None)


class Bucket(models.Model):
    """An organization's own S3-compatible bucket: where its articles' images and its
    chats' files are (apps.workspaces.buckets)."""

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="bucket")
    endpoint_url = models.CharField(max_length=300)
    region = models.CharField(max_length=40, default="auto")
    bucket = models.CharField(max_length=63)
    # Secret: encrypted in the database, and the API never returns them.
    access_key_id = EncryptedTextField()
    secret_access_key = EncryptedTextField()
    # Where anyone can read the files: the bucket's public address, or a CDN in front of it.
    public_base_url = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bucket} of {self.organization}"

    @property
    def key_hint(self) -> str:
        key = self.access_key_id
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


class WidgetBackground(models.TextChoices):
    """The pattern on the widget's header. The widget draws it (frontend/src/lib/patterns.ts)."""

    PLAIN = "plain"
    BUBBLES = "bubbles"
    CONFETTI = "confetti"
    CHAT = "chat"
    NIGHT = "night"
    STARS = "stars"
    LEAVES = "leaves"
    PETALS = "petals"
    WAVES = "waves"
    HEXAGONS = "hexagons"
    TRIANGLES = "triangles"
    DIAMONDS = "diamonds"
    CIRCUIT = "circuit"


class ColorMode(models.TextChoices):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"  # what the visitor's device is set to


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
    background = models.CharField(
        max_length=16, choices=WidgetBackground, default=WidgetBackground.PLAIN, db_default=WidgetBackground.PLAIN
    )
    color_mode = models.CharField(max_length=8, choices=ColorMode, default=ColorMode.LIGHT, db_default=ColorMode.LIGHT)
    # Shown in the widget's header instead of the workspace's initials.
    logo = models.FileField(upload_to=workspace_logo, max_length=200, blank=True)
    greeting = models.CharField(max_length=300, default="Hi! How can we help?")
    # An IANA name ("Europe/Berlin"). Rules read the local hour and weekday in it.
    timezone = models.CharField(max_length=64, default="UTC")
    ai_enabled = models.BooleanField(default=True)
    # Extra instructions for the AI agent: tone, scope, product facts.
    ai_instructions = models.TextField(blank=True)
    # Past either one, the chat goes to the team. They cap what the organization's LLM key is charged.
    ai_replies_per_visitor = models.PositiveIntegerField(default=50, db_default=50)
    ai_replies_per_day = models.PositiveIntegerField(default=2000, db_default=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self.name, self.pk)
        super().save(*args, **kwargs)

    @property
    def logo_url(self) -> str:
        return self.logo.url if self.logo else ""


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
