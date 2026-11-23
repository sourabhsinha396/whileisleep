from django.contrib import admin
from django.urls import path

from apps.realtime import views as realtime

from .api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    # Live streams: async views for the ASGI process (apps/realtime/views.py). Before the
    # Ninja API, which would otherwise claim these paths.
    path("api/v1/widget/<str:key>/stream", realtime.widget_stream),
    path("api/v1/workspaces/<int:workspace_id>/stream", realtime.inbox_stream),
    path("api/", api.urls),
]
