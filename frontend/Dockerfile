# Frontend: production build served by an unprivileged nginx that also proxies
# /api to the API, so the browser sees one origin (the session cookie is
# SameSite=Strict and the app calls relative /api URLs).
# Build from the repo root:  docker build -f frontend/Dockerfile -t alex-frontend .
#
# Runtime settings (environment variables):
#   API_UPSTREAM     where /api goes, e.g. http://api:8001
#   CSP_CONNECT_SRC  extra connect-src origins (LiveKit), default *.livekit.cloud

ARG NODE_IMAGE=node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.27-alpine@sha256:65e3e85dbaed8ba248841d9d58a899b6197106c23cb0ff1a132b7bfe0547e4c0

FROM ${NODE_IMAGE} AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM ${NGINX_IMAGE}
ENV API_UPSTREAM=http://api:8001 \
    CSP_CONNECT_SRC="wss://*.livekit.cloud https://*.livekit.cloud"
COPY frontend/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
