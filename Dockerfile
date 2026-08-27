#     (c) snakenet.org, All rights reserved
#         Nebula Vault Dockerfile — Lite (nebula) variant, the default
#
# Nebula Vault is a FastAPI/uvicorn service that serves both the JSON API and the built static SPA
# portal (from /nebula/public). This is the "lite" image variant — the default, published as
# `nebula` (and tagged `:latest`): it has NO embedded database, unlike the sibling `nebula-aio`
# image (see Dockerfile.aio) — point NEBULA_POSTGRES_* at a PostgreSQL instance you already run.
# This keeps the image small and lets it scale/back up independently of its database, at the cost
# of needing that external Postgres yourself. TLS termination + reverse proxying are still handled
# externally by Traefik. The Vue frontend is built in a separate Node stage and copied into the
# final image.
#
# Both variants are built from the same source, versioned identically, and published under
# different image names (`nebula` here, `nebula-aio` for the all-in-one variant); see
# .github/workflows/build.yml.

# ── Stage 1: build the Vite frontend ────────────────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# Vite is configured to emit the production build into ../public (see vite.config.js).
RUN npm run build

# ── Stage 2: the Python API only — no embedded PostgreSQL ───────────────────
# Same Debian-based `uv` image as the all-in-one variant, for consistency between the two — this
# variant doesn't strictly need Debian specifically (no PGDG apt package involved here), but sharing
# a base image keeps behavior identical across both.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /nebula

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Berlin \
    DEBIAN_FRONTEND=noninteractive \
    NEBULA_HOST=0.0.0.0 \
    NEBULA_PORT=8000

# GitHub CLI (`gh`) — nebula.github_sync shells out to it for the Project "Sync to GitHub" feature;
# installed from GitHub's own official apt repo, signed-repo pattern. No PostgreSQL server package
# here at all — this image only ever speaks to Postgres over the network via asyncpg (a pure-Python
# driver), so no `postgresql-client` is needed either.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates tzdata curl gnupg && \
    install -d /etc/apt/keyrings && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] \
      https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y --no-install-recommends gh && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer) without building the project itself.
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev

# Bundle the application source.
COPY main.py alembic.ini README.md ./
COPY src/ src/
COPY migrations/ migrations/
COPY scripts/ scripts/
COPY entrypoint.lite.sh ./

# Install the project itself now that the source is present.
RUN uv sync --frozen --no-dev

# Bring in the built frontend from stage 1 (Vite emits to /public — outDir ../public from /build).
COPY --from=frontend /public ./public

# FastAPI/uvicorn listens here; Traefik proxies to this port.
EXPOSE 8000

ENTRYPOINT ["sh", "./entrypoint.lite.sh"]
