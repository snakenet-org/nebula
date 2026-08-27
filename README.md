<div align="center">

# 🌌 Nebula Vault

**A self-hosted secrets manager for snakeNet.org.**

</div>

---

## What is Nebula Vault?

Nebula is a secrets manager you run yourself: projects hold your secrets and environment
variables, environments keep production, staging, and everything else cleanly separated, and
every value is encrypted at rest under a key only you hold.

It was built as a free, open-source, self-hosted alternative to commercial secrets managers — no
per-seat pricing, no vendor lock-in, and no secret ever leaves infrastructure you control.

The data model is simple and maps directly onto how real applications actually configure
themselves:

- A **Project** is a bucket for one application/service's secrets (e.g. "billing-api").
- **Environments** (`production`, `staging`, `development`, ...) are global and shared across
  every Project.
- A Project has any number of **Keys** — plain, readable names like `DATABASE_URL` or
  `STRIPE_SECRET_KEY` — each linked to exactly one Environment and holding its own encrypted
  value.
- A Key's value can also be a **live reference** to another Key elsewhere in the vault — rotate
  the source once, and every place that references it updates instantly.

Every value is encrypted at rest with a master encryption key that **you** provide when you start
the container. Nebula Vault's own database is never a copy/paste target for that key — it's read
once from the environment and never written anywhere itself. See
[docs/encryption.md](docs/encryption.md) for exactly how that works, and its one real limitation
(rotating the key is destructive today).

## Who can see what

- Sign-in is via **snakeNet ID** (Authentik SSO), same as every other snakeNet.org app, with an
  optional local admin login as a fallback (handy for first boot, before Authentik groups exist).
- A `nebula-user` can create their own Projects and see only what they own or what's been
  explicitly **shared** with them.
- A `nebula-admin` can see and manage every Project.
- Sharing a Project grants either **Viewer** (read the structure, values stay masked) or **Editor**
  (create/edit Environments, Keys, and Values) access. Only the Project's **owner or an admin** can
  ever reveal a value's plaintext, manage sharing, manage API access keys, or delete the Project —
  regardless of Editor status. This is deliberate: an Editor can rotate a secret without ever seeing
  what the old one was.
- Every value is hidden by default in the UI (`••••••••`) — a Reveal button fetches and displays the
  plaintext on demand, for those allowed to see it.

## The REST API (for your deploy pipeline)

Every Project can generate any number of **API access keys** — long-lived credentials scoped to
that one Project, used by scripts/CI/containers to pull secrets at deploy time without a human
session.

Two things are required on every API call, mirroring the shared-secret + per-resource-credential
pattern used across snakeNet.org's other internal services (Satellite, Gravity):

1. `X-Nebula-Token` — a site-wide shared secret, set once when you spawn the container
   (`NEBULA_TOKEN`). Proves the caller is allowed to talk to this Nebula Vault instance at all.
2. `Authorization: Bearer <project access key>` — proves which Project, and that the caller was
   explicitly granted access to it.

```bash
curl "https://your-nebula-host/api/v1/vault/secret?key=DATABASE_URL&environment=production" \
  -H "X-Nebula-Token: $NEBULA_TOKEN" \
  -H "Authorization: Bearer nbv_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

```json
{ "key": "DATABASE_URL", "environment": "production", "value": "postgres://..." }
```

Full route reference: [docs/api.md](docs/api.md).

## Running it

Nebula Vault ships as two Docker image variants, built from the same source and always versioned
identically:

- **`nebula`** (the default, also tagged `:latest`) — the **lite** image. No embedded database;
  point it at a PostgreSQL instance you already run.
- **`nebula-aio`** — the **all-in-one** image. The FastAPI backend, the built Vue frontend, and its
  own embedded PostgreSQL 17 instance all run in one container, no separate database container to
  stand up.

```bash
# Lite (default) — bring your own PostgreSQL
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

```bash
# All-in-one — embedded PostgreSQL, no external database needed
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

`NEBULA_MASTER_KEY` and `NEBULA_TOKEN` are the two variables neither image will start without —
everything else has a working default. **Write down `NEBULA_MASTER_KEY` somewhere safe.
If you lose it, every stored secret becomes permanently unrecoverable** (there's no backdoor —
that's the point of encryption). The lite image needs `NEBULA_POSTGRES_*` pointed at a real
database; the all-in-one image needs its `/data` volume mounted persistently, since that's where
the embedded Postgres cluster lives.

Full deployment reference (every environment variable, the Authentik application setup, building
from source): [docs/deployment.md](docs/deployment.md).

## Documentation

- [docs/architecture.md](docs/architecture.md) — module map, request flow, why the pieces are
  shaped the way they are.
- [docs/encryption.md](docs/encryption.md) — the master-key/Fernet design, what's encrypted vs.
  cleartext, and the key-rotation limitation.
- [docs/api.md](docs/api.md) — every `/api/v1/*` route, request/response shapes, and the three
  distinct auth modes (human session, local admin, project access key).
- [docs/deployment.md](docs/deployment.md) — running the Docker image, every env var, and the
  GitHub Actions release flow.

## Stack

FastAPI · Vue 3 (SPA) · Tailwind CSS · PostgreSQL 17 (embedded in the `nebula-aio` image, external
for `nebula`) · SQLAlchemy (async) + Alembic · Authentik (OIDC) · Python 3.14, `uv`.

---

<div align="center">

© snakeNet.org, All rights reserved

Made with ❤️ by the snakeNet.org Team, Claude AI, and Google Gemini.

</div>
