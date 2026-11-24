from ninja import Path, Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.accounts.security import token_auth

from .models import DocPage
from .youtube import video_id

router = Router(tags=["docs"])

PAGE = Path(..., max_length=100, pattern=r"^[a-z0-9-]+$")


class DocPagePatch(Schema):
    # Only what is sent changes. An empty body brings the original text back; an empty link removes the video.
    body: str | None = Field(None, max_length=100_000)
    video_link: str | None = Field(None, max_length=500)


class DocPageOut(Schema):
    body: str
    youtube_id: str


@router.get("/docs/{page}", response=DocPageOut)
def get(request, page: str = PAGE):
    """Public, like the page it is about."""
    return DocPage.objects.filter(page=page).first() or DocPage(page=page)


@router.patch("/docs/{page}", response=DocPageOut, auth=token_auth)
def update(request, payload: DocPagePatch, page: str = PAGE):
    if not request.auth.is_superuser:
        raise HttpError(403, "Only a superuser can edit the docs.")
    changes = {}
    if payload.body is not None:
        changes["body"] = payload.body if payload.body.strip() else ""
    if payload.video_link is not None:
        youtube_id = video_id(payload.video_link) if payload.video_link.strip() else ""
        if youtube_id is None:
            raise HttpError(400, "That isn't a link to a YouTube video. Copy it from the video's Share button.")
        changes["youtube_id"] = youtube_id
    saved, _ = DocPage.objects.update_or_create(page=page, defaults=changes)
    return saved
