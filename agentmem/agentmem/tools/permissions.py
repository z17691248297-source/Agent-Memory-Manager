from __future__ import annotations

from enum import Enum


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    COMPUTE_ONLY = "compute_only"
    SAFE_LOCAL = "safe_local"
    DISABLED = "disabled"


DEFAULT_ALLOWED_PERMISSIONS = {
    PermissionLevel.READ_ONLY.value,
    PermissionLevel.COMPUTE_ONLY.value,
    PermissionLevel.SAFE_LOCAL.value,
}


def permission_allowed(permission_level: str, allowed: set[str] | None = None) -> bool:
    if permission_level == PermissionLevel.DISABLED.value:
        return False
    allowed = allowed or DEFAULT_ALLOWED_PERMISSIONS
    return permission_level in allowed

