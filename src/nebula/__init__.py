#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Package metadata + console-script entry point.
@ai-context: `version` is read by main.py (FastAPI app version, Server header) and the frontend's
  About view (via GET /api/v1/config). `main()` is the `nebula` console script installed by
  pyproject.toml's [project.scripts] — a thin wrapper around main.run() so `uv run nebula` works
  the same as `uv run main.py`.
@ai-rules:
  - Bump `version` together with pyproject.toml's [project] version on every release-worthy change.
  - Maintain 100% type-hinting coverage.
@dependencies: (none)
@version: 2.31.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-10-15
"""

version = "2.31.0"


def main() -> None:
    """Console-script entry point (`uv run nebula`)."""
    from main import run

    run()
