"""Files in chat messages, from visitors and teammates.

They go to the organization's own bucket (apps.workspaces.buckets), never to ours: what people
send in a chat is the customer's to keep. Without a bucket, chats are text.

A file is uploaded first, on its own, and belongs to nobody's message. Sending a message with
its id attaches it. One that is never sent is deleted a day later (tasks.py).

Visitors are strangers, so what they upload is limited: pictures are decoded and saved again
(whileisleep.images), and only known kinds of document are kept, under a type we choose, as a
download. None of them runs in the browser that opens it.
"""

import mimetypes
import re
from pathlib import PurePosixPath

from ninja.errors import HttpError

from apps.workspaces import buckets
from apps.workspaces.models import Workspace
from whileisleep import images
from whileisleep.folders import in_folder, workspace_folder

from .models import Attachment, Message, Visitor

MAX_BYTES = 10 * 1024 * 1024
MAX_PER_MESSAGE = 5
# Longest side, in pixels: a full screenshot stays readable.
IMAGE_SIDE = 2400
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
DOCUMENTS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".csv": "text/csv",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def clean_name(name: str) -> str:
    """The file's own name, safe to show: no folders, control characters or direction tricks."""
    name = PurePosixPath(name.replace("\\", "/")).name
    name = "".join(c for c in name if c.isprintable() and c not in '"<>').strip()
    # Cut in the middle: the end says what kind of file it is.
    return name if len(name) <= 120 else f"{name[:90]}…{name[-29:]}"


def upload(workspace: Workspace, file, *, visitor: Visitor | None = None, user=None) -> Attachment:
    """Stores a file that someone is about to send. HttpError says what is wrong with it."""
    bucket = workspace.organization.storage_bucket
    if bucket is None:
        raise HttpError(409, "Files are off: no storage is connected.")
    if file.size > MAX_BYTES:
        raise HttpError(400, f"That file is too big. The limit is {MAX_BYTES // (1024 * 1024)} MB.")
    name = clean_name(file.name or "")
    extension = PurePosixPath(name).suffix.lower()
    width = height = None
    if extension in IMAGES:
        picture = images.clean_image(file, IMAGE_SIDE, max_bytes=MAX_BYTES)
        content, stored = picture.read(), picture.name
        width, height = images.size(content)
        content_type, download_as = mimetypes.guess_type(stored)[0], ""
    elif extension in DOCUMENTS:
        content, stored = file.read(), f"file{extension}"
        content_type, download_as = DOCUMENTS[extension], name
    else:
        raise HttpError(400, "Send a picture (PNG, JPEG, WebP), a PDF, a text or CSV file, or a Word or Excel file.")
    if not content:
        raise HttpError(400, "That file is empty.")
    path = f"{buckets.FOLDER}/{in_folder(f'{workspace_folder(workspace.pk)}/chats', stored)}"
    try:
        buckets.put(bucket, path, content, content_type, download_as=download_as)
    except buckets.BucketError as error:
        # What is wrong with the bucket is for the team, not for a visitor.
        why = f"Your storage didn't take the file. {error}" if user else "The file couldn't be saved. Please try again."
        raise HttpError(502, why) from error
    return Attachment.objects.create(
        workspace=workspace,
        visitor=visitor,
        uploaded_by=user,
        bucket=bucket,
        path=path,
        url=buckets.url(bucket, path),
        name=name or stored,
        content_type=content_type,
        size=len(content),
        width=width,
        height=height,
    )


def unsent(workspace: Workspace, ids: list[int], *, visitor: Visitor | None = None, user=None) -> list[Attachment]:
    """The files with these ids, which this person uploaded and hasn't sent. 400 if any isn't."""
    if not ids:
        return []
    found = Attachment.objects.filter(
        workspace=workspace, pk__in=ids, message=None, visitor=visitor, uploaded_by=user
    ).order_by("pk")
    if len(found) != len(set(ids)):
        raise HttpError(400, "A file is no longer there. Remove it and attach it again.")
    return list(found)


def label(names: list[str]) -> str:
    """A message's files in a few words, for lists."""
    if not names:
        return ""
    return f"📎 {names[0]}" + (f" +{len(names) - 1}" if len(names) > 1 else "")


# --- What the AI reads ---

AI_NOTE = re.compile(r"^\[Attached: .*\]$", re.MULTILINE)


def text_for_ai(message: Message) -> str:
    """The message with a line that names its files. The AI can't see inside them."""
    names = [a.name.replace("[", "(").replace("]", ")") for a in message.attachments.all()]
    if not names:
        return message.body
    note = f"[Attached: {', '.join(names)}]"
    return f"{message.body}\n\n{note}" if message.body else note


def without_notes(text: str) -> str:
    """`text_for_ai` without the names of files, for searching."""
    return AI_NOTE.sub("", text).strip()
