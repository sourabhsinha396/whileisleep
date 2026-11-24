"""What a new workspace still has to set up, for the dashboard's "Get started" guide.

Each step is done when the thing itself is there, never because someone ticked a box. Nothing
here is required: the product works while steps are open, only with less.
"""

from django.db.models import Q

from .models import Workspace


def steps(workspace: Workspace) -> list[dict]:
    """In the order to do them."""
    done = {
        "install": installed(workspace),
        "ai": workspace.organization.llm_ready,
        "chat": workspace.conversations.filter(messages__sender="visitor").exists(),
        "storage": workspace.organization.storage_bucket is not None,
    }
    return [{"key": key, "done": value} for key, value in done.items()]


def installed(workspace: Workspace) -> bool:
    """The widget has been loaded on a page that isn't the dashboard's own test page."""
    test_page = Q(current_url__contains=f"/demo?key={workspace.public_key}")
    return workspace.visitors.exclude(test_page).exclude(current_url="").exists()
