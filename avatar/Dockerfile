# Avatar service: the HTTP API (target "api") and the LiveKit agent (target "agent").
# Build from the repo root, since the services share ../shared:
#   docker build -f avatar/Dockerfile --target api   -t alex-api .
#   docker build -f avatar/Dockerfile --target agent -t alex-agent .
# Base images are pinned by digest; update them deliberately (see docs/DEPLOY.md).

ARG PYTHON_IMAGE=python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105

FROM ${UV_IMAGE} AS uv

# ---- dependencies, from the lock file ---------------------------------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY shared /src/shared
COPY avatar/pyproject.toml avatar/uv.lock /src/avatar/
WORKDIR /src/avatar
# --no-editable installs ../shared as a regular package, so the runtime image
# needs only the virtualenv and this service's code
RUN uv sync --frozen --no-dev --no-install-project --no-editable

# ---- common runtime ----------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
RUN useradd --uid 10001 --user-group --create-home --shell /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
COPY avatar /app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# ---- HTTP API ----------------------------------------------------------------
FROM runtime AS api
# OCR for resume uploads
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*
USER app
EXPOSE 8001
# Liveness only; load balancers should use GET /ready (checks Redis + Postgres)
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2)"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--no-server-header", "--timeout-graceful-shutdown", "30"]

# ---- LiveKit agent -----------------------------------------------------------
FROM runtime AS agent
ENV HF_HOME=/home/app/.cache/huggingface
USER app
# Bake model files (VAD, turn detector, ...) into the image instead of
# downloading them when the first interview starts
RUN python -m livekit.agents download-files
EXPOSE 8081
# 200 once connected to LiveKit (port: AGENT_HEALTH_PORT)
HEALTHCHECK --interval=15s --timeout=3s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/', timeout=2)"]
# `start`, not `dev`: production mode, and SIGTERM drains running interviews
# (AGENT_DRAIN_TIMEOUT_SECONDS) before exiting
CMD ["python", "-m", "agents.entrypoint", "start"]
