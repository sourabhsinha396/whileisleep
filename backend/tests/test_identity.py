"""Signed identity tokens: the host site's server vouches for who is in the chat."""

from datetime import timedelta

import jwt
import pytest
from django.utils import timezone

from apps.conversations import attributes, identity
from apps.conversations.attributes import Source
from apps.conversations.models import Conversation, Visitor

from .conftest import Api
from .factories import AuthTokenFactory, ConversationFactory, MembershipFactory, VisitorFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db


def token_for(workspace, secret=None, algorithm="HS256", expires_in=3600, **claims):
    """What the site's server would produce for its signed-in user."""
    payload = {"sub": "user_42", "exp": timezone.now() + timedelta(seconds=expires_in)} | claims
    payload = {key: value for key, value in payload.items() if value is not None}
    return jwt.encode(payload, secret or workspace.identity_secret, algorithm=algorithm)


def session(workspace, visitor_token="", **body):
    return Api(visitor_token=visitor_token).post(f"/widget/{workspace.public_key}/session", body)


# --- Checking the token ---


def test_a_valid_token_yields_its_claims():
    workspace = WorkspaceFactory()
    claims = identity.verify(workspace, token_for(workspace, email="sofia@example.com"))
    assert claims["sub"] == "user_42" and claims["email"] == "sofia@example.com"


def test_numeric_user_ids_are_accepted():
    # PyJWT refuses a non-string `sub`, so sites with integer ids send it as a string.
    workspace = WorkspaceFactory()
    assert identity.verify(workspace, token_for(workspace, sub="42"))["sub"] == "42"


@pytest.mark.parametrize(
    "make",
    [
        lambda w: token_for(w, secret="some-other-secret-that-is-long-enough-1234"),  # not signed by us
        lambda w: token_for(w, expires_in=-3600),  # expired
        lambda w: token_for(w, sub=None),  # nobody named
        lambda w: token_for(w, sub="   "),
        lambda w: token_for(w, exp=None),  # would never expire
        lambda w: token_for(w, secret="x" * 64, algorithm="HS512"),  # not the algorithm we accept
        lambda w: jwt.encode({"sub": "user_42", "exp": 9999999999}, "", algorithm="none"),  # unsigned
        lambda w: "not.a.token",
        lambda w: token_for(w)[:-4] + "AAAA",  # tampered signature
    ],
)
def test_untrustworthy_tokens_are_refused(make):
    workspace = WorkspaceFactory()
    with pytest.raises(identity.IdentityError):
        identity.verify(workspace, make(workspace))


def test_another_workspaces_token_is_refused():
    workspace, other = WorkspaceFactory(), WorkspaceFactory()
    with pytest.raises(identity.IdentityError):
        identity.verify(workspace, token_for(other))


def test_a_changed_payload_breaks_the_signature():
    workspace = WorkspaceFactory()
    header, _, signature = token_for(workspace, email="me@example.com").split(".")
    forged_payload = token_for(workspace, secret="attacker-secret-attacker-secret-1234", email="victim@example.com")
    forged = ".".join([header, forged_payload.split(".")[1], signature])
    with pytest.raises(identity.IdentityError):
        identity.verify(workspace, forged)


# --- Signing in through the widget ---


def test_identity_token_verifies_the_visitor_and_its_claims():
    workspace = WorkspaceFactory()
    response = session(workspace, identity_token=token_for(workspace, email="Sofia@Example.com", plan="pro"))
    assert response.status_code == 200
    visitor = Visitor.objects.get()
    assert visitor.external_id == "user_42" and visitor.is_verified
    assert visitor.email == "sofia@example.com"
    assert attributes.is_verified(visitor, "email") and attributes.is_verified(visitor, "plan")
    # Token bookkeeping isn't a fact about the user.
    assert not {"sub", "exp"} & set(visitor.attributes)


def test_a_bad_token_is_rejected_loudly():
    workspace = WorkspaceFactory()
    response = session(workspace, identity_token=token_for(workspace, secret="wrong-secret-wrong-secret-wrong-12"))
    assert response.status_code == 401
    assert Visitor.objects.count() == 0


def test_the_anonymous_visitor_becomes_the_signed_in_one():
    workspace = WorkspaceFactory()
    anonymous = session(workspace).json()["token"]
    conversation = ConversationFactory(workspace=workspace, visitor=Visitor.objects.get())
    signed_in = session(workspace, anonymous, identity_token=token_for(workspace)).json()
    # Same record, so the chat they started before signing in is still theirs.
    assert signed_in["token"] == anonymous
    assert signed_in["conversation_id"] == conversation.id
    assert Visitor.objects.get().external_id == "user_42"


def test_the_same_user_on_another_device_gets_the_same_visitor():
    workspace = WorkspaceFactory()
    laptop = session(workspace, identity_token=token_for(workspace)).json()
    conversation = ConversationFactory(workspace=workspace, visitor=Visitor.objects.get())
    phone = session(workspace, identity_token=token_for(workspace)).json()
    assert phone["token"] == laptop["token"]
    assert phone["conversation_id"] == conversation.id
    assert Visitor.objects.count() == 1


def test_an_anonymous_chat_is_folded_into_the_known_user():
    workspace = WorkspaceFactory()
    known = session(workspace, identity_token=token_for(workspace)).json()["token"]
    # Later, on a new browser, they chat before signing in.
    anonymous = session(workspace).json()["token"]
    stray = Visitor.objects.get(token=anonymous)
    conversation = ConversationFactory(workspace=workspace, visitor=stray)

    merged = session(workspace, anonymous, identity_token=token_for(workspace)).json()

    assert merged["token"] == known
    assert not Visitor.objects.filter(pk=stray.pk).exists()
    assert Conversation.objects.get(pk=conversation.pk).visitor.token == known


def test_a_second_user_on_the_same_browser_does_not_inherit_the_first():
    workspace = WorkspaceFactory()
    first = session(workspace, identity_token=token_for(workspace, sub="alice")).json()["token"]
    ConversationFactory(workspace=workspace, visitor=Visitor.objects.get(token=first))
    # The site forgot to call reset() on sign-out, then Bob signs in.
    second = session(workspace, first, identity_token=token_for(workspace, sub="bob")).json()
    assert second["token"] != first
    assert second["conversation_id"] is None
    assert Visitor.objects.get(external_id="alice").conversations.count() == 1


def test_the_same_user_id_in_two_workspaces_is_two_visitors():
    one, two = WorkspaceFactory(), WorkspaceFactory()
    session(one, identity_token=token_for(one))
    session(two, identity_token=token_for(two))
    assert Visitor.objects.filter(external_id="user_42").count() == 2


def test_unsigned_identify_cannot_replace_verified_claims():
    workspace = WorkspaceFactory()
    token = session(workspace, identity_token=token_for(workspace, email="real@example.com")).json()["token"]
    # Someone edits the page's JavaScript to claim another address.
    session(workspace, token, email="victim@example.com")
    visitor = Visitor.objects.get()
    assert visitor.email == "real@example.com"
    assert attributes.source_of(visitor, "email") == Source.VERIFIED


def test_unsigned_identify_never_marks_a_visitor_verified():
    workspace = WorkspaceFactory()
    session(workspace, email="sofia@example.com")
    assert not Visitor.objects.get().is_verified


# --- The secret ---


def test_each_workspace_has_its_own_secret():
    assert WorkspaceFactory().identity_secret != WorkspaceFactory().identity_secret


def test_owner_can_read_and_rotate_the_secret(api, workspace):
    shown = api.get(f"/workspaces/{workspace.id}/identity-secret").json()["secret"]
    assert shown == workspace.identity_secret
    old_token = token_for(workspace)

    rotated = api.post(f"/workspaces/{workspace.id}/identity-secret/rotate").json()["secret"]

    assert rotated != shown
    workspace.refresh_from_db()
    assert session(workspace, identity_token=old_token).status_code == 401
    assert session(workspace, identity_token=token_for(workspace)).status_code == 200


def test_agents_cannot_read_the_secret(workspace):
    agent = MembershipFactory(workspace=workspace, role="agent")
    as_agent = Api(token=AuthTokenFactory(user=agent.user).key)
    assert as_agent.get(f"/workspaces/{workspace.id}/identity-secret").status_code == 404
    assert as_agent.post(f"/workspaces/{workspace.id}/identity-secret/rotate").status_code == 404


def test_the_secret_is_not_in_ordinary_workspace_responses(api, workspace):
    assert workspace.identity_secret not in str(api.get(f"/workspaces/{workspace.id}").json())
    assert workspace.identity_secret not in str(api.get("/workspaces").json())
    assert workspace.identity_secret not in str(Api().get(f"/widget/{workspace.public_key}/config").json())


def test_inbox_shows_whether_a_visitor_is_verified(api, workspace):
    session(workspace, identity_token=token_for(workspace))
    ConversationFactory(workspace=workspace, visitor=Visitor.objects.get())
    VisitorFactory(workspace=workspace)
    rows = api.get(f"/workspaces/{workspace.id}/visitors").json()
    assert sorted(row["verified"] for row in rows) == [False, True]
