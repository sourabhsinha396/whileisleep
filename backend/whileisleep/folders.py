"""Which folder of the bucket each kind of file goes in.

    workspaces/<workspace id>/logo/
    workspaces/<workspace id>/articles/<article id>/
    users/<user id>/photo/          (a person can be in several workspaces)

Ids, not names or slugs: those change, and the files would be left in the old folder. File
names are random, so a link can't be guessed and a replaced file gets a new address instead
of showing from someone's cache.
"""

import uuid
from pathlib import PurePosixPath


def in_folder(folder: str, name: str) -> str:
    return f"{folder}/{uuid.uuid4().hex}{PurePosixPath(name).suffix.lower()}"


def workspace_folder(workspace_id: int) -> str:
    return f"workspaces/{workspace_id}"


# The three below are `upload_to` functions: (the row the file belongs to, its file name).


def workspace_logo(workspace, name: str) -> str:
    return in_folder(f"{workspace_folder(workspace.pk)}/logo", name)


def article_image(image, name: str) -> str:
    article = image.article
    return in_folder(f"{workspace_folder(article.workspace_id)}/articles/{article.pk}", name)


def user_photo(profile, name: str) -> str:
    return in_folder(f"users/{profile.user_id}/photo", name)
