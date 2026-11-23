"""Condition trees: pure logic, no database."""

import pytest

from apps.agent import conditions
from apps.agent.conditions import InvalidCondition, evaluate, validate


def t(field, op, value=None):
    """One test node."""
    node = {"field": field, "op": op}
    if value is not None:
        node["value"] = value
    return node


FACTS = {
    "message.text": "Hi, I'd like a REFUND for my order please",
    "message.intent": "exam_request",
    "message.is_first": True,
    "message.data.exam_code": "SY0-401",
    "page.url": "https://shop.example.com/pricing?plan=pro",
    "contact.plan": "pro",
    "contact.seats": 12,
    "contact.verified": False,
    "conversation.tags": ["vip", "Billing"],
    "conversation.order_total": "49.90",
    "time.hour": 22,
}


# --- Operators ---


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        # Text, ignoring case and extra spaces.
        (t("message.text", "contains", "refund"), True),
        (t("message.text", "contains", "a  refund"), True),
        (t("message.text", "contains", "exchange"), False),
        (t("message.text", "not_contains", "exchange"), True),
        (t("message.text", "starts_with", "hi,"), True),
        (t("message.text", "ends_with", "PLEASE"), True),
        (t("message.text", "contains_any", ["exchange", "refund"]), True),
        (t("message.text", "contains_any", ["exchange", "swap"]), False),
        # Whole words: "hi" is a word here, "fun" only a part of "refund".
        (t("message.text", "has_word", "hi"), True),
        (t("message.text", "has_word", "fun"), False),
        (t("message.text", "has_word", "my order"), True),
        (t("message.text", "has_any_word", ["fun", "order"]), True),
        (t("message.text", "has_any_word", ["fun", "ord"]), False),
        # Equality.
        (t("message.intent", "equals", "EXAM_REQUEST"), True),
        (t("message.intent", "not_equals", "refund"), True),
        (t("contact.plan", "in", ["free", "pro"]), True),
        (t("contact.plan", "not_in", ["free", "team"]), True),
        (t("contact.seats", "equals", 12), True),
        (t("contact.seats", "equals", "12"), True),
        (t("message.is_first", "equals", True), True),
        (t("contact.verified", "equals", True), False),
        (t("contact.verified", "equals", False), True),
        # true is not 1 and not "true".
        (t("message.is_first", "equals", 1), False),
        (t("message.is_first", "equals", "true"), False),
        # Numbers, also when stored as text.
        (t("contact.seats", "gt", 10), True),
        (t("contact.seats", "lte", 12), True),
        (t("contact.seats", "lt", 12), False),
        (t("conversation.order_total", "gte", 49.9), True),
        (t("time.hour", "gte", 18), True),
        (t("contact.plan", "gt", 1), False),  # not a number
        (t("message.is_first", "gt", 0), False),  # true isn't a number either
        # Lists: a tag list "equals" a tag it holds.
        (t("conversation.tags", "equals", "billing"), True),
        (t("conversation.tags", "equals", "sales"), False),
        (t("conversation.tags", "in", ["sales", "vip"]), True),
        (t("conversation.tags", "contains", "bill"), True),
        # Presence.
        (t("contact.plan", "exists"), True),
        (t("contact.company", "exists"), False),
        (t("contact.company", "not_exists"), True),
        (t("contact.plan", "not_exists"), False),
    ],
)
def test_operators(node, expected):
    validate(node)
    assert evaluate(node, FACTS) is expected


@pytest.mark.parametrize("op", [op for op in conditions.OPS if op not in ("exists", "not_exists")])
def test_an_unknown_fact_fails_every_test_even_negative_ones(op):
    """A rule saying "plan is not pro" must not fire for visitors whose plan we don't know."""
    value = {"in": ["x"], "not_in": ["x"], "contains_any": ["x"], "has_any_word": ["x"]}.get(op, "x")
    if op in conditions.NUMBER_OPS:
        value = 1
    assert evaluate(t("contact.company", op, value), FACTS) is False


def test_empty_values_count_as_missing():
    facts = {"contact.name": "", "conversation.tags": []}
    assert evaluate(t("contact.name", "not_exists"), facts)
    assert evaluate(t("conversation.tags", "not_exists"), facts)
    assert not evaluate(t("contact.name", "exists"), facts)


def test_special_characters_in_a_word_are_literal():
    facts = {"message.text": "is c++ (or c#) supported? price: $5.00"}
    assert evaluate(t("message.text", "has_word", "c++"), facts)
    assert evaluate(t("message.text", "has_word", "$5.00"), facts)
    assert not evaluate(t("message.text", "has_word", "pric"), facts)
    # Not a pattern: ".*" would match anything if it were one.
    assert not evaluate(t("message.text", "has_word", ".*"), facts)


# --- Combining ---


def test_all_any_and_not_combine():
    tree = {
        "all": [
            t("message.text", "contains", "refund"),
            {"any": [t("contact.plan", "equals", "team"), t("page.url", "contains", "/pricing")]},
            {"not": t("conversation.tags", "equals", "blocked")},
        ]
    }
    validate(tree)
    assert evaluate(tree, FACTS)
    assert not evaluate(tree, FACTS | {"page.url": "https://shop.example.com/"})
    assert not evaluate(tree, FACTS | {"conversation.tags": ["blocked"]})


def test_not_of_an_unknown_fact_is_true():
    """Deliberate: `not` flips the result, so use it to say "unless we know X is Y"."""
    assert evaluate({"not": t("contact.company", "equals", "Acme")}, FACTS)


def test_fields_lists_what_a_tree_reads():
    tree = {"all": [t("message.text", "contains", "x"), {"not": {"any": [t("contact.plan", "exists")]}}]}
    assert conditions.fields(tree) == {"message.text", "contact.plan"}


# --- Validation ---


@pytest.mark.parametrize(
    ("node", "message"),
    [
        ("message.text contains refund", "must be an object"),
        ([], "must be an object"),
        ({}, "needs a field"),
        ({"all": []}, "at least one"),
        ({"any": "x"}, "at least one"),
        ({"all": [t("message.text", "contains", "x")], "any": [t("page.url", "contains", "y")]}, "stand alone"),
        ({"not": t("message.text", "contains", "x"), "field": "page.url"}, "stand alone"),
        (t("Message.Text", "contains", "x"), "needs a field"),
        (t("text", "contains", "x"), "needs a field"),
        (t("message.text; drop", "contains", "x"), "needs a field"),
        (t("message.text", "matches", "x"), "Unknown operator"),
        (t("message.text", "contains"), "needs some text"),
        (t("message.text", "contains", "   "), "needs some text"),
        (t("message.text", "contains", ["x"]), "needs some text"),
        (t("message.text", "contains_any", "x"), "needs a list"),
        (t("message.text", "contains_any", []), "needs a list"),
        (t("message.text", "contains_any", [["x"]]), "values must be"),
        (t("message.text", "contains_any", ["x"] * 51), "needs a list"),
        (t("contact.seats", "gt", "ten"), "needs a number"),
        (t("contact.seats", "gt", True), "needs a number"),
        (t("contact.plan", "equals"), "needs a value"),
        (t("contact.plan", "equals", {"a": 1}), "needs a value"),
        (t("contact.plan", "equals", "x" * 301), "needs a value"),
        (t("contact.plan", "exists", "yes"), "takes no value"),
        ({"field": "contact.plan", "op": "exists", "extra": 1}, "Unknown key"),
    ],
)
def test_malformed_trees_are_rejected_with_a_reason(node, message):
    with pytest.raises(InvalidCondition, match=message):
        validate(node)


def test_nesting_has_a_limit():
    node = t("message.text", "contains", "x")
    for _ in range(conditions.MAX_DEPTH):
        node = {"not": node}
    validate(node)
    with pytest.raises(InvalidCondition, match="nested"):
        validate({"not": node})


def test_the_number_of_tests_has_a_limit():
    tests = [t("message.text", "contains", f"word{n}") for n in range(conditions.MAX_TESTS)]
    validate({"any": tests})
    with pytest.raises(InvalidCondition, match="at most"):
        validate({"any": [*tests, t("message.text", "contains", "one more")]})


def test_a_pathological_text_does_not_stall_matching():
    """Operators are plain string tests (no user-written regular expressions), so a huge
    message costs time in proportion to its size and no more."""
    facts = {"message.text": "a" * 200_000 + "!"}
    assert not evaluate(t("message.text", "has_word", "aaa"), facts)
    assert evaluate(t("message.text", "ends_with", "a!"), facts)
