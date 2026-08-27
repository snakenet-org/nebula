# Deployment

## Two image variants

Nebula Vault is built from the same source into two image variants, always versioned identically
but published under different names:

| Image | Default? | Database | Dockerfile | Entrypoint |
|---|---|---|---|---|
| `nebula` | Yes — also tagged `:latest` | External PostgreSQL you provide | [`Dockerfile`](../Dockerfile) | [`entrypoint.lite.sh`](../entrypoint.lite.sh) |
| `nebula-aio` | No — version tag only | Embedded PostgreSQL 17 | [`Dockerfile.aio`](../Dockerfile.aio) | [`entrypoint.aio.sh`](../entrypoint.aio.sh) |

Pick `nebula` if you already run Postgres somewhere (a managed database, an existing cluster) and
want the smaller image; pick `nebula-aio` for a single self-contained container with nothing else
to stand up.

## Running the Lite image (`nebula`, default)

```bash
docker run -d \
  --name nebula \
  -p 8000:8000 \
  -e NEBULA_MASTER_KEY="$(openssl rand -base64 32)" \
  -e NEBULA_TOKEN="$(openssl rand -base64 32)" \
  -e NEBULA_JWT_SECRET="$(openssl rand -base64 32)" \
  -e NEBULA_ADMIN_USER=admin \
  -e NEBULA_ADMIN_PASS=change-me \
  -e NEBULA_POSTGRES_HOST=your-postgres-host \
  -e NEBULA_POSTGRES_PASSWORD=your-postgres-password \
  scr.snakenet.io/nebula:latest
```

`entrypoint.lite.sh` fails fast if `NEBULA_POSTGRES_HOST` is unset — this image has no embedded
database to fall back to. Point the full `NEBULA_POSTGRES_*` group at a real, already-running
PostgreSQL instance, then it runs `alembic upgrade head` and starts the app directly.

## Running the All-in-One image (`nebula-aio`)

```bash
docker run -d \
  --name nebula \
  -p 8000:8000 \
  -v nebula-data:/data \
  -e NEBULA_MASTER_KEY="$(openssl rand -base64 32)" \
  -e NEBULA_TOKEN="$(openssl rand -base64 32)" \
  -e NEBULA_JWT_SECRET="$(openssl rand -base64 32)" \
  -e NEBULA_ADMIN_USER=admin \
  -e NEBULA_ADMIN_PASS=change-me \
  scr.snakenet.io/nebula-aio:<version>
```

The `/data` volume is required for persistence — it holds the embedded PostgreSQL cluster (see
below). Without a mounted volume, every secret is lost the moment the container is recreated.

## Embedded PostgreSQL (`nebula-aio` only)

Unlike every sibling snakeNet.org service — and unlike its own sibling `nebula` image above —
`nebula-aio` runs its own PostgreSQL 17 instance **inside the same container**, started by
`entrypoint.aio.sh` before the API:

1. Fails fast if `NEBULA_MASTER_KEY` or `NEBULA_TOKEN` is unset — before touching Postgres at all.
2. On first boot (`$PGDATA/PG_VERSION` absent), runs `initdb` with UTF-8 encoding, then creates the
   `nebula` role's password and the `nebula` database.
3. Starts Postgres bound to `127.0.0.1` only — it never listens on a published port; the only way to
   reach it is from inside the same container.
4. Runs `alembic upgrade head`.
5. Starts the FastAPI app.

On `docker stop`/`restart`, a shutdown trap stops Postgres cleanly (`pg_ctl ... stop -m fast`)
before the container exits, so a normal stop/restart never leaves the data directory in an unclean
shutdown state.

This trades the usual "separate database container" flexibility (independent scaling, external
backups via your Postgres tooling of choice, swapping in a managed database) for genuine
single-container simplicity — reasonable for a self-hosted internal tool where "one container, one
volume" is the whole point. Back up the `/data` volume the same way you'd back up any other
container's persistent volume. If you'd rather keep that flexibility, use the `nebula` (lite) image
instead.

## Required environment variables

Only two variables have no safe default on either image — the container refuses to start without
them:

| Variable | Purpose |
|---|---|
| `NEBULA_MASTER_KEY` | Encrypts every secret value at rest. **Losing this makes all data permanently unrecoverable.** See [encryption.md](encryption.md). |
| `NEBULA_TOKEN` | The shared `X-Nebula-Token` secret required on every API call. |

The `nebula` (lite) image has one more: `NEBULA_POSTGRES_HOST` must point at a real database — it
has no embedded fallback.

Everything else has a working default — see [`.env.example`](../.env.example) for the full list
with explanations, grouped by area (server, the optional local admin login, Authentik OIDC, login
screen feature flags, PostgreSQL, the data folder).

Notable ones:

| Variable | Default | Purpose |
|---|---|---|
| `NEBULA_JWT_SECRET` | *(unset)* | Signs locally minted session tokens — required if the local admin login is used. |
| `NEBULA_ADMIN_USER` / `_PASS` / `_EMAIL` | *(unset)* | Seeds a bootstrap admin account once, on first start, iff no users exist yet. |
| `NEBULA_BASIC_LOGIN_DISABLED` | `no` | Hide the username/password form once Authentik is fully set up. |
| `NEBULA_OIDC_LOGIN_DISABLED` | `yes` | Set to `no` to show "Sign in with snakeNet ID". |
| `NEBULA_OIDC_JWKS_URL` / `_ISSUER` / `_CLIENT_ID` | *(unset)* | Authentik application details — see below. |
| `NEBULA_POSTGRES_*` | matches `nebula-aio`'s embedded Postgres | Required on the `nebula` (lite) image — point at your real database. Only override on `nebula-aio` for local development against an external Postgres instead of the embedded one. |

## Setting up the Authentik application

1. In Authentik, create a new OAuth2/OIDC **Provider**, application slug `nebula`, redirect URI
   `https://<your-host>/reentry`.
2. Create the matching **Application**, and two groups: `nebula-admin` and `nebula-user` (see
   [architecture.md](architecture.md) — group membership maps directly to entitlements).
3. Set `NEBULA_OIDC_CLIENT_ID` to the provider's client id, `NEBULA_OIDC_JWKS_URL`/`_ISSUER` to its
   JWKS/issuer URLs, and `NEBULA_OIDC_LOGIN_DISABLED=no`.
4. Assign users to `nebula-admin`/`nebula-user` as appropriate. A user in neither group can
   authenticate against Authentik successfully but will be rejected by Nebula Vault itself (no
   entitlements → no access).

## Building from source

```bash
uv sync
cd frontend && npm install && npm run build && cd ..
alembic upgrade head   # against a Postgres you point NEBULA_POSTGRES_* at
uv run main.py
```

## Release flow (GitHub Actions)

Pushing a tag matching `X.Y.Z` or `X.Y.Z-rcN` triggers
[`.github/workflows/build.yml`](../.github/workflows/build.yml): builds and pushes both images to
the snakeNet container registry, each tagged with the version and its own `:latest` (`nebula:latest`
and `nebula-aio:latest` are independent floating tags in their own image repos) — then auto-deploys
`nebula-aio` via Satellite (this app's own ops.snakenet.io instance already runs on the
embedded-Postgres image) and notifies Pulsar.
