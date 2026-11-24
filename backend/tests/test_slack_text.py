"""Text between whileisleep and Slack (plugins/slack/text.py). No database."""

import pytest

from plugins.slack import text


@pytest.mark.parametrize(
    ("markdown", "slack"),
    [
        ("plain", "plain"),
        ("**bold** and *italic* and _this_", "*bold* and _italic_ and _this_"),
        ("***both***", "*_both_*"),
        ("[orders](https://a.com/?x=1&y=2)", "<https://a.com/?x=1&amp;y=2|orders>"),
        ("https://a.com/?x=1&y=2", "https://a.com/?x=1&amp;y=2"),
        ("- one\n- two\n1. three", "• one\n• two\n1. three"),
        ("1 < 2 & 3 > 2", "1 &lt; 2 &amp; 3 &gt; 2"),
        ("<!channel>", "&lt;!channel&gt;"),
        (r"\*not bold\*", "*not bold*"),
        ("snake_case_name", "snake_case_name"),
        ("[x](javascript:alert(1))", "[x](javascript:alert(1))"),
        ("**<@U1>**", "*&lt;@U1&gt;*"),
    ],
)
def test_to_slack(markdown, slack):
    assert text.from_markdown(markdown) == slack


def blocks(*elements):
    return [{"type": "rich_text", "elements": list(elements)}]


def section(*children):
    return {"type": "rich_text_section", "elements": list(children)}


def word(value, **style):
    return {"type": "text", "text": value} | ({"style": style} if style else {})


@pytest.mark.parametrize(
    ("typed", "markdown"),
    [
        ([section(word("Hi "), word("there", bold=True))], "Hi **there**"),
        ([section(word("bold ", bold=True), word("x"))], "**bold** x"),
        ([section(word("it", italic=True), word(" "), word("both", bold=True, italic=True))], "*it* ***both***"),
        ([section(word("2*3*4 and snake_case"))], "2*3*4 and snake_case"),
        ([section(word("literally **bold**"))], r"literally \*\*bold\*\*"),
        ([section(word("[x](https://evil.example)"))], r"\[x\](https://evil.example)"),
        ([section({"type": "link", "url": "https://a.com"})], "https://a.com"),
        ([section({"type": "link", "url": "https://a.com/(1)", "text": "see"})], "[see](https://a.com/%281%29)"),
        ([section({"type": "link", "url": "mailto:a@b.com", "text": "a@b.com"})], "a@b.com"),
        ([section({"type": "emoji", "name": "wave", "unicode": "1f44b-1f3fd"})], "\U0001f44b\U0001f3fd"),
        ([section({"type": "emoji", "name": "partyparrot"})], ":partyparrot:"),
        ([section({"type": "user", "user_id": "U1"}, word(" look"))], "@teammate look"),
        ([section({"type": "broadcast", "range": "here"})], "@here"),
        (
            [
                section(word("Steps:")),
                {
                    "type": "rich_text_list",
                    "style": "ordered",
                    "elements": [section(word("one")), section(word("two"))],
                },
                {"type": "rich_text_list", "style": "bullet", "elements": [section(word("three"))]},
            ],
            "Steps:\n1. one\n2. two\n- three",
        ),
        ([{"type": "rich_text_preformatted", "elements": [word("code")]}], "code"),
        ([{"type": "rich_text_something_new", "elements": []}], "the fallback"),
    ],
)
def test_from_slack(typed, markdown):
    assert text.to_markdown(blocks(*typed), "the fallback") == markdown


def test_from_slack_without_blocks():
    markup = "Hi <@U1>, see <https://a.com|this> &amp; <#C1|general> <!here> a &lt; b"
    assert text.to_markdown([], markup) == "Hi @teammate, see this & #channel @here a < b"


def test_long_text_is_cut():
    assert len(text.clip("x" * 10000)) == text.MAX_CHARS + 1
