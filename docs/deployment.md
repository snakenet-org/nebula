# Deployment

## Running the Docker image

```bash
docker run -d \
  --name nebular \
  -p 8000:8000 \
  -v nebular-data:/data \
  -e NEBULAR_MASTER_KEY="$(openssl rand -base64 32)" \
  -e NEBULAR_TOKEN="$(openssl rand -base64 32)" \
  -e NEBULAR_JWT_SECRET="$(openssl rand -base64 32)" \
  -e NEBULAR_ADMIN_USER=admin \
  -e NEBULAR_ADMIN_PASS=change-me \
  scr.snakenet.io/nebular:latest
```

The `/data` volume is required for persistence — it holds the embedded PostgreSQL cluster (see
below). Without a mounted volume, every secret is lost the moment the container is recreated.

## Embedded PostgreSQL

Unlike every sibling snakeNet.org service, Nebular Vault runs its own PostgreSQL 17 instance
**inside the same container**, started by `entrypoint.sh` before the API:

1. Fails fast if `NEBULAR_MASTER_KEY` or `NEBULAR_TOKEN` is unset — before touching Postgres at all.
2. On first boot (`$PGDATA/PG_VERSION` absent), runs `initdb` with UTF-8 encoding, then creates the
   `nebular` role's password and the `nebular` database.
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
container's persistent volume.

## Required environment variables

Only two variables have no safe default — the container refuses to start without them:

| Variable | Purpose |
|---|---|
| `NEBULAR_MASTER_KEY` | Encrypts every secret value at rest. **Losing this makes all data permanently unrecoverable.** See [encryption.md](encryption.md). |
| `NEBULAR_TOKEN` | The shared `X-Nebular-Token` secret required on every API call. |

Everything else has a working default — see [`.env.example`](../.env.example) for the full list
with explanations, grouped by area (server, the optional local admin login, Authentik OIDC, login
screen feature flags, PostgreSQL, the data folder).

Notable ones:

| Variable | Default | Purpose |
|---|---|---|
| `NEBULAR_JWT_SECRET` | *(unset)* | Signs locally minted session tokens — required if the local admin login is used. |
| `NEBULAR_ADMIN_USER` / `_PASS` / `_EMAIL` | *(unset)* | Seeds a bootstrap admin account once, on first start, iff no users exist yet. |
| `NEBULAR_BASIC_LOGIN_DISABLED` | `no` | Hide the username/password form once Authentik is fully set up. |
| `NEBULAR_OIDC_LOGIN_DISABLED` | `yes` | Set to `no` to show "Sign in with snakeNet ID". |
| `NEBULAR_OIDC_JWKS_URL` / `_ISSUER` / `_CLIENT_ID` | *(unset)* | Authentik application details — see below. |
| `NEBULAR_POSTGRES_*` | matches the embedded Postgres defaults | Only override for local development against an external Postgres. |

## Setting up the Authentik application

1. In Authentik, create a new OAuth2/OIDC **Provider**, application slug `nebular`, redirect URI
   `https://<your-host>/reentry`.
2. Create the matching **Application**, and two groups: `nebular-admin` and `nebular-user` (see
   [architecture.md](architecture.md) — group membership maps directly to entitlements).
3. Set `NEBULAR_OIDC_CLIENT_ID` to the provider's client id, `NEBULAR_OIDC_JWKS_URL`/`_ISSUER` to its
   JWKS/issuer URLs, and `NEBULAR_OIDC_LOGIN_DISABLED=no`.
4. Assign users to `nebular-admin`/`nebular-user` as appropriate. A user in neither group can
   authenticate against Authentik successfully but will be rejected by Nebular Vault itself (no
   entitlements → no access).

## Building from source

```bash
uv sync
cd frontend && npm install && npm run build && cd ..
alembic upgrade head   # against a Postgres you point NEBULAR_POSTGRES_* at
uv run main.py
```

## Release flow (GitHub Actions)

Pushing a tag matching `X.Y.Z` or `X.Y.Z-rcN` triggers
[`.github/workflows/build.yml`](../.github/workflows/build.yml): builds the multi-arch
(`linux/amd64`, `linux/arm64`) image and pushes it to the snakeNet container registry, tagged both
with the version and `latest`. The workflow deliberately stops at build+push — it does not yet
notify or auto-deploy anywhere, since Nebular Vault isn't registered in Gravity/Satellite with real
secrets/push-topic-ids. See the workflow file's own header comment for what to add once it is.
