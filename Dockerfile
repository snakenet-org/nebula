#     (c) snakenet.org, All rights reserved
#         Nebular Vault Dockerfile
#
# Nebular Vault is a FastAPI/uvicorn service that serves both the JSON API and the built static SPA
# portal (from /nebular/public). Unlike every sibling snakeNet app (Gravity/Satellite/Singularity),
# this image bundles its OWN PostgreSQL 17 instance — Nebular Vault is meant to run as a single,
# self-contained container with no external database dependency (see entrypoint.sh). TLS termination
# + reverse proxying are still handled externally by Traefik. The Vue frontend is built in a
# separate Node stage and copied into the final image.

# ── Stage 1: build the Vite frontend ────────────────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
# Vite is configured to emit the production build into ../public (see vite.config.js).
RUN npm run build

# ── Stage 2: the Python API + embedded PostgreSQL 17 ────────────────────────
# Debian, not Alpine (unlike every sibling app's uv base image): PostgreSQL 17 exact-version packages
# come from the official PGDG apt repository, which only targets Debian/Ubuntu — Alpine has no PGDG
# equivalent, and its own community repo tracks whichever PG version its release cycle bundles, not
# necessarily 17.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /nebular

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Berlin \
    DEBIAN_FRONTEND=noninteractive \
    NEBULAR_HOST=0.0.0.0 \
    NEBULAR_PORT=8000 \
    NEBULAR_DATA_FOLDER=/data \
    PGDATA=/data/postgres \
    PATH="/usr/lib/postgresql/17/bin:${PATH}"

# Install PostgreSQL 17 from the official PGDG apt repository, plus gosu — the standard technique the
# official postgres Docker image itself uses to cleanly drop from root to the `postgres` system user
# (created automatically by the postgresql-17 package) and back, since the app process runs as root
# (for `uv`) while Postgres itself must run as a non-root user.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates tzdata curl gnupg gosu && \
    install -d /usr/share/postgresql-common/pgdg && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc && \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
      https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list && \
    # Suppress postgresql-common's own automatic "main" cluster at /var/lib/postgresql/17/main —
    # entrypoint.sh creates its own cluster at $PGDATA (/data/postgres, a mounted volume) instead, so
    # the package-managed default cluster would just be dead weight baked into every image layer.
    mkdir -p /etc/postgresql-common && \
    echo "create_main_cluster = false" > /etc/postgresql-common/createcluster.conf && \
    apt-get update && apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17 && \
    rm -rf /var/lib/apt/lists/*

# The embedded Postgres data directory + Nebular's own data folder live here — see entrypoint.sh and
# NEBULAR_DATA_FOLDER. Mount this as a volume for durability across container recreation.
RUN mkdir -p /data

# Install Python dependencies first (cached layer) without building the project itself.
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev

# Bundle the application source.
COPY main.py alembic.ini README.md ./
COPY src/ src/
COPY migrations/ migrations/
COPY entrypoint.sh ./

# Install the project itself now that the source is present.
RUN uv sync --frozen --no-dev

# Bring in the built frontend from stage 1 (Vite emits to /public — outDir ../public from /build).
COPY --from=frontend /public ./public

# FastAPI/uvicorn listens here; Traefik proxies to this port. PostgreSQL never leaves the container
# (entrypoint.sh binds it to 127.0.0.1 only) — no port is exposed for it here.
EXPOSE 8000

VOLUME ["/data"]

ENTRYPOINT ["sh", "./entrypoint.sh"]
