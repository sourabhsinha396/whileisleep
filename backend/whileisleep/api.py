from ninja import NinjaAPI

from apps.accounts.apis import router as auth_router
from apps.agent.apis import router as tools_router
from apps.agent.automation_apis import router as automation_router
from apps.conversations.apis import router as inbox_router
from apps.conversations.widget_apis import router as widget_router
from apps.knowledge.apis import router as knowledge_router
from apps.workspaces.apis import router as workspaces_router
from apps.workspaces.organization_apis import router as organization_router

api = NinjaAPI(title="whileisleep API", version="1")

api.add_router("v1/auth", auth_router)
api.add_router("v1", workspaces_router)
api.add_router("v1", organization_router)
api.add_router("v1", inbox_router)
api.add_router("v1", knowledge_router)
api.add_router("v1", tools_router)
api.add_router("v1", automation_router)
api.add_router("v1/widget", widget_router)


@api.get("v1/health", tags=["health"])
def health(request):
    return {"ok": True}
