#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Nebula Vault FastAPI entry point — serves the JSON API and the built static SPA portal.
@ai-context: Boots the FastAPI app, wires CORS + a global Server header, seeds the optional local
  bootstrap admin, checks the NEBULA_MASTER_KEY canary (nebula.crypto/models.tables.VaultMeta —
  fails startup loudly on a wrong key instead of a confusing per-request decrypt error later),
  dynamically mounts every api/v1/*.py router at /api/v1/<stem>, and serves the built Vite frontend
  from the `public/` folder with SPA-style fallback (any non-/api path resolves to a real file in
  public/ or falls back to index.html so client-side routes deep-link correctly). Schema is managed
  by Alembic (both entrypoint.lite.sh and entrypoint.aio.sh run `alembic upgrade head` before this
  starts) — the lifespan only seeds/validates idempotent bootstrap data, no DDL.
@ai-rules:
  - API routes must be registered before the SPA catch-all so /api/* always wins.
  - Never return raw passwords or secrets; never log secrets.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, uvicorn, loguru, sqlalchemy[asyncio]
@version: 1.0.1
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import importlib
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from nebula import version
from nebula.config import settings

# Replace loguru's default (unfiltered) sink with one gated by settings.log_level, before any other
# module's import-time/startup logging can fire.
logger.remove()
logger.add(sys.stderr, level=settings.log_level)

# Directory holding the built Vite frontend (served as the SPA). Created by `npm run build`.
PUBLIC_DIR = Path(__file__).parent / "public"


async def _seed_admin() -> None:
    """Create the optional local bootstrap admin from env when no local users exist (idempotent).

    Uses NEBULA_ADMIN_USER / NEBULA_ADMIN_PASS (+ optional NEBULA_ADMIN_EMAIL). Skipped when
    either is unset or when any user already exists, so it never clobbers a managed account.
    """
    from sqlalchemy import func, select

    from nebula.database import async_session_factory
    from nebula.models.tables import UserAccount
    from nebula.security import hash_password

    if not settings.admin_user or not settings.admin_pass:
        logger.info("No NEBULA_ADMIN_USER/PASS set — skipping local admin seed.")
        return

    async with async_session_factory() as session:
        existing = (await session.execute(select(func.count(UserAccount.id)))).scalar_one()
        if existing:
            return
        session.add(
            UserAccount(
                username=settings.admin_user,
                email=settings.admin_email or None,
                password=hash_password(settings.admin_pass),
                is_admin=True,
            )
        )
        await session.commit()
        logger.info(f"Seeded local bootstrap admin user '{settings.admin_user}'.")


async def _check_master_key_canary() -> None:
    """Verify NEBULA_MASTER_KEY against the stored VaultMeta canary (see nebula.crypto).

    First boot: encrypts the canary plaintext and stores it. Every later boot: decrypts it and
    compares. A wrong key raises RuntimeError here — at startup, loudly — rather than surfacing as a
    confusing per-request decrypt failure on some caller's first reveal/vault call.
    """
    from nebula.crypto import CANARY_PLAINTEXT, DecryptionError, decrypt_value, encrypt_value
    from nebula.database import async_session_factory
    from nebula.models.tables import VaultMeta

    async with async_session_factory() as session:
        row = await session.get(VaultMeta, 1)
        if row is None:
            session.add(VaultMeta(id=1, canary_ciphertext=encrypt_value(CANARY_PLAINTEXT)))
            await session.commit()
            logger.info("Initialized NEBULA_MASTER_KEY canary (first boot).")
            return

        try:
            plaintext = decrypt_value(row.canary_ciphertext)
        except DecryptionError as exc:
            raise RuntimeError(
                "NEBULA_MASTER_KEY does not match the key used to encrypt existing data. "
                "Refusing to start — see docs/encryption.md."
            ) from exc

        if plaintext != CANARY_PLAINTEXT:
            raise RuntimeError(
                "NEBULA_MASTER_KEY canary mismatch — refusing to start. See docs/encryption.md."
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Schema is managed by Alembic (run `alembic upgrade head` before starting). Seed/validate only
    # idempotent bootstrap data here, no DDL.
    await _check_master_key_canary()
    await _seed_admin()
    yield


app = FastAPI(
    title="Nebula Vault API",
    version=version,
    description="Self-hosted secrets manager for snakeNet.org.",
    lifespan=lifespan,
)

# CORS: the SPA is served same-origin in production; localhost:5173 is the Vite dev server.
origins = [
    "http://localhost:5173",
    "https://snakenet.org",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "X-Nebula-Token", "Content-Type"],
)


@app.middleware("http")
async def add_global_headers(request: Request, call_next):
    """Stamp a Nebula Server header on every response."""
    response = await call_next(request)
    response.headers["Server"] = "Nebula/" + version
    return response


def load_routers(api_version: str = "v1") -> None:
    """Dynamically load and mount every router under src/nebula/api/<version>/*.py."""
    api_dir = Path(__file__).parent / "src" / "nebula" / "api" / api_version
    for path in sorted(api_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module = importlib.import_module(f"nebula.api.{api_version}.{path.stem}")
        if hasattr(module, "router"):
            logger.debug(f"Mounting router '{path.stem}' at /api/{api_version}/{path.stem}")
            app.include_router(
                module.router,
                prefix=f"/api/{api_version}/{path.stem}",
                tags=[path.stem.capitalize()],
            )
        else:
            logger.debug(f"No router in {path.name}, skipping")


# Mount the API first so /api/* always takes precedence over the SPA fallback.
load_routers("v1")


# ── Static SPA serving ──────────────────────────────────────────────────────
# Vite emits hashed assets under public/assets; mount them directly when present.
if (PUBLIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str):
    """Serve the built SPA: a real file in public/ if it exists, else index.html (client routing).

    /api/* never reaches here (those routers are registered first); a stray /api/* still 404s as
    JSON rather than returning the SPA shell.
    """
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    candidate = (PUBLIC_DIR / full_path).resolve()
    # Guard against path traversal: only serve files inside PUBLIC_DIR.
    if full_path and candidate.is_file() and PUBLIC_DIR.resolve() in candidate.parents:
        return FileResponse(candidate)

    index = PUBLIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse(
        {"detail": "Frontend not built. Run `npm run build` in frontend/."}, status_code=404
    )


def run() -> None:
    """Boot uvicorn using the settings singleton — shared by `__main__` and the console script."""
    logger.debug(
        f"Starting Nebula Vault (version {version}) on {settings.host}:{settings.port} "
        f"reload={settings.dev} log_level={settings.log_level}"
    )
    uvicorn.run(
        "main:app" if settings.dev else app,
        host=settings.host,
        port=settings.port,
        reload=settings.dev,
        server_header=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
