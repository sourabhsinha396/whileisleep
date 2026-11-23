from datetime import datetime

from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from pydantic import Field

from apps.accounts.security import token_auth
from apps.workspaces.services import member_workspace

from .models import Article

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
