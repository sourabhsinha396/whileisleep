"""Condition trees: how a rule says when it applies.

A condition is JSON, so it can be stored, sent to the dashboard and exported as config:

    {"all": [
        {"field": "message.text", "op": "contains_any", "value": ["refund", "money back"]},
        {"any": [
            {"field": "contact.plan", "op": "equals", "value": "pro"},
            {"field": "page.url", "op": "contains", "value": "/pricing"}
        ]}
    ]}

A node is one of

- {"all": [nodes]}   every node holds
- {"any": [nodes]}   at least one holds
- {"not": node}      the node doesn't hold
- {"field": name, "op": operator, "value": ...}   a test on one fact

It is evaluated against a *context*: a flat dict of facts by dotted name
(apps.agent.rules.context_for builds it from a message). A field that isn't in the context
is simply unknown, and every test on it is false except `not_exists`.

Pure functions, no database and no model calls: a rule costs nothing to evaluate, so it can
also be tried against thousands of past messages before it is switched on.
"""

import re

MAX_DEPTH = 5
MAX_TESTS = 40
MAX_LIST_VALUES = 50
MAX_TEXT = 300

FIELD = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$")
GROUPS = ("all", "any")

# Operators by the kind of value they compare with.
TEXT_OPS = ("contains", "not_contains", "starts_with", "ends_with", "has_word")
LIST_OPS = ("contains_any", "has_any_word", "in", "not_in")
NUMBER_OPS = ("gt", "gte", "lt", "lte")
ANY_OPS = ("equals", "not_equals")
NO_VALUE_OPS = ("exists", "not_exists")
OPS = (*TEXT_OPS, *LIST_OPS, *NUMBER_OPS, *ANY_OPS, *NO_VALUE_OPS)


class InvalidCondition(ValueError):
    """The tree isn't well-formed. The message is safe to show the rule's author."""


# --- Checking a tree before it is saved ---


def validate(node, depth: int = 0, counter: list[int] | None = None) -> None:
    """Raises InvalidCondition unless `node` is a tree `evaluate` can run."""
    counter = counter if counter is not None else [0]
    if depth > MAX_DEPTH:
        raise InvalidCondition(f"Conditions can be nested at most {MAX_DEPTH} levels deep.")
    if not isinstance(node, dict):
        raise InvalidCondition("A condition must be an object.")

    group = [key for key in GROUPS if key in node]
    if group or "not" in node:
        if len(node) != 1:
            raise InvalidCondition('"all", "any" and "not" stand alone in their object.')
        if "not" in node:
            validate(node["not"], depth + 1, counter)
            return
        children = node[group[0]]
        if not isinstance(children, list) or not children:
            raise InvalidCondition(f'"{group[0]}" needs a list with at least one condition.')
        for child in children:
            validate(child, depth + 1, counter)
        return

    counter[0] += 1
    if counter[0] > MAX_TESTS:
        raise InvalidCondition(f"A rule can have at most {MAX_TESTS} conditions.")
    validate_test(node)


def validate_test(node: dict) -> None:
    unknown = set(node) - {"field", "op", "value"}
    if unknown:
        raise InvalidCondition(f"Unknown key in a condition: {sorted(unknown)[0]}.")
    field, op = node.get("field"), node.get("op")
    if not isinstance(field, str) or not FIELD.match(field):
        raise InvalidCondition("A condition needs a field such as message.text or contact.plan.")
    if op not in OPS:
        raise InvalidCondition(f"Unknown operator for {field}: {op!r}.")
    value = node.get("value")
    if op in NO_VALUE_OPS:
        if value is not None:
            raise InvalidCondition(f"{op} takes no value.")
    elif op in LIST_OPS:
        if not isinstance(value, list) or not value or len(value) > MAX_LIST_VALUES:
            raise InvalidCondition(f"{op} needs a list of 1 to {MAX_LIST_VALUES} values.")
        if not all(is_scalar(item) for item in value):
            raise InvalidCondition(f"{op} values must be text, numbers or true/false.")
    elif op in NUMBER_OPS:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise InvalidCondition(f"{op} needs a number.")
    elif op in TEXT_OPS:
        if not isinstance(value, str) or not value.strip():
            raise InvalidCondition(f"{op} needs some text.")
    elif not is_scalar(value):
        raise InvalidCondition(f"{op} needs a value: text, a number or true/false.")


def is_scalar(value) -> bool:
    if isinstance(value, str):
        return 0 < len(value) <= MAX_TEXT
    return isinstance(value, bool | int | float)


# --- Evaluating ---


def evaluate(node: dict, context: dict) -> bool:
    """Whether the (validated) tree holds for these facts."""
    if "all" in node:
        return all(evaluate(child, context) for child in node["all"])
    if "any" in node:
        return any(evaluate(child, context) for child in node["any"])
    if "not" in node:
        return not evaluate(node["not"], context)
    return test(node["op"], context.get(node["field"]), node.get("value"))


def test(op: str, actual, expected) -> bool:
    if op == "exists":
        return actual not in (None, "", [])
    if op == "not_exists":
        return actual in (None, "", [])
    if actual is None:
        # Nothing is known, so nothing can be said about it, not even "not equal to".
        return False
    if op == "equals":
        return same(actual, expected)
    if op == "not_equals":
        return not same(actual, expected)
    if op == "in":
        return any(same(actual, item) for item in expected)
    if op == "not_in":
        return not any(same(actual, item) for item in expected)
    if op in NUMBER_OPS:
        return compare(op, actual, expected)
    return text_test(op, actual, expected)


def same(actual, expected) -> bool:
    """Equal, ignoring case for text. A list (tags) equals a value it contains."""
    if isinstance(actual, list):
        return any(same(item, expected) for item in actual)
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, int | float) and isinstance(expected, int | float):
        return actual == expected
    return fold(actual) == fold(expected)


def compare(op: str, actual, expected) -> bool:
    number = as_number(actual)
    if number is None:
        return False
    return {"gt": number > expected, "gte": number >= expected, "lt": number < expected, "lte": number <= expected}[op]


def as_number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def text_test(op: str, actual, expected) -> bool:
    haystack = fold(" ".join(map(str, actual)) if isinstance(actual, list) else actual)
    if op == "contains":
        return fold(expected) in haystack
    if op == "not_contains":
        return fold(expected) not in haystack
    if op == "starts_with":
        return haystack.startswith(fold(expected))
    if op == "ends_with":
        return haystack.endswith(fold(expected))
    if op == "contains_any":
        return any(fold(item) in haystack for item in expected)
    if op == "has_word":
        return has_word(haystack, fold(expected))
    if op == "has_any_word":
        return any(has_word(haystack, fold(item)) for item in expected)
    raise InvalidCondition(f"Unknown operator {op!r}.")


def has_word(haystack: str, phrase: str) -> bool:
    """`phrase` appears as whole words: "hi" is in "hi there" but not in "this"."""
    if not phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", haystack) is not None


def fold(value) -> str:
    return " ".join(str(value).casefold().split())


def fields(node: dict) -> set[str]:
    """Every field a tree looks at."""
    if "all" in node or "any" in node:
        children = node.get("all") or node.get("any")
        return set().union(*(fields(child) for child in children))
    if "not" in node:
        return fields(node["not"])
    return {node["field"]}
