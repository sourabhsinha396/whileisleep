"""Widget colors come from a short list."""

import pytest

from apps.workspaces.colors import DEFAULT_COLOR, WIDGET_COLORS
from apps.workspaces.management.commands import seed_demo
from apps.workspaces.models import Workspace

pytestmark = pytest.mark.django_db


def contrast_with_white(color: str) -> float:
    """WCAG contrast ratio."""
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 1.05 / (0.2126 * r + 0.7152 * g + 0.0722 * b + 0.05)


@pytest.mark.parametrize("color", WIDGET_COLORS)
def test_every_color_is_readable_with_white(color):
    assert contrast_with_white(color) >= 4.5


def test_the_default_is_one_of_them():
    assert DEFAULT_COLOR in WIDGET_COLORS
    assert Workspace._meta.get_field("color").default == DEFAULT_COLOR


def test_an_owner_picks_a_listed_color(api, workspace):
    response = api.patch(f"/workspaces/{workspace.id}", {"color": "#0F766E"})
    assert response.status_code == 200
    assert response.json()["color"] == "#0f766e"


@pytest.mark.parametrize("color", ["#ffff00", "teal", "", "#0f766e;"])
def test_any_other_color_is_refused(api, workspace, color):
    before = workspace.color
    response = api.patch(f"/workspaces/{workspace.id}", {"color": color})
    assert response.status_code == 400
    workspace.refresh_from_db()
    assert workspace.color == before


def test_a_color_from_before_the_list_survives_saving_other_settings(api, workspace):
    Workspace.objects.filter(pk=workspace.pk).update(color="#1E6FD9")
    response = api.patch(f"/workspaces/{workspace.id}", {"color": "#1E6FD9", "greeting": "Hello"})
    assert response.status_code == 200
    assert response.json()["color"] == "#1E6FD9"
    assert response.json()["greeting"] == "Hello"


def test_null_leaves_the_color_alone(api, workspace):
    response = api.patch(f"/workspaces/{workspace.id}", {"color": None})
    assert response.status_code == 200
    assert response.json()["color"] == workspace.color


def test_the_demo_workspaces_use_listed_colors():
    source = open(seed_demo.__file__, encoding="utf-8").read()
    used = [line.split('"')[3] for line in source.splitlines() if line.strip().startswith('"color":')]
    assert used and set(used) <= set(WIDGET_COLORS)
