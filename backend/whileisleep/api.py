from django.core.cache import cache
from django.db import connection
from ninja import NinjaAPI
from ninja.errors import HttpError

from apps.accounts.apis import router as auth_router
from apps.agent.apis import router as tools_router
from apps.agent.automation_apis import router as automation_router
from apps.agent.mcp_apis import router as mcp_router
from apps.agent.turn_apis import router as turns_router
from apps.billing.apis import router as billing_router
from apps.conversations.apis import router as inbox_router
from apps.conversations.widget_apis import router as widget_router
from apps.integrations.apis import router as integrations_router
from apps.knowledge.apis import router as knowledge_router
from apps.workspaces.apis import router as workspaces_router
from apps.workspaces.organization_apis import router as organization_router
from apps.workspaces.storage_apis import router as storage_router

api = NinjaAPI(title="whileisleep API", version="1")

api.add_router("v1/auth", auth_router)
api.add_router("v1", workspaces_router)
api.add_router("v1", organization_router)
api.add_router("v1", billing_router)
api.add_router("v1", storage_router)
api.add_router("v1", inbox_router)
api.add_router("v1", knowledge_router)
api.add_router("v1", tools_router)
api.add_router("v1", automation_router)
api.add_router("v1", mcp_router)
api.add_router("v1", turns_router)
api.add_router("v1", integrations_router)
api.add_router("v1/widget", widget_router)


@api.get("v1/health", tags=["health"])
def health(request):
    """The process is up. For container liveness checks."""
    return {"ok": True}


@api.get("v1/ready", tags=["health"])
def ready(request):
    """The process can do its job: the database and the cache answer. For load balancers
    and deploy scripts; 503 when it can't."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        cache.set("ready-check", 1, 5)
    except Exception as error:  # any failure here means "not ready"
        raise HttpError(503, f"Not ready: {type(error).__name__}") from error
    return {"ok": True}
