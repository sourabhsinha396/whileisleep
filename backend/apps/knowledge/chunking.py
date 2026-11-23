"""Splits an article into passages small enough to hand to the AI.

Giving the model whole articles spends most of the prompt on text that doesn't answer the
question. A passage is one section of an article (or part of a long one), kept together
with the headings above it so it still makes sense alone: a paragraph saying "30 days" is
only useful when it also says "Refunds > Digital products".

Pure functions, no database: the indexer and the data migration both use them.
"""

import re
from dataclasses import dataclass

# About 300 tokens. Small enough that several fit a prompt, big enough to hold an answer.
MAX_CHARS = 1200
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Piece:
    # The headings above this text, outermost first: "Refunds > Digital products".
    heading: str
    text: str


def split(body: str) -> list[Piece]:
    """The article's body as passages, in reading order."""
    pieces: list[Piece] = []
    path: list[tuple[int, str]] = []
    paragraphs: list[str] = []

    def heading() -> str:
        return " > ".join(title for _, title in path)

    def flush():
        for text in pack(paragraphs):
            pieces.append(Piece(heading(), text))
        paragraphs.clear()

    for block in blocks(body):
        match = HEADING.match(block)
        if match and "\n" not in block:
            flush()
            level = len(match.group(1))
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, match.group(2)))
        else:
            paragraphs.append(block)
    flush()
    return pieces


def blocks(body: str) -> list[str]:
    """Paragraphs and headings: text separated by blank lines, with a heading always alone."""
    result: list[str] = []
    current: list[str] = []

    def close():
        if current:
            result.append("\n".join(current).strip())
            current.clear()

    for line in (body or "").replace("\r\n", "\n").split("\n"):
        if not line.strip():
            close()
        elif HEADING.match(line):
            close()
            result.append(line.strip())
        else:
            current.append(line.rstrip())
    close()
    return [block for block in result if block]


def pack(paragraphs: list[str]) -> list[str]:
    """Joins paragraphs into passages of at most MAX_CHARS, never cutting inside one unless
    it alone is too long."""
    passages: list[str] = []
    current = ""
    for paragraph in paragraphs:
        for part in fit(paragraph):
            if current and len(current) + 2 + len(part) > MAX_CHARS:
                passages.append(current)
                current = part
            else:
                current = f"{current}\n\n{part}" if current else part
    if current:
        passages.append(current)
    return passages


def fit(paragraph: str) -> list[str]:
    """A paragraph as parts of at most MAX_CHARS, cut at sentence ends where possible."""
    if len(paragraph) <= MAX_CHARS:
        return [paragraph]
    parts: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(paragraph):
        while len(sentence) > MAX_CHARS:
            # One endless sentence (a pasted log, a table): cut it hard.
            if current:
                parts.append(current)
                current = ""
            parts.append(sentence[:MAX_CHARS])
            sentence = sentence[MAX_CHARS:]
        if current and len(current) + 1 + len(sentence) > MAX_CHARS:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        parts.append(current)
    return parts
