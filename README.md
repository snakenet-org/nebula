<div align="center">

# 🌌 Nebula Vault

**A self-hosted secrets manager for snakeNet.org.**

Projects → Environments → Keys → per-environment Values, encrypted at rest under a master key
only you hold.

</div>

---

## What is Nebula Vault?

Nebula Vault stores credentials, passwords, logins, and environment variables so your team (and
your deploy pipelines) don't have to pass them around as plaintext files, Slack messages, or shared
spreadsheets.

The data model is simple and maps directly onto how real applications actually configure
themselves:

- A **Project** is a bucket for one application/service's secrets (e.g. "billing-api").
- A Project has one or more **Environments** (e.g. `production`, `staging`, `development`).
- A Project has any number of **Keys** — plain, readable names like `DATABASE_URL` or
  `STRIPE_SECRET_KEY`.
- Each Key can hold a different **Value** per Environment — or the same value everywhere, if that's
  all it needs (a "copy to every environment" convenience when setting a value).

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

Nebula Vault ships as a **single, self-contained Docker image** — the FastAPI backend, the built
Vue frontend, and its own embedded PostgreSQL 17 instance all run in one container. There is no
separate database container to stand up.

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
  scr.snakenet.io/nebula:latest
```

`NEBULA_MASTER_KEY` and `NEBULA_TOKEN` are the two variables the container refuses to start
without — everything else has a working default. **Write down `NEBULA_MASTER_KEY` somewhere safe.
If you lose it, every stored secret becomes permanently unrecoverable** (there's no backdoor — that's
the point of encryption). The `/data` volume is where the embedded Postgres cluster lives; mount it
persistently or your secrets vanish on container recreation.

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

FastAPI · Vue 3 (SPA) · Tailwind CSS · PostgreSQL 17 (embedded in the image) · SQLAlchemy (async) +
Alembic · Authentik (OIDC) · Python 3.14, `uv`.

---

<div align="center">© snakeNet.org, All rights reserved</div>
