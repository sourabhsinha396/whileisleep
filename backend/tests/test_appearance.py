"""The widget's header pattern and color mode."""

import pytest

from apps.workspaces.models import WidgetBackground

from .conftest import Api

pytestmark = pytest.mark.django_db


def config(workspace) -> dict:
    return Api().get(f"/widget/{workspace.public_key}/config").json()


def test_a_new_workspace_is_plain_and_light(workspace):
    assert (config(workspace)["background"], config(workspace)["color_mode"]) == ("plain", "light")


@pytest.mark.parametrize("background", WidgetBackground.values)
def test_an_owner_picks_a_background(api, workspace, background):
    response = api.patch(f"/workspaces/{workspace.id}", {"background": background})
    assert response.json()["background"] == background
    assert config(workspace)["background"] == background


@pytest.mark.parametrize("mode", ["light", "dark", "auto"])
def test_an_owner_picks_a_color_mode(api, workspace, mode):
    assert api.patch(f"/workspaces/{workspace.id}", {"color_mode": mode}).json()["color_mode"] == mode
    assert config(workspace)["color_mode"] == mode


@pytest.mark.parametrize(
    "change", [{"background": "url(x)"}, {"background": "grid"}, {"background": ""}, {"color_mode": "pink"}]
)
def test_anything_else_is_refused(api, workspace, change):
    assert api.patch(f"/workspaces/{workspace.id}", change).status_code == 422


def test_nothing_chosen_changes_nothing(api, workspace):
    api.patch(f"/workspaces/{workspace.id}", {"background": "night", "color_mode": "dark"})
    body = api.patch(f"/workspaces/{workspace.id}", {"background": None, "color_mode": None, "greeting": "Hey"}).json()
    assert (body["background"], body["color_mode"], body["greeting"]) == ("night", "dark", "Hey")
