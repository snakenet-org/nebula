#!/bin/sh
#
#   snakeNet.org Nebula Vault Entrypoint — Lite (nebula) variant, the default
#       Author: Marc Fiedler <marc@snakenet.org>
#
# Unlike entrypoint.aio.sh (the all-in-one variant), this image owns no database lifecycle at all —
# it only ever talks to Postgres over the network via NEBULA_POSTGRES_* (see nebula.config), so this
# script is just: fail-fast checks -> migrate -> run. Still needs the same background+wait signal
# handling as the AIO entrypoint so `docker stop`/`restart` shuts down promptly instead of sitting on
# SIGTERM until Docker's grace period force-SIGKILLs everything.
set -e

# Fail fast on the required secrets/config, before anything else runs.
if [ -z "$NEBULA_MASTER_KEY" ]; then
  echo "FATAL: NEBULA_MASTER_KEY is not set. Refusing to start." >&2
  exit 1
fi
if [ -z "$NEBULA_TOKEN" ]; then
  echo "FATAL: NEBULA_TOKEN is not set. Refusing to start." >&2
  exit 1
fi
# This image has no embedded database (see the sibling `nebula-aio` image for that) — it must be
# pointed at a real, already-running PostgreSQL instance. Checked here, against the raw env var,
# rather than relying on nebula.config's own "localhost" default, since silently trying (and
# failing) to reach a Postgres on localhost inside this container is a confusing failure mode next
# to a clear, immediate error telling the operator what's actually missing.
if [ -z "$NEBULA_POSTGRES_HOST" ]; then
  echo "FATAL: NEBULA_POSTGRES_HOST is not set. This is the 'lite' Nebula Vault image — it has no" >&2
  echo "       embedded database. Point NEBULA_POSTGRES_HOST (and _PORT/_DB/_USER/_PASSWORD as" >&2
  echo "       needed) at a PostgreSQL instance you already run, or use the 'nebula-aio' image" >&2
  echo "       instead, which bundles its own." >&2
  exit 1
fi

# Stop the app + rotation daemon cleanly on container shutdown (same trap-on-EXIT cleanup pattern as
# entrypoint.aio.sh/Gravity's scheduler.py entrypoint) — APP_PID/ROTATOR_PID are set once their
# respective `uv run` commands start below; guarded since a signal could in principle arrive before
# then.
shutdown() {
  [ -n "$APP_PID" ] && kill -TERM "$APP_PID" 2>/dev/null && wait "$APP_PID" 2>/dev/null
  [ -n "$ROTATOR_PID" ] && kill -TERM "$ROTATOR_PID" 2>/dev/null && wait "$ROTATOR_PID" 2>/dev/null
}
trap shutdown EXIT INT TERM

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
# SIGKILLs everything instead of shutting down promptly. `wait` on a background job's pid, unlike a
# plain foreground command, IS interruptible immediately by a trapped signal, which is what lets
# `shutdown` actually run promptly.
echo "Starting Nebula Vault..."
uv run main.py &
APP_PID=$!
wait "$APP_PID"
