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


def email_form(surface_id: str) -> list[dict]:
    """Asks for an email so the team can follow up if the visitor leaves."""
    components = [
        column("root", ["prompt", "email", "save"]),
        text("prompt", "Leave your email and we'll reply there too if you step away."),
        {
            "id": "email",
            "component": "TextField",
            "label": "Email",
            "variant": "shortText",
            "value": {"@path": "/email"},
        },
        *button("save", "Save email", "save_email", {"email": {"@path": "/email"}}, "primary"),
    ]
    return surface(surface_id, components, data_model={"email": ""})
