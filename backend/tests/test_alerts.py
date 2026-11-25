"""How the dashboard alerts the team: the organization's settings, read by every teammate."""

import pytest

from apps.workspaces.models import Membership

from .conftest import Api
from .factories import AuthTokenFactory, MembershipFactory

pytestmark = pytest.mark.django_db

DEFAULTS = {"alert_sound": "chime", "alert_volume": 60, "alert_on": "person", "alert_repeat": 0}
CHOSEN = {"alert_sound": "bell", "alert_volume": 0, "alert_on": "all", "alert_repeat": 30}


def alerts(row: dict) -> dict:
    return {key: row[key] for key in DEFAULTS}


def test_the_owner_chooses_and_the_rest_stays(api, membership):
    assert alerts(api.get("/organization").json()) == DEFAULTS
    assert alerts(api.patch("/organization", CHOSEN).json()) == CHOSEN
    saved = api.patch("/organization", {"name": "Acme", "alert_volume": None, "alert_sound": None}).json()
    assert alerts(saved) == CHOSEN


@pytest.mark.parametrize(
    "bad", [{"alert_sound": "foghorn"}, {"alert_volume": 101}, {"alert_on": "none"}, {"alert_repeat": 1}]
)
def test_only_what_the_dashboard_can_do(api, membership, bad):
    assert api.patch("/organization", bad).status_code == 422


def test_every_teammate_hears_the_same(workspace):
    organization = workspace.organization
    for field, value in CHOSEN.items():
        setattr(organization, field, value)
    organization.save()
    agent = MembershipFactory(workspace=workspace, role=Membership.Role.AGENT).user
    rows = Api(AuthTokenFactory(user=agent).key).get("/workspaces").json()
    assert [alerts(row) for row in rows] == [CHOSEN]
