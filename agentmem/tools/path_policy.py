from __future__ import annotations

from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_allowed_path(
    value: str | Path,
    allowed_roots: Iterable[str | Path],
    *,
    base_dir: str | Path = PROJECT_ROOT,
) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path(base_dir) / path
    target = path.resolve()
    roots = [Path(root).resolve() for root in allowed_roots]
    if not any(_is_relative_to(target, root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise PermissionError(f"路径不在允许目录内: {target}; allowed_roots={allowed}")
    return target


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
