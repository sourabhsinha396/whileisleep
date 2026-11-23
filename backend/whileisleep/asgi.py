"""ASGI entry point, for the stream process: `uvicorn whileisleep.asgi:application`.

It serves the live streams (apps/realtime/views.py), async views that hold one connection
per open widget or inbox while they wait on Redis. The REST API runs on WSGI (gunicorn,
wsgi.py); the reverse proxy sends only the stream paths here.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "whileisleep.settings.local")

application = get_asgi_application()
