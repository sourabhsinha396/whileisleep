import mimetypes
from datetime import datetime

from django.shortcuts import get_object_or_404
from ninja import File, Router, Schema, UploadedFile
from ninja.errors import HttpError
from pydantic import Field

from apps.accounts.security import token_auth
from apps.workspaces import buckets
from apps.workspaces.services import member_workspace
from whileisleep import images
from whileisleep.folders import article_image

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
    """Stores a picture for the article, in the organization's own bucket. The editor puts its
    address in the text. Never in our storage, whose files anyone can open: what is in someone's
    articles is theirs to publish. Without a bucket, articles are text."""
    workspace = member_workspace(request.auth, workspace_id)
    article = get_object_or_404(Article, pk=article_id, workspace=workspace)
    bucket = workspace.organization.storage_bucket
    if bucket is None:
        raise HttpError(409, "Connect your storage in Settings to add images. Articles work without them.")
    content = images.clean_image(file, images.PICTURE_SIDE)
    name = f"{buckets.FOLDER}/{article_image(ArticleImage(article=article), content.name)}"
    try:
        buckets.put(bucket, name, content.read(), mimetypes.guess_type(name)[0] or "application/octet-stream")
    except buckets.BucketError as error:
        raise HttpError(502, f"Your storage didn't take the image. {error}") from error
    ArticleImage.objects.create(article=article, file=name, hosted=False, bucket=bucket)
    return {"url": buckets.url(bucket, name)}
