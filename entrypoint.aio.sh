#!/bin/sh
#
#   snakeNet.org Nebula Vault Entrypoint — All-in-One (nebula-aio) variant
#       Author: Marc Fiedler <marc@snakenet.org>
#
# Unlike every sibling app's entrypoint.sh, this one also owns the embedded PostgreSQL 17 instance's
# entire lifecycle (init -> start -> stop) — see Dockerfile.aio's own header for why the all-in-one
# image variant bundles its own database instead of depending on an external one. See the sibling
# entrypoint.lite.sh (used by the default `Dockerfile`/`nebula` image) for the leaner variant that
# skips all of this and talks to an external Postgres instead.
set -e

# Fail fast on the two required secrets — before touching Postgres at all, so a misconfigured
# container never even gets as far as initializing a database it couldn't be used with anyway.
if [ -z "$NEBULA_MASTER_KEY" ]; then
  echo "FATAL: NEBULA_MASTER_KEY is not set. Refusing to start." >&2
  exit 1
fi
if [ -z "$NEBULA_TOKEN" ]; then
  echo "FATAL: NEBULA_TOKEN is not set. Refusing to start." >&2
  exit 1
fi

NEBULA_POSTGRES_DB="${NEBULA_POSTGRES_DB:-nebula}"
NEBULA_POSTGRES_USER="${NEBULA_POSTGRES_USER:-postgres}"
NEBULA_POSTGRES_PASSWORD="${NEBULA_POSTGRES_PASSWORD:-nebula}"
export NEBULA_POSTGRES_HOST="${NEBULA_POSTGRES_HOST:-localhost}"
export NEBULA_POSTGRES_PORT="${NEBULA_POSTGRES_PORT:-5432}"
export NEBULA_POSTGRES_DB NEBULA_POSTGRES_USER NEBULA_POSTGRES_PASSWORD

mkdir -p "$PGDATA"
chown -R postgres:postgres "$PGDATA"

# initdb only ever runs once — a re-created container that mounted the same /data volume already has
# a PG_VERSION file and skips straight to starting the existing cluster.
FIRST_BOOT=0
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  FIRST_BOOT=1
  echo "Initializing embedded PostgreSQL 17 data directory..."
  # This image has no generated locales (see Dockerfile) — initdb would otherwise fall back to the
  # "C" locale and default to SQL_ASCII encoding, which breaks storing any non-ASCII project/key
  # name or description. C.UTF-8 is a built-in glibc locale on Debian bookworm (glibc >= 2.35),
  # available with no locale-gen step, and gives real UTF8 encoding + sane collation.
  gosu postgres initdb -D "$PGDATA" --encoding=UTF8 --locale=C.UTF-8 \
    --auth-host=scram-sha-256 --auth-local=trust
fi

# Stop the app + rotation daemon + Postgres cleanly on container shutdown (same trap-on-EXIT cleanup
# pattern as Gravity's scheduler.py entrypoint) — APP_PID/ROTATOR_PID are set once their respective
# `uv run` commands start below; guarded since a signal could in principle arrive before then.
shutdown() {
  [ -n "$APP_PID" ] && kill -TERM "$APP_PID" 2>/dev/null && wait "$APP_PID" 2>/dev/null
  [ -n "$ROTATOR_PID" ] && kill -TERM "$ROTATOR_PID" 2>/dev/null && wait "$ROTATOR_PID" 2>/dev/null
  gosu postgres pg_ctl -D "$PGDATA" -m fast stop
}
trap shutdown EXIT INT TERM

echo "Starting embedded PostgreSQL..."
# Bound to 127.0.0.1 only — Postgres never leaves this container, no port is published for it.
gosu postgres pg_ctl -D "$PGDATA" -l "$PGDATA/postgres.log" -o "-c listen_addresses=127.0.0.1" -w start

if [ "$FIRST_BOOT" = "1" ]; then
  echo "Creating the Nebula Vault role password + database..."
  gosu postgres psql -v ON_ERROR_STOP=1 \
    -c "ALTER USER \"$NEBULA_POSTGRES_USER\" WITH PASSWORD '$NEBULA_POSTGRES_PASSWORD';"
  gosu postgres createdb -O "$NEBULA_POSTGRES_USER" "$NEBULA_POSTGRES_DB"
fi

# Apply any pending database migrations before the app starts. Idempotent: a DB already at head is a
# no-op. Schema is owned by Alembic (the app does not run create_all on startup).
echo "Applying database migrations..."
uv run alembic upgrade head

# The hourly automatic secret-rotation daemon (scripts/rotate_secrets.py) — its own OS process, same
# "a crash/hang in the loop must never take the API down with it" reasoning as Gravity's own
# scheduler.py, backgrounded before the app so it's already ticking by the time requests arrive.
echo "Starting Nebula Vault secret-rotation daemon..."
uv run scripts/rotate_secrets.py &
ROTATOR_PID=$!

# Run the API + portal in the BACKGROUND, then `wait` on it — not a plain foreground command, and
# not exec'd. POSIX sh only delivers a trapped signal once the shell's current foreground command
# exits; `docker stop`/`restart` sends SIGTERM to this script (PID 1), and a plain foreground `uv
# run main.py` would sit on that signal until Docker's shutdown grace period expires and forcibly
# SIGKILLs everything — leaving Postgres stopped uncleanly (a stale postmaster.pid, "another server
# might be running" on the next start) instead of via the trap's own `pg_ctl stop`. `wait` on a
# background job's pid, unlike a plain foreground command, IS interruptible immediately by a
# trapped signal, which is what lets `shutdown` actually run promptly.
echo "Starting Nebula Vault..."
uv run main.py &
APP_PID=$!
wait "$APP_PID"
