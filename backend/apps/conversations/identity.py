"""Signed identity: how a website proves which of its users is in the chat.

Anything the page's JavaScript says (identify({email})) can be typed into a browser console,
so it can't be trusted to decide whose data a tool returns. A site that wants that trust
has its *server* sign a short-lived token with the workspace's identity secret:

    jwt.encode({"sub": user.id, "email": user.email, "plan": "pro", "exp": now + 1h},
               WHILEISLEEP_IDENTITY_SECRET, algorithm="HS256")

and the page passes it on: window.whileisleep.identify({token}). The widget sends it with
the session request; here we check it and

- tie the visitor to `sub` (the site's own user id), so the same person on another device
  or browser gets the same conversations, and
- store every other claim as an attribute with Source.VERIFIED.
"""

import jwt
from django.db import transaction
from django.utils import timezone

from apps.workspaces.models import Workspace

from . import attributes
from .models import Visitor

# Part of the token format, not facts about the user.
RESERVED_CLAIMS = {"sub", "exp", "iat", "nbf", "iss", "aud", "jti"}
# Seconds of clock difference between the site's server and ours that we forgive.
LEEWAY_SECONDS = 30
MAX_EXTERNAL_ID_CHARS = 200


class IdentityError(Exception):
    """The token can't be trusted. The message is safe to return to the page."""


def verify(workspace: Workspace, token: str) -> dict:
    """The token's claims, if this workspace's secret signed it and it hasn't expired."""
    try:
        claims = jwt.decode(
            token,
            workspace.identity_secret,
            # Fixed: a token can't pick a weaker algorithm (or "none") for itself.
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
            leeway=LEEWAY_SECONDS,
        )
    except jwt.ExpiredSignatureError as error:
        raise IdentityError("The identity token has expired. Sign a new one on each page load.") from error
    except jwt.PyJWTError as error:
        raise IdentityError("The identity token isn't valid for this workspace.") from error
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise IdentityError("The identity token needs a `sub` claim: your user's id.")
    claims["sub"] = subject.strip()[:MAX_EXTERNAL_ID_CHARS]
    return claims


@transaction.atomic
def sign_in(workspace: Workspace, current: Visitor | None, claims: dict) -> Visitor:
    """The visitor for a verified user, taking over from the browser's anonymous one.

    `current` is the visitor this browser had until now (None for a fresh browser). If the
    user is already known from elsewhere, an anonymous `current` is folded into that record:
    its conversations move over and it is deleted.
    """
    external_id = claims["sub"]
    known = Visitor.objects.select_for_update().filter(workspace=workspace, external_id=external_id).first()
    if known is None:
        if current is not None and not current.external_id:
            visitor = current
        else:
            # A fresh browser, or one still holding another signed-in user's visitor.
            visitor = Visitor(workspace=workspace, ip=current.ip if current else None)
        visitor.external_id = external_id
    else:
        visitor = known
        if current is not None and current.pk != known.pk and not current.external_id:
            current.conversations.update(visitor=known)
            current.delete()
    visitor.verified_at = timezone.now()
    visitor.save()
    facts = {key: value for key, value in claims.items() if key not in RESERVED_CLAIMS}
    attributes.set_many(visitor, facts, attributes.Source.VERIFIED)
    return visitor
