"""An organization's own bucket: connecting it, and article images that go there. Requests run
through real httpx and stop at the socket, where a bucket in memory answers (fake_s3)."""

import re

import httpx
import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.knowledge.models import Article, ArticleImage
from apps.workspaces import buckets
from apps.workspaces.models import Bucket, Membership
from whileisleep import outbound

from .conftest import Api
from .factories import ArticleFactory, AuthTokenFactory, MembershipFactory
from .fake_s3 import ENDPOINT, PUBLIC, SETTINGS
from .test_encryption import raw
from .test_images import picture

pytestmark = pytest.mark.django_db


@pytest.fixture
def article(workspace):
    return ArticleFactory(workspace=workspace)


def connect(api, **changes):
    return api.put("/organization/storage", SETTINGS | changes)


def upload(api, article):
    return api.upload(f"/workspaces/{article.workspace_id}/articles/{article.id}/images", picture())


# --- Connecting ---


def test_not_connected_at_first(api):
    assert api.get("/organization/storage").json()["connected"] is False


def test_connecting_tries_the_bucket_first(api, s3, workspace):
    body = connect(api).json()
    assert [method for method, _ in s3.requests] == ["PUT", "GET", "DELETE"]
    assert s3.files == {}
    assert body == {
        "connected": True,
        "endpoint_url": ENDPOINT,
        "region": "auto",
        "bucket": "acme-uploads",
        "key_hint": "…MPLE",
        "public_base_url": PUBLIC,
        "image_count": 0,
    }
    assert api.get("/organization/storage").json() == body


def test_the_key_is_write_only_and_encrypted(api, connected):
    shown = str(api.get("/organization/storage").json())
    assert "customer-secret" not in shown and "AKIDEXAMPLE" not in shown
    bucket = Bucket.objects.get()
    for column, value in (("secret_access_key", "customer-secret"), ("access_key_id", "AKIDEXAMPLE")):
        assert value not in raw("workspaces_bucket", column, bucket.pk)


@pytest.mark.parametrize(
    "answers, message",
    [
        ({"PUT": 403}, "may not store files in acme-uploads"),
        ({"PUT": 404}, "no bucket called acme-uploads"),
        ({"PUT": 301}, "region is probably wrong"),
        ({"PUT": 500}, "answered 500"),
        ({"DELETE": 403}, "may not delete files from acme-uploads"),
    ],
)
def test_a_bucket_that_does_not_work_is_not_saved(api, s3, answers, message):
    s3.answers = answers
    response = connect(api)
    assert response.status_code == 400 and message in response.json()["detail"]
    # What the bucket answered stays on the server.
    assert "internal details" not in response.json()["detail"]
    assert not Bucket.objects.exists()


def test_a_wrong_secret_is_refused(api, s3):
    response = connect(api, secret_access_key="wrong")
    assert response.status_code == 400 and "Check the key" in response.json()["detail"]


def test_a_private_bucket_is_refused_and_left_clean(api, s3):
    s3.public = False
    response = connect(api)
    assert response.status_code == 400 and "Turn on public access" in response.json()["detail"]
    assert s3.files == {}


def test_an_unreachable_endpoint(api, s3, monkeypatch):
    def down(self, request):
        raise httpx.ConnectTimeout("timed out", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", down)
    response = connect(api)
    assert response.status_code == 400 and "can't be reached" in response.json()["detail"]


@pytest.mark.parametrize("address", ["169.254.169.254", "127.0.0.1", "172.17.0.1"])
def test_our_own_network_is_out_of_reach(api, s3, monkeypatch, address):
    monkeypatch.setattr(outbound, "resolve", lambda host, port: [address])
    response = connect(api)
    assert response.status_code == 400 and "private network" in response.json()["detail"]
    assert s3.requests == []


def test_a_private_public_address_is_not_fetched(api, s3, monkeypatch):
    resolve = {"account.r2.example.com": ["93.184.216.34"], "files.example.com": ["10.0.0.5"]}
    monkeypatch.setattr(outbound, "resolve", lambda host, port: resolve[host])
    assert connect(api).status_code == 400
    assert "GET" not in [method for method, _ in s3.requests]


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"endpoint_url": "account.r2.example.com"}, "The endpoint must be a full address"),
        ({"endpoint_url": "http://account.r2.example.com"}, "The endpoint must be a full address"),
        ({"endpoint_url": "https://user:pw@account.r2.example.com"}, "The endpoint must be a full address"),
        ({"endpoint_url": "https://account.r2.example.com:port"}, "The endpoint must be a full address"),
        ({"endpoint_url": "https://account.r2.example.com/a/b"}, "without a folder"),
        ({"public_base_url": "javascript:alert(1)"}, "The public address must be a full address"),
        ({"public_base_url": "https://files.example.com/)![x](https://evil"}, "The public address must be"),
        ({"bucket": "Acme Uploads"}, "isn't a bucket name"),
        ({"bucket": "../other"}, "isn't a bucket name"),
        ({"region": "eu central/1"}, "isn't a region"),
        ({"secret_access_key": ""}, "Enter both"),
        ({"access_key_id": "", "secret_access_key": ""}, "Enter both"),
    ],
)
def test_mistakes_are_named_before_anything_is_sent(api, s3, changes, message):
    response = connect(api, **changes)
    assert response.status_code == 400 and message in response.json()["detail"]
    assert s3.requests == []


def test_an_endpoint_with_the_bucket_on_the_end_is_understood(api, s3):
    """Cloudflare's dashboard shows it that way."""
    assert connect(api, endpoint_url=f"{ENDPOINT}/acme-uploads/").json()["endpoint_url"] == ENDPOINT


def test_http_is_for_private_networks(api, settings):
    settings.OUTBOUND_ALLOW_PRIVATE_NETWORKS = True
    assert buckets.clean_address("http://minio:9000", "The endpoint") == "http://minio:9000"


# --- Changing and disconnecting ---


def test_the_saved_key_is_kept_when_left_empty(api, connected):
    response = connect(api, access_key_id="", secret_access_key="", region="weur")
    assert response.status_code == 200
    bucket = Bucket.objects.get()
    assert (bucket.region, bucket.secret_access_key) == ("weur", "customer-secret")


def test_the_saved_key_never_goes_to_another_endpoint(api, connected):
    response = connect(api, endpoint_url="https://evil.example.com", access_key_id="", secret_access_key="")
    assert response.status_code == 400 and "The endpoint changed" in response.json()["detail"]
    assert connected.requests == []


def test_a_failed_change_keeps_the_working_bucket(api, connected):
    assert connect(api, secret_access_key="wrong").status_code == 400
    assert Bucket.objects.get().secret_access_key == "customer-secret"


def test_the_same_bucket_keeps_its_images_and_another_does_not(api, connected, article, monkeypatch):
    upload(api, article)
    first = Bucket.objects.get()
    connect(api, region="weur")
    assert ArticleImage.objects.get().bucket == first
    monkeypatch.setitem(SETTINGS, "bucket", "other-uploads")
    assert connect(api).status_code == 200
    assert ArticleImage.objects.get().bucket is None
    assert api.get("/organization/storage").json()["image_count"] == 0


def test_disconnecting_leaves_the_files_alone(api, connected, article):
    url = upload(api, article).json()["url"]
    assert api.delete("/organization/storage").json()["connected"] is False
    assert len(connected.files) == 1
    # Not ours to delete any more.
    api.delete(f"/workspaces/{article.workspace_id}/articles/{article.id}")
    assert [f"{PUBLIC}/{name}" for name in connected.files] == [url]


def test_agents_reach_only_their_own_organization(workspace, connected):
    agent = MembershipFactory(workspace=workspace, role=Membership.Role.AGENT).user
    as_agent = Api(token=AuthTokenFactory(user=agent).key)
    assert as_agent.get("/organization/storage").json()["connected"] is False
    as_agent.delete("/organization/storage")
    assert Bucket.objects.filter(organization=workspace.organization).exists()
    assert Api().get("/organization/storage").status_code == 401


# --- Article images ---


def test_images_go_to_the_customers_bucket(api, connected, article):
    url = upload(api, article).json()["url"]
    folder = f"whileisleep/workspaces/{article.workspace_id}/articles/{article.id}"
    assert re.fullmatch(rf"{PUBLIC}/{folder}/[0-9a-f]{{32}}\.png", url)
    (name,) = connected.files
    assert url == f"{PUBLIC}/{name}"
    assert connected.headers[name]["content-type"] == "image/png"
    assert "immutable" in connected.headers[name]["cache-control"]
    # Nothing in ours.
    assert not default_storage.exists(ArticleImage.objects.get().file.name)
    assert api.get("/organization/storage").json()["image_count"] == 1


def test_teammates_upload_to_it_too(workspace, connected, article):
    agent = MembershipFactory(workspace=workspace, role=Membership.Role.AGENT).user
    assert upload(Api(token=AuthTokenFactory(user=agent).key), article).json()["url"].startswith(PUBLIC)


def test_without_a_bucket_articles_are_text(api, s3, article):
    response = upload(api, article)
    assert response.status_code == 409 and "Connect your storage" in response.json()["detail"]
    assert s3.requests == [] and not ArticleImage.objects.exists()
    path = f"/workspaces/{article.workspace_id}/articles"
    assert api.post(path, {"title": "Shipping", "body": "Three days."}).status_code == 200


def test_the_dashboard_knows_whether_articles_can_have_images(api, s3, workspace, settings):
    def enabled():
        one, listed = api.get(f"/workspaces/{workspace.id}").json(), api.get("/workspaces").json()[0]
        assert one["article_uploads_enabled"] == listed["article_uploads_enabled"]
        return one["article_uploads_enabled"]

    assert enabled() is False
    connect(api)
    assert enabled() is True
    # Whether the server has storage of its own makes no difference.
    settings.UPLOADS_ENABLED = False
    assert enabled() is True
    api.delete("/organization/storage")
    assert enabled() is False


def test_a_broken_bucket_fails_the_upload_and_does_not_use_ours(api, connected, article):
    connected.answers = {"PUT": 403}
    response = upload(api, article)
    assert response.status_code == 502 and "may not store files" in response.json()["detail"]
    assert not ArticleImage.objects.exists()


def test_bad_images_never_reach_it(api, connected, article):
    path = f"/workspaces/{article.workspace_id}/articles/{article.id}/images"
    assert api.upload(path, picture("GIF")).status_code == 400
    assert connected.requests == []


def test_images_from_before_are_still_deleted_from_our_storage(api, connected, article):
    old = ArticleImage.objects.create(article=article, file=ContentFile(b"old", name="old.png"))
    assert old.hosted and default_storage.exists(old.file.name)
    api.delete(f"/workspaces/{article.workspace_id}/articles/{article.id}")
    assert not default_storage.exists(old.file.name)
    assert connected.requests == []


def test_a_copied_image_survives_its_article(api, connected, article):
    url = upload(api, article).json()["url"]
    ArticleFactory(workspace=article.workspace, body=f"![x]({url})")
    api.delete(f"/workspaces/{article.workspace_id}/articles/{article.id}")
    assert len(connected.files) == 1


def test_a_bucket_that_is_down_does_not_stop_an_article_being_deleted(api, connected, article):
    upload(api, article)
    connected.answers = {"DELETE": 500}
    assert api.delete(f"/workspaces/{article.workspace_id}/articles/{article.id}").status_code == 200
    assert not Article.objects.filter(pk=article.pk).exists()


def test_the_guide_counts_a_connected_bucket(api, connected, workspace):
    steps = api.get(f"/workspaces/{workspace.id}/setup").json()
    assert {"key": "storage", "done": True} in steps
