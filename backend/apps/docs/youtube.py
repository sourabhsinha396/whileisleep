import re
from urllib.parse import parse_qs, urlsplit

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
SITES = {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}
# youtube.com/shorts/ID and the like.
PATHS = {"shorts", "embed", "live"}


def video_id(link: str) -> str | None:
    """The id in a YouTube link, or None if it isn't a link to one video."""
    link = link.strip()
    try:
        parts = urlsplit(link if "://" in link else f"https://{link}")
        host = (parts.hostname or "").removeprefix("www.")
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    path = parts.path.strip("/").split("/")
    found = ""
    if host == "youtu.be":
        found = path[0]
    elif host in SITES and path == ["watch"]:
        found = parse_qs(parts.query).get("v", [""])[0]
    elif host in SITES and len(path) == 2 and path[0] in PATHS:
        found = path[1]
    return found if VIDEO_ID.fullmatch(found) else None
