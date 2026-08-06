#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Map snakeNet ID (Authentik) group memberships to Nebula entitlements.
@ai-context: Access to Nebula is group-driven, mirroring gravity.entitlements exactly. On OIDC (or
  local admin) login the caller's `groups` claim is resolved to a set of entitlements via
  GROUP_ENTITLEMENTS; an entitlement is a bare capability stem with no prefix. The special `admin`
  entitlement grants full access to every Project regardless of ownership/sharing (see
  nebula.projects' can_view/can_edit/can_reveal/can_manage_sharing/can_manage_access_keys/
  can_delete, all of which treat is_admin as an unconditional bypass). A user with no entitlements
  has no access at all — login is rejected and the API gate denies. `nebula-user` is the baseline:
  it lets someone log in and create/own their own Projects; it grants nothing about anyone else's
  Project — that's ProjectShare's job, not this module's.
@ai-rules:
  - Keep entitlements as bare stems (no `api_`/`page_` prefixes).
  - Maintain 100% type-hinting coverage.
@dependencies: (none)
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from collections.abc import Iterable

# The entitlement that grants unrestricted access.
ADMIN_ENTITLEMENT = "admin"

# Authentik group name → entitlement stems it grants.
GROUP_ENTITLEMENTS: dict[str, list[str]] = {
    "nebula-admin": [ADMIN_ENTITLEMENT],
    "nebula-user": ["user"],
}


def entitlements_for_groups(groups: Iterable[str]) -> list[str]:
    """Resolve the union of entitlements granted by the caller's groups (sorted, de-duplicated)."""
    resolved: set[str] = set()
    for group in groups:
        resolved.update(GROUP_ENTITLEMENTS.get(group, []))
    return sorted(resolved)


def has_access(entitlements: Iterable[str]) -> bool:
    """True if the caller holds at least one entitlement (i.e. may use Nebula at all)."""
    return bool(list(entitlements))


def is_admin(entitlements: Iterable[str]) -> bool:
    """True if the caller holds the full-access `admin` entitlement."""
    return ADMIN_ENTITLEMENT in set(entitlements)
