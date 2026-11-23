"""Builders for A2UI v1.0 surfaces (https://a2ui.org) that bot messages carry.

The server writes these from templates; the model only chooses the text and which
articles to show. A message's `a2ui` field holds the list of A2UI messages
(createSurface, then updateComponents) that the widget renders under the text.
A button's `action.event` comes back to POST /widget/{key}/actions.
"""

CATALOG_ID = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json"
VERSION = "1.0"


def surface(surface_id: str, components: list[dict], data_model: dict | None = None) -> list[dict]:
    create = {"surfaceId": surface_id, "catalogId": CATALOG_ID}
    if data_model is not None:
        create["dataModel"] = data_model
    return [
        {"version": VERSION, "createSurface": create},
        {"version": VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}},
    ]


def text(id: str, value, variant: str | None = None) -> dict:
    component = {"id": id, "component": "Text", "text": value}
    if variant:
        component["variant"] = variant
    return component


def button(id: str, label: str, event: str, context: dict | None = None, variant: str = "default") -> list[dict]:
    """A Button and the Text inside it."""
    return [
        {
            "id": id,
            "component": "Button",
            "child": f"{id}_label",
            "variant": variant,
            "action": {"event": {"name": event, "context": context or {}}},
        },
        text(f"{id}_label", label),
    ]


def column(id: str, children: list[str]) -> dict:
    return {"id": id, "component": "Column", "children": children}


def reply_actions(surface_id: str, articles: list, offer_human: bool) -> list[dict] | None:
    """Related-article buttons and a "Talk to a person" button under a bot answer."""
    components, children = [], []
    for i, article in enumerate(articles):
        children.append(f"article_{i}")
        components += button(f"article_{i}", article.title, "open_article", {"articleId": article.id}, "borderless")
    if offer_human:
        children.append("human")
        components += button("human", "Talk to a person", "talk_to_human")
    if not children:
        return None
    return surface(surface_id, [column("root", children), *components])


TEXT_VARIANTS = {"long_text": "longText", "number": "number"}


def form(surface_id: str, spec: dict) -> list[dict]:
    """Compiles a checked form spec (apps.agent.forms.normalize) to an A2UI surface.

    Each field binds to /fields/<name>; the submit button sends them all as the
    submit_form event's `fields` context.
    """
    children, components = [], []
    if spec.get("title"):
        children.append("title")
        components.append(text("title", spec["title"]))
    for field in spec["fields"]:
        cid = f"f_{field['name']}"
        children.append(cid)
        label = field["label"] + (" *" if field["required"] else "")
        binding = {"@path": f"/fields/{field['name']}"}
        if field["type"] == "choice":
            components.append(
                {
                    "id": cid,
                    "component": "ChoicePicker",
                    "label": label,
                    "variant": "mutuallyExclusive",
                    "options": [{"label": o, "value": o} for o in field["options"]],
                    "value": binding,
                }
            )
        else:
            components.append(
                {
                    "id": cid,
                    "component": "TextField",
                    "label": label,
                    "variant": TEXT_VARIANTS.get(field["type"], "shortText"),
                    "value": binding,
                }
            )
    children.append("submit")
    components += button("submit", spec["submit_label"], "submit_form", {"fields": {"@path": "/fields"}}, "primary")
    data = {"fields": {f["name"]: "" for f in spec["fields"]}}
    return surface(surface_id, [column("root", children), *components], data_model=data)


# Shown when a visitor asks for a person and we don't have their email yet.
AWAY_FORM = {
    "title": "Leave your email and we'll reply there too if you step away.",
    "fields": [{"name": "email", "label": "Email", "type": "email", "required": True}],
    "submit_label": "Save email",
}
