#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Shared name-charset rule for Project/Environment/SecretKey names.
@ai-context: These are exactly the three identifiers api/v1/vault.py's external GET /secret route
  addresses by name (never by internal UUID, since a machine caller only ever knows the
  human-readable names) — restricting the charset to letters/digits/hyphen/underscore keeps a name
  always safe to reuse verbatim downstream (a synced GitHub Actions secret name, a .env line, a raw
  query-string value) with no quoting/escaping question ever coming up. `validate_name` is meant to
  be called from a Pydantic `field_validator` — raising `ValueError` there becomes a clean 422
  automatically, no HTTPException translation needed at the router layer.
@ai-rules:
  - Every Project/Environment/SecretKey name field (create AND update requests) must run through
    validate_name — wire it in when adding a new one.
  - Maintain 100% type-hinting coverage.
@dependencies: none
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-07
"""

import re

NAME_PATTERN = r"^[A-Za-z0-9_-]+$"
NAME_RE = re.compile(NAME_PATTERN)


def validate_name(value: str) -> str:
    """Raise ValueError unless `value` is only letters/digits/hyphens/underscores (1+ chars)."""
    if not NAME_RE.fullmatch(value):
        raise ValueError(
            "must contain only letters, numbers, hyphens (-), and underscores (_) — "
            "no spaces, dots, or other special characters"
        )
    return value
