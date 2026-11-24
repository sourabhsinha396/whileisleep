from datetime import datetime

from django.conf import settings
from django.shortcuts import get_object_or_404
from ninja import File, Router, Schema, UploadedFile
from ninja.errors import HttpError
from pydantic import Field

from apps.accounts.security import token_auth
from apps.workspaces.services import member_workspace
from whileisleep import images

from .models import Article, ArticleImage

router = Router(tags=["knowledge"], auth=token_auth)


class ArticleIn(Schema):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    published: bool = True


class ArticleOut(Schema):
    id: int
    title: str
    body: str
    published: bool
    updated_at: datetime


class ArticleImageOut(Schema):
    url: str


@router.get("/workspaces/{workspace_id}/articles", response=list[ArticleOut])
def list_articles(request, workspace_id: int):
    return member_workspace(request.auth, workspace_id).articles.all()


@router.post("/workspaces/{workspace_id}/articles", response=ArticleOut)
def create(request, workspace_id: int, payload: ArticleIn):
    return Article.objects.create(workspace=member_workspace(request.auth, workspace_id), **payload.dict())


@router.put("/workspaces/{workspace_id}/articles/{article_id}", response=ArticleOut)
def update(request, workspace_id: int, article_id: int, payload: ArticleIn):
    article = get_object_or_404(Article, pk=article_id, workspace=member_workspace(request.auth, workspace_id))
    for field, value in payload.dict().items():
        setattr(article, field, value)
    article.save()
    return article


@router.delete("/workspaces/{workspace_id}/articles/{article_id}")
def delete(request, workspace_id: int, article_id: int):
    get_object_or_404(Article, pk=article_id, workspace=member_workspace(request.auth, workspace_id)).delete()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/articles/{article_id}/images", response=ArticleImageOut)
def upload_image(request, workspace_id: int, article_id: int, file: UploadedFile = File(...)):  # noqa: B008
    """Stores a picture for the article. The editor puts its address in the text."""
    workspace = member_workspace(request.auth, workspace_id)
    article = get_object_or_404(Article, pk=article_id, workspace=workspace)
    images.require_storage()
    limit = settings.ARTICLE_IMAGES_PER_WORKSPACE
    if ArticleImage.objects.filter(article__workspace=workspace).count() >= limit:
        raise HttpError(400, f"This workspace has reached its limit of {limit} article images.")
    image = ArticleImage.objects.create(article=article, file=images.clean_image(file, images.PICTURE_SIDE))
    return {"url": image.file.url}
