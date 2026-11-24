import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command

from apps.conversations import identity
from apps.docs.models import DocPage
from apps.docs.youtube import video_id

from .conftest import Api
from .factories import AuthTokenFactory, UserFactory, WorkspaceFactory

ID = "dQw4w9WgXcQ"
LINK = f"https://youtu.be/{ID}?si=abc"
PAGE = "/docs/install"
PAGES = Path(__file__).resolve().parents[2] / "frontend" / "content" / "docs"


@pytest.fixture
def superuser():
    return Api(token=AuthTokenFactory(user=UserFactory(is_superuser=True)).key)


@pytest.mark.parametrize(
    "link",
    [
        LINK,
        f"https://www.youtube.com/watch?v={ID}&t=10s",
        f"https://m.youtube.com/watch?app=desktop&v={ID}",
        f"https://youtube.com/shorts/{ID}",
        f"https://www.youtube.com/live/{ID}?feature=share",
        f"https://www.youtube-nocookie.com/embed/{ID}",
        f"  youtube.com/watch?v={ID}  ",
    ],
)
def test_reads_the_id_from_a_link(link):
    assert video_id(link) == ID


@pytest.mark.parametrize(
    "link",
    [
        "",
        "hello",
        ID,
        f"https://evil.com/watch?v={ID}",
        f"https://youtube.com.evil.com/watch?v={ID}",
        f"https://notyoutube.com/watch?v={ID}",
        f"javascript://youtube.com/watch?v={ID}",
        "https://youtube.com/watch?v=short",
        f"https://youtu.be/{ID}x",
        "https://youtube.com/playlist?list=PL1",
        "https://[youtube.com/watch",
    ],
)
def test_refuses_anything_else(link):
    assert video_id(link) is None


@pytest.mark.django_db
def test_anyone_sees_what_was_changed(anon):
    assert anon.get(PAGE).json() == {"body": "", "youtube_id": ""}
    DocPage.objects.create(page="install", body="## New", youtube_id=ID)
    assert anon.get(PAGE).json() == {"body": "## New", "youtube_id": ID}
    assert anon.get("/docs/rules").json() == {"body": "", "youtube_id": ""}


@pytest.mark.django_db
def test_looking_at_a_page_saves_nothing(anon):
    anon.get(PAGE)
    assert not DocPage.objects.exists()


@pytest.mark.django_db
def test_a_superuser_sets_replaces_and_removes_the_video(superuser):
    assert superuser.patch(PAGE, {"video_link": LINK}).json()["youtube_id"] == ID
    other = "abcdefghij_"
    assert superuser.patch(PAGE, {"video_link": f"https://youtu.be/{other}"}).json()["youtube_id"] == other
    assert superuser.patch(PAGE, {"video_link": " "}).json()["youtube_id"] == ""
    assert DocPage.objects.count() == 1


@pytest.mark.django_db
def test_text_and_video_are_changed_apart(superuser):
    superuser.patch(PAGE, {"video_link": LINK})
    assert superuser.patch(PAGE, {"body": "Hello"}).json() == {"body": "Hello", "youtube_id": ID}
    assert superuser.patch(PAGE, {"video_link": ""}).json() == {"body": "Hello", "youtube_id": ""}


@pytest.mark.django_db
def test_an_empty_text_brings_the_original_back(superuser):
    superuser.patch(PAGE, {"body": "Hello"})
    assert superuser.patch(PAGE, {"body": " \n"}).json()["body"] == ""


@pytest.mark.django_db
def test_a_bad_link_changes_nothing(superuser):
    superuser.patch(PAGE, {"video_link": LINK})
    assert superuser.patch(PAGE, {"video_link": "https://vimeo.com/1", "body": "x"}).status_code == 400
    saved = DocPage.objects.get()
    assert (saved.youtube_id, saved.body) == (ID, "")


@pytest.mark.django_db
def test_nobody_else_can_change_a_page(anon, api):
    for change in ({"video_link": LINK}, {"body": "Hacked"}):
        assert anon.patch(PAGE, change).status_code == 401
        # Owns a workspace, but not this installation.
        assert api.patch(PAGE, change).status_code == 403
    assert not DocPage.objects.exists()


@pytest.mark.django_db
def test_me_says_who_is_a_superuser(api, superuser):
    assert api.get("/auth/me").json()["is_superuser"] is False
    assert superuser.get("/auth/me").json()["is_superuser"] is True


@pytest.mark.django_db
def test_make_superuser():
    user = UserFactory(email="me@example.com")
    call_command("make_superuser", "Me@Example.com")
    user.refresh_from_db()
    assert user.is_superuser and user.is_staff
    with pytest.raises(CommandError):
        call_command("make_superuser", "nobody@example.com")


@pytest.mark.django_db
@pytest.mark.skipif(not PAGES.exists(), reason="The container has only the backend.")
def test_the_token_example_is_accepted(monkeypatch):
    workspace = WorkspaceFactory()
    monkeypatch.setenv("WHILEISLEEP_IDENTITY_SECRET", workspace.identity_secret)
    page = (PAGES / "verified-identity.md").read_text(encoding="utf-8")
    example = {}
    exec(re.search(r"```python\n(.*?)```", page, re.S)[1], example)
    token = example["chat_token"](SimpleNamespace(id=7, email="maya@example.com", name="Maya", plan="pro"))
    claims = identity.verify(workspace, token)
    assert (claims["sub"], claims["email"], claims["plan"]) == ("7", "maya@example.com", "pro")
