"""Paths as the filesystem compares them, for the hooks that decide by path.

A hook is handed whatever spelling the tool call used. On a volume that
ignores letter case (the default on macOS and Windows) `ONTOLOGY/Workflow.yaml`
opens `ontology/workflow.yaml`, so a rule that compares the spelling is dodged
by a capital letter. Symlinks are followed first, for the same reason.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .config import CONFIG_FILE, Config


@lru_cache(maxsize=8)
def ignores_case(root: Path) -> bool:
    """True if the volume holding the repository treats names that differ only in case as one."""
    other = CONFIG_FILE.swapcase()
    try:
        return (root / other).exists() and other not in os.listdir(root)
    except OSError:
        return False


def fold(cfg: Config, text: str) -> str:
    """A path or glob in the form two spellings of one file share on this volume."""
    return text.casefold() if ignores_case(cfg.root) else text


def key(cfg: Config, path: Path | str) -> str:
    """Repository-relative path to compare with: symlinks followed, then `fold`.

    Works for a file that does not exist yet, which is what a Write creates.
    """
    p = Path(path)
    if not p.is_absolute():
        p = cfg.root / p
    resolved = fold(cfg, p.resolve().as_posix())
    root = fold(cfg, cfg.root.as_posix())
    return resolved[len(root) + 1 :] if resolved.startswith(root + "/") else resolved


def stored(path: Path | str) -> Path:
    """An existing file's path as the volume stores it: symlinks followed, stored letter case."""
    resolved = Path(path).resolve()
    out = Path(resolved.anchor)
    for part in resolved.parts[1:]:
        try:
            names = os.listdir(out)
        except OSError:
            names = []
        if part not in names:
            folded = part.casefold()
            part = next(
                (n for n in names if n.casefold() == folded and _same_file(out / n, out / part)),
                part,
            )
        out = out / part
    return out


def _same_file(one: Path, other: Path) -> bool:
    try:
        return os.path.samefile(one, other)
    except OSError:
        return False
