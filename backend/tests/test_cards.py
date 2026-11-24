import json
from pathlib import Path

import pytest

from apps.agent import a2ui, bot, cards, forms, http_tools
from apps.conversations.models import Message

from .conftest import assistant, final, tool_call
from .factories import MessageFactory, OrganizationFactory, ToolFactory

CATALOG = Path(__file__).parents[2] / "frontend/public/a2ui/v1/catalog.json"

ORDER = {
    "order": {
        "number": "A-1042",
        "status": "Shipped",
        "total": 89.5,
        "gift": False,
        "placed": "2026-11-20T09:30:00Z",
        "note": None,
        "customer": {"internal_id": "secret-77"},
    },
    "steps": [
        {"name": "Packed", "at": "2026-11-21", "done": True},
        {"name": "Delivered", "done": False},
        {"at": "nameless"},
    ],
    "tags": ["new", "sale"],
}


def details(*rows, **extra):
    return {
        "type": "details",
        "result": "r1",
        "title": "Your order",
        "rows": [{"label": label, "path": path} for label, path in rows],
        **extra,
    }


def build(*specs, data=ORDER):
    return cards.normalize(list(specs), {"r1": data})


# --- values come from the result ---


def test_details_read_values_from_the_result():
    [card] = build(
        details(
            ("Order", "/order/number"),
            ("Total", "order/total"),
            ("Gift", "/order/gift"),
            ("Placed", "/order/placed"),
        )
    )
    assert card["rows"] == [
        {"label": "Order", "value": "A-1042"},
        {"label": "Total", "value": "89.5"},
        {"label": "Gift", "value": "No"},
        {"label": "Placed", "value": "2026-11-20 09:30 UTC"},
    ]


def test_a_value_the_model_writes_itself_is_ignored():
    spec = details(("Status", "/order/status"))
    spec["rows"][0]["value"] = "Refunded"
    assert build(spec)[0]["rows"] == [{"label": "Status", "value": "Shipped"}]


def test_numbers_in_titles_and_labels_must_be_in_the_result():
    [card] = build(details(("Order", "/order/number"), ("Refund 500 EUR", "/order/status"), title="Order A-9999"))
    assert card["title"] == ""
    assert card["rows"] == [{"label": "Order", "value": "A-1042"}]
    assert build(details(("Order", "/order/number"), title="Order A-1042"))[0]["title"] == "Order A-1042"


@pytest.mark.parametrize(
    "path",
    ["/order", "/steps", "/order/note", "/nope/x", "/steps/99/name", "/steps/-1/name", "/order/status/x", 7, None],
)
def test_paths_to_nothing_showable_are_dropped(path):
    assert build(details(("X", path))) == []


def test_timeline_and_list():
    steps = {"type": "timeline", "result": "r1", "items_path": "/steps", "title_path": "/name"}
    [card] = build({**steps, "detail_path": "/at", "done_path": "/done"})
    assert card["rows"] == [
        {"title": "Packed", "detail": "2026-11-21", "done": True},
        {"title": "Delivered", "detail": "", "done": False},
    ]
    [card] = build({"type": "list", "result": "[result r1]", "items_path": "/tags"})
    assert [row["title"] for row in card["rows"]] == ["new", "sale"]
    [card] = build({"type": "list", "result": "r1", "title_path": "/n"}, data=[{"n": i} for i in range(9)])
    assert len(card["rows"]) == cards.MAX_ITEMS


def test_limits():
    assert len(build(*[details(("Order", "/order/number"))] * 9)) == cards.MAX_CARDS
    assert len(build(details(*[("Order", "/order/number")] * 30))[0]["rows"]) == cards.MAX_ROWS
    [card] = build(details(("Text", "/t")), data={"t": "x" * 999})
    assert len(card["rows"][0]["value"]) == cards.MAX_VALUE + 1


@pytest.mark.parametrize(
    "specs",
    [
        None,
        "x",
        {},
        [None],
        [{}],
        [{"type": "details", "result": 1}],
        [{"type": "html", "result": "r1"}],
        [{"type": "details", "result": "r2", "rows": [{"label": "A", "path": "/order/number"}]}],
        [{"type": "details", "result": "r1", "rows": [3, {"label": 4, "path": "/order/number"}]}],
        [{"type": "list", "result": "r1", "items_path": 5, "title_path": 6}],
    ],
)
def test_unusable_cards_are_dropped(specs):
    assert cards.normalize(specs, {"r1": ORDER}) == []


@pytest.mark.parametrize("content", ["plain", '{"a": 1} ...[truncated]', "5", "[]", "", "null"])
def test_only_whole_json_can_be_shown(content):
    assert cards.parse(content) is None


# --- A2UI ---


def test_only_shown_values_reach_the_visitor():
    sent = json.dumps(cards.attach(build(details(("Status", "/order/status")))))
    assert "Shipped" in sent
    assert "secret-77" not in sent


def test_everything_we_send_is_in_the_catalog():
    catalog = json.loads(CATALOG.read_text(encoding="utf8"))
    assert catalog["catalogId"] == a2ui.CATALOG_ID
    form = forms.normalize(
        {
            "title": "T",
            "fields": [{"name": "a", "label": "A", "type": kind, "options": ["x", "y"]} for kind in ["choice"]]
            + [{"name": "b", "label": "B", "type": "long_text"}],
        }
    )
    steps = {"type": "timeline", "result": "r1", "items_path": "/steps", "title_path": "/name", "done_path": "/done"}
    messages = [
        *cards.attach(build(details(("Order", "/order/number")), steps)),
        *a2ui.form("form_1", form),
        *a2ui.reply_actions("reply_1", [], True),
    ]
    for message in messages:
        for component in message.get("updateComponents", {}).get("components", []):
            spec = catalog["components"][component["component"]]
            props = set(component) - {"id"}
            assert props <= set(spec["properties"])
            assert set(spec["required"]) <= props
            if "variant" in component:
                assert component["variant"] in spec["properties"]["variant"]["enum"]


def test_card_children_exist_and_bindings_resolve():
    create, update = cards.attach(build(details(("Order", "/order/number"))))
    components = {c["id"]: c for c in update["updateComponents"]["components"]}
    assert components["root"] == {"id": "root", "component": "Card", "child": "body"}
    for component in components.values():
        for child in component.get("children", []) + ([component["child"]] if "child" in component else []):
            assert child in components
    assert components["value_0"]["text"] == {"@path": "/value_0"}
    assert create["createSurface"]["dataModel"] == {"value_0": "A-1042"}


# --- the AI's reply ---


def ask(llm, monkeypatch, content, *responses, is_error=False):
    conversation = MessageFactory(
        body="Where is my order?", conversation__workspace__organization=OrganizationFactory(ready=True)
    ).conversation
    ToolFactory(workspace=conversation.workspace, name="get_order", url="https://shop.example.com/order")
    monkeypatch.setattr(http_tools, "run", lambda tool, inputs, visitor: (content, is_error))
    fake = llm(assistant(tool_call("get_order", {})), *responses)
    return conversation, bot.reply(conversation.id), fake


def answer(text="It has shipped.", **extra):
    args = {"reply": text, "article_ids": [], "offer_human": False, **extra}
    return assistant(tool_call("reply_to_visitor", args, id="call_final"))


@pytest.mark.django_db
def test_reply_carries_a_card_and_the_ai_remembers_it(llm, monkeypatch):
    card = details(("Status", "/order/status"))
    conversation, message, fake = ask(llm, monkeypatch, json.dumps(ORDER), answer(cards=[card], offer_human=True))
    [result] = [m for m in fake.requests[1]["messages"] if m.get("role") == "tool"]
    assert result["content"].startswith("[result r1]\n{")
    assert message.body == "It has shipped."
    surfaces = [m["createSurface"]["surfaceId"] for m in message.a2ui if "createSurface" in m]
    # The card comes first, then the buttons.
    assert [s.split("_")[0] for s in surfaces] == ["card", "reply"]

    MessageFactory(conversation=conversation, body="Thanks, and the total?", sender=Message.Sender.VISITOR)
    history = bot.chat_history(conversation)
    assert history[1]["content"] == "It has shipped.\n\n[Card shown: Your order; Status; Shipped]"


@pytest.mark.django_db
@pytest.mark.parametrize("content,is_error", [("Shipped", False), ('{"order": {"status": "Shipped"}}', True)])
def test_text_and_errors_give_no_card(llm, monkeypatch, content, is_error):
    _, message, fake = ask(
        llm, monkeypatch, content, answer(cards=[details(("Status", "/order/status"))]), is_error=is_error
    )
    assert message.a2ui is None
    assert message.body == "It has shipped."
    assert "[result" not in str([m for m in fake.requests[1]["messages"] if m.get("role") == "tool"])


@pytest.mark.django_db
def test_a_copied_note_is_not_sent(llm, monkeypatch):
    _, message, _ = ask(llm, monkeypatch, "Shipped", final("It has shipped.\n\n[Card shown: Order; 1]"))
    assert message.body == "It has shipped."
