"""Pictures in help articles: stored in the article's folder, described in words to the AI."""

import re

import pytest

from apps.knowledge import chunking, search
from apps.knowledge.models import ArticleImage, Chunk

from .conftest import Api
from .factories import ArticleFactory, AuthTokenFactory, MembershipFactory, WorkspaceFactory
from .test_images import picture

pytestmark = pytest.mark.django_db


def path(article) -> str:
    return f"/workspaces/{article.workspace_id}/articles/{article.id}/images"


def stored(connected, article) -> list[str]:
    folder = f"whileisleep/workspaces/{article.workspace_id}/articles/{article.id}/"
    return [name.removeprefix(folder) for name in connected.files if name.startswith(folder)]


@pytest.fixture
def article(workspace):
    return ArticleFactory(workspace=workspace)


# --- Uploading ---


def test_an_image_goes_to_its_articles_folder(api, article, connected):
    response = api.upload(path(article), picture(size=(3000, 1500)))
    assert response.status_code == 200
    folder = f"workspaces/{article.workspace_id}/articles/{article.id}"
    assert re.fullmatch(
        rf"https://files\.example\.com/whileisleep/{folder}/[0-9a-f]{{32}}\.png", response.json()["url"]
    )
    assert len(stored(connected, article)) == 1


def test_two_articles_have_two_folders(api, workspace, connected):
    first, second = ArticleFactory(workspace=workspace), ArticleFactory(workspace=workspace)
    for each in (first, second):
        api.upload(path(each), picture())
    assert len(stored(connected, first)) == len(stored(connected, second)) == 1


def test_bad_images_are_refused(api, article, connected):
    assert api.upload(path(article), picture("GIF")).status_code == 400
    assert stored(connected, article) == [] and not ArticleImage.objects.exists()


def test_teammates_may_upload_but_strangers_may_not(article, connected):
    agent = MembershipFactory(workspace=article.workspace, role="agent").user
    assert Api(token=AuthTokenFactory(user=agent).key).upload(path(article), picture()).status_code == 200
    stranger = MembershipFactory().user
    assert Api(token=AuthTokenFactory(user=stranger).key).upload(path(article), picture()).status_code == 404
    assert Api().upload(path(article), picture()).status_code == 401


def test_an_article_of_another_workspace_is_not_found(api, workspace, connected):
    foreign = ArticleFactory(workspace=WorkspaceFactory())
    response = api.upload(f"/workspaces/{workspace.id}/articles/{foreign.id}/images", picture())
    assert response.status_code == 404
    assert stored(connected, foreign) == []


# --- Deleting ---


def test_deleting_an_article_deletes_its_images(api, article, connected):
    api.upload(path(article), picture())
    api.upload(path(article), picture())
    assert api.delete(f"/workspaces/{article.workspace_id}/articles/{article.id}").status_code == 200
    assert stored(connected, article) == []


def test_an_image_copied_into_another_article_survives(api, article, connected):
    url = api.upload(path(article), picture()).json()["url"]
    api.upload(path(article), picture())
    ArticleFactory(workspace=article.workspace, body=f"See ![the button]({url})")
    api.delete(f"/workspaces/{article.workspace_id}/articles/{article.id}")
    assert stored(connected, article) == [url.rsplit("/", 1)[1]]


def test_another_workspace_naming_the_image_does_not_keep_it(api, article, connected):
    url = api.upload(path(article), picture()).json()["url"]
    ArticleFactory(workspace=WorkspaceFactory(), body=f"![x]({url})")
    api.delete(f"/workspaces/{article.workspace_id}/articles/{article.id}")
    assert stored(connected, article) == []


# --- What the AI and search see ---


def test_images_become_their_descriptions():
    body = "Press ![the blue button](https://cdn.example.com/a.png) now.\n\n![](https://cdn.example.com/b.png)\n\nDone."
    assert chunking.split(body) == [chunking.Piece("", "Press [Image: the blue button] now.\n\nDone.")]


def test_links_are_left_alone():
    assert chunking.without_images("[pricing](https://a.example.com/x)") == "[pricing](https://a.example.com/x)"


def test_search_finds_the_description_but_not_the_address(workspace):
    article = ArticleFactory(
        workspace=workspace, title="Setup", body="![blue button](https://cdn.example.com/workspaces/zebra.png)"
    )
    assert Chunk.objects.get(article=article).text == "[Image: blue button]"
    assert search.search(workspace, "blue button") == [article]
    assert search.search(workspace, "zebra") == []


def test_the_widgets_list_shows_no_addresses_but_the_article_keeps_them(anon, article):
    body = "![](https://cdn.example.com/a.png)\n\nHow to pay ![card form](https://cdn.example.com/b.png)"
    article.body = body
    article.save()
    key = article.workspace.public_key
    assert anon.get(f"/widget/{key}/articles").json()[0]["excerpt"] == "How to pay [Image: card form]"
    assert anon.get(f"/widget/{key}/articles/{article.id}").json()["body"] == body
