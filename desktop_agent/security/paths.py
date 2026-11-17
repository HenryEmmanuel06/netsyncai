"""Path security — the single funnel for all local filesystem access.

Every agent file operation MUST resolve through safe_resolve(). Rules:
- target must live under an explicitly allowed root
- `..`, symlink escapes, and junction escapes are rejected
- UNC/device paths never match a local root unless registered as one
"""

from __future__ import annotations

import os
from pathlib import Path


class PathSecurityError(Exception):
    """Denied path access. Never catch-and-ignore in callers."""


def _norm(p: Path | str) -> str:
    """Case-normalized absolute path (Windows paths are case-insensitive)."""
    return os.path.normcase(os.path.normpath(str(p)))


class AllowedRoots:
    """Registry of local directories the agent may touch."""

    def __init__(self, roots: list[str | Path] | None = None) -> None:
        self._roots: list[Path] = []
        for r in roots or []:
            self.add(r)

    def add(self, root: str | Path) -> Path:
        p = Path(root).resolve()
        if not p.is_dir() and not p.is_file():
            raise PathSecurityError(f"root does not exist: {root}")
        if _norm(p) not in {_norm(r) for r in self._roots}:
            self._roots.append(p)
        return p

    def remove(self, root: str | Path) -> None:
        target = _norm(Path(root).resolve())
        self._roots = [r for r in self._roots if _norm(r) != target]

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def _containing_root(self, resolved: Path) -> Path | None:
        for root in self._roots:
            if resolved == root:
                return root      # a root may itself be a shared file
            try:
                resolved.relative_to(root)
                return root
            except ValueError:
                continue
        return None

    def safe_resolve(self, candidate: str | Path) -> Path:
        """Resolve `candidate` and require it to live under an allowed root.

        Rejects traversal escapes (`../../etc/passwd`), resolved symlink
        escapes, and paths not under any registered root. `resolve()` follows
        symlinks and collapses `..`, so a resolved path inside a root is safe
        even if the raw string contained `..` — but a *raw* `..` that escapes
        is caught by the relative_to check on the resolved path.
        """
        raw = Path(candidate)
        if not raw.is_absolute():
            # Relative paths are resolved against each root until one fits.
            for root in self._roots:
                resolved = (root / raw).resolve()
                try:
                    resolved.relative_to(root)
                    return resolved
                except ValueError:
                    continue
            raise PathSecurityError(f"path outside allowed roots: {candidate}")

        resolved = raw.resolve()
        if self._containing_root(resolved) is None:
            raise PathSecurityError(f"path outside allowed roots: {candidate}")
        return resolved

    def is_allowed(self, candidate: str | Path) -> bool:
        try:
            self.safe_resolve(candidate)
            return True
        except PathSecurityError:
            return False
