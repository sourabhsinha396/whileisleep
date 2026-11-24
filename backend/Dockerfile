FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# collectstatic writes here in production (not in /app, where compose mounts the code); the
# app user must own it.
RUN useradd --create-home app && mkdir -p /opt/static && chown app:app /opt/static
USER app

EXPOSE 8000

# Compose picks this or the development server (docker-compose.yaml).
# Threads rather than more processes: requests mostly wait on the database and the LLM.
CMD ["gunicorn", "whileisleep.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "8", "--timeout", "90", "--access-logfile", "-"]
