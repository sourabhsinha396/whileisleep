"""Text between whileisleep and Slack.

Teammates and the AI write a little Markdown (frontend/src/lib/chat-text.ts); visitors write plain
text. Slack has its own markup, and describes what people typed as `rich_text` blocks.
"""

import re

# A section block takes 3000 characters.
MAX_CHARS = 2900

INLINE = re.compile(
    r"\\([\\*_\[\]])"
    r"|\[((?:\\.|[^\]\\\n])+)\]\((https?://[^)\s]+)\)"
    r"|\*\*\*(\S(?:.*?\S)?)\*\*\*"
    r"|\*\*(\S(?:.*?\S)?)\*\*"
    r"|(?<![^\W_])\*([^\s*](?:[^*\n]*[^\s*])?)\*(?![^\W_])"
    r"|(?<![^\W_])_([^\s_](?:[^_\n]*[^\s_])?)_(?![^\W_])"
    r"|(https?://[^\s<]+)"
)


def escape(text: str) -> str:
    """So Slack shows it as it is: no mentions, no links in disguise."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def link(url: str, label: str) -> str:
    """Only ever an http(s) address."""
    if not re.match(r"https?://", url):
        return escape(label)
    url = escape(url).replace("|", "%7C")
    return f"<{url}|{escape(label).replace('|', '/')}>"


def clip(text: str) -> str:
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS].rstrip() + "…"


# --- To Slack ---


def from_markdown(text: str) -> str:
    lines = (re.sub(r"^\s*[-*]\s+(?=\S)", "• ", line) for line in text.split("\n"))
    return "\n".join(inline(line) for line in lines)


def inline(text: str) -> str:
    def convert(match: re.Match) -> str:
        escaped, label, url, both, bold, italic, italic2, bare = match.groups()
        if escaped:
            return escape(escaped)
        if url:
            return link(url, re.sub(r"\\([\\*_\[\]])", r"\1", label))
        if both:
            return f"*_{inline(both)}_*"
        if bold:
            return f"*{inline(bold)}*"
        if italic or italic2:
            return f"_{inline(italic or italic2)}_"
        return escape(bare)

    parts, end = [], 0
    for match in INLINE.finditer(text):
        parts += [escape(text[end : match.start()]), convert(match)]
        end = match.end()
    return "".join([*parts, escape(text[end:])])


# --- From Slack ---


def to_markdown(blocks: list, fallback: str) -> str:
    """What a person typed in Slack. `fallback` is Slack's markup of it, for a message without blocks."""
    parts = []
    for block in blocks or []:
        if block.get("type") == "rich_text":
            parts += [rich(element) for element in block.get("elements") or []]
    text = "\n".join(part for part in parts if part.strip())
    return (text or from_markup(fallback)).strip()


def rich(element: dict) -> str:
    kind, children = element.get("type"), element.get("elements") or []
    if kind == "rich_text_list":
        ordered = element.get("style") == "ordered"
        first = 1 + (element.get("offset") or 0)
        items = [rich(child).replace("\n", " ") for child in children]
        return "\n".join(f"{first + i}. {item}" if ordered else f"- {item}" for i, item in enumerate(items))
    return "".join(piece(child) for child in children)


def piece(child: dict) -> str:
    kind = child.get("type")
    if kind == "text":
        return styled(child.get("text", ""), child.get("style") or {})
    if kind == "link":
        url, label = child.get("url", ""), child.get("text", "")
        if not url.startswith(("http://", "https://")):
            return label or url.removeprefix("mailto:").removeprefix("tel:")
        if not label or label == url:
            return url
        return f"[{protect(label)}]({url.replace('(', '%28').replace(')', '%29')})"
    if kind == "emoji":
        return emoji(child)
    if kind == "channel":
        return "#channel"
    if kind in ("user", "usergroup"):
        # Who that is in Slack is none of the visitor's business.
        return "@teammate"
    if kind == "broadcast":
        return f"@{child.get('range', 'here')}"
    return ""


def styled(text: str, style: dict) -> str:
    mark = ("**" if style.get("bold") else "") + ("*" if style.get("italic") else "")
    if not mark:
        return protect(text)
    # The marks must touch the words, and stay on one line.
    lines = []
    for line in text.split("\n"):
        words = line.strip()
        before, after = line[: len(line) - len(line.lstrip())], line[len(line.rstrip()) :]
        lines.append(f"{before}{mark}{protect(words)}{mark}{after}" if words else line)
    return "\n".join(lines)


def protect(text: str) -> str:
    """Characters that would otherwise become formatting."""
    if all(match.group(8) for match in INLINE.finditer(text)):
        return text
    return re.sub(r"([\\*_\[\]])", r"\\\1", text)


def emoji(child: dict) -> str:
    try:
        return "".join(chr(int(code, 16)) for code in child["unicode"].split("-"))
    except (KeyError, ValueError, OverflowError):
        # One of the team's own.
        return f":{child.get('name', '')}:"


def from_markup(text: str) -> str:
    def angle(match: re.Match) -> str:
        target, _, label = match.group(1).partition("|")
        if target.startswith(("@", "!subteam")):
            return "@teammate"
        if target.startswith("#"):
            return "#channel"
        if target.startswith("!"):
            return f"@{target[1:]}"
        return label or target.removeprefix("mailto:")

    text = re.sub(r"<([^>]+)>", angle, text or "")
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
