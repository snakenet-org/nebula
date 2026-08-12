#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Automatic SecretKey rotation — due-check + fresh-value generation.
@ai-context: A SecretKey optionally carries a `rotation_frequency`/`rotation_unit` schedule (see
  nebula.models.tables.RotationUnit and the SecretKey class docstring) — this module is the one place
  that knows how to turn that schedule into an actual "is this key due right now" decision and how to
  perform the rotation itself. scripts/rotate_secrets.py (the standalone hourly process) is the only
  caller of list_due_for_rotation/rotate_key; nebula.secrets owns everything else about a SecretKey's
  CRUD (including validating/storing the schedule fields themselves — see its
  RotationNotSupportedError) so this module only ever reads rotation_frequency/rotation_unit, never
  sets them.
  Interval math is a fixed day-count approximation (week=7, month=30, year=365), not a calendar-exact
  computation (e.g. via a proper relativedelta) — this app has no such dependency, and "every N
  months" is already an inherently fuzzy product concept for something evaluated on an hourly tick;
  being off by a day or two near a rotation boundary is an acceptable trade for not adding a new
  dependency. is_due never fires for a reference key (source_key_id — it owns no value of its own,
  see nebula.secrets' module docstring) or a non-SECRET key (rotation is a secret-only concept, see
  models/secret.py's validators) — both are also excluded from list_due_for_rotation's own query, so
  is_due's own re-check there is defense-in-depth, not the only guard.
  generate_rotated_value uses the stdlib `secrets` module (`secrets.choice`, itself backed by
  `os.urandom`/`random.SystemRandom` — already uniformly distributed over the charset with no
  rejection-sampling needed, unlike the frontend's Web-Crypto-via-getRandomValues generator in
  lib/generators.js, which has to hand-roll rejection sampling since it draws raw bytes instead of
  going through a charset-aware `choice`) — same 35-character length/charset as that frontend
  generator (PASSWORD_CHARSET there / _CHARSET here), so a rotated value looks indistinguishable from
  one a human generated via the "Generate" button.
@ai-rules:
  - Never log a rotated value's plaintext (return it from rotate_key only for a caller that itself
    never logs it — scripts/rotate_secrets.py does not).
  - encrypt_value only — never import `cryptography` directly here (see nebula.crypto).
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import secrets as pysecrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.crypto import encrypt_value
from nebula.models.tables import RotationUnit, SecretKey, VariableType

# Same charset/length as frontend/src/lib/generators.js's generateSecurePassword — a rotated value
# should be indistinguishable from one a human generated via the "Generate" button.
ROTATED_VALUE_LENGTH = 35
_CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"

# Fixed day-count approximation per unit — see the module docstring for why this isn't calendar-exact.
ROTATION_UNIT_DAYS: dict[RotationUnit, int] = {
    RotationUnit.WEEK: 7,
    RotationUnit.MONTH: 30,
    RotationUnit.YEAR: 365,
}


def generate_rotated_value(length: int = ROTATED_VALUE_LENGTH) -> str:
    """A fresh cryptographically-random replacement value — see the module docstring."""
    return "".join(pysecrets.choice(_CHARSET) for _ in range(length))


def rotation_interval(key: SecretKey) -> timedelta | None:
    """The configured rotation cadence as a timedelta, or None if rotation isn't enabled."""
    if key.rotation_frequency is None or key.rotation_unit is None:
        return None
    return timedelta(
        days=ROTATION_UNIT_DAYS[RotationUnit(key.rotation_unit)] * key.rotation_frequency
    )


def is_due(key: SecretKey, *, now: datetime | None = None) -> bool:
    """Whether `key` should be automatically rotated right now — see the module docstring for the
    reference/non-SECRET/no-value exclusions."""
    interval = rotation_interval(key)
    if interval is None:
        return False
    if key.source_key_id is not None or key.variable_type != VariableType.SECRET:
        return False
    if key.ciphertext is None:
        return False
    reference_point = key.last_rotated_at or key.created_at
    return (now or datetime.utcnow()) - reference_point >= interval


async def list_due_for_rotation(session: AsyncSession) -> list[SecretKey]:
    """Every SecretKey, across every Project, currently due for automatic rotation.

    The DB query narrows to rotation-enabled, non-reference, SECRET-type rows with a value already
    set; the actual due/not-due decision (which depends on rotation_unit's day-length mapping) is
    finished in Python via is_due, since three different per-unit intervals aren't something a single
    SQL WHERE clause expresses cleanly.
    """
    result = await session.execute(
        select(SecretKey).where(
            SecretKey.rotation_frequency.is_not(None),
            SecretKey.source_key_id.is_(None),
            SecretKey.variable_type == VariableType.SECRET,
            SecretKey.ciphertext.is_not(None),
        )
    )
    return [key for key in result.scalars().all() if is_due(key)]


async def rotate_key(session: AsyncSession, key: SecretKey) -> str:
    """Re-generate `key`'s value with a fresh random secret, encrypt+store it, and stamp
    last_rotated_at. Leaves rotation_frequency/rotation_unit (the schedule itself) untouched — only
    set_value/create_key (nebula.secrets) ever change those. Returns the new plaintext ONLY so a
    caller could act on it in-memory if it ever needed to (scripts/rotate_secrets.py does not — it
    never logs or forwards this return value anywhere)."""
    plaintext = generate_rotated_value()
    key.ciphertext = encrypt_value(plaintext)
    key.last_rotated_at = datetime.utcnow()
    # No human performed this — leave a stale updated_by pointing at whoever last touched the value
    # unset, same "no attributable actor" reasoning as this column's ON DELETE SET NULL.
    key.updated_by = None
    await session.commit()
    await session.refresh(key)
    return plaintext
