# Brain worker. Build from the repo root, since the services share ../shared:
#   docker build -f worker/Dockerfile -t alex-worker .
# Candidate code does NOT run in this container: in SANDBOX_MODE=docker the
# worker starts a throwaway container per test case on the Docker daemon at
# DOCKER_HOST (a separate, isolated daemon — never mount the host's socket).

ARG PYTHON_IMAGE=python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105
ARG DOCKER_CLI_IMAGE=docker:27-cli@sha256:851f91d241214e7c6db86513b270d58776379aacc5eb9c4a87e5b47115e3065c

FROM ${UV_IMAGE} AS uv
FROM ${DOCKER_CLI_IMAGE} AS docker-cli

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY shared /src/shared
COPY worker/pyproject.toml worker/uv.lock /src/worker/
WORKDIR /src/worker
RUN uv sync --frozen --no-dev --no-install-project --no-editable

FROM ${PYTHON_IMAGE}
RUN useradd --uid 10001 --user-group --create-home --shell /usr/sbin/nologin app
# Only the client binary: the worker talks to the sandbox daemon over DOCKER_HOST
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=build /opt/venv /opt/venv
COPY worker /app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
USER app
# Ready = Redis reachable, schema current, consumer group joined, heartbeat fresh
HEALTHCHECK --interval=15s --timeout=3s --start-period=60s --retries=3 \
    CMD ["python", "-m", "core.readiness"]
# On SIGTERM the worker finishes its current message, then exits; give it a
# stop grace period longer than one turn (compose: stop_grace_period)
CMD ["python", "worker.py"]
