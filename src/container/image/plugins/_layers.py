"""_layers.py - Shared helper: safe archive extraction and ordered layer merge.

Spec 023 FR-021…FR-030 (data-model §3, research R-05/R-06). Used by the
source plugins; imports no other plugin (constitution Principle I).

A merge runs in two phases so a failed run never leaves a half-built tree:
plan_merge() walks every layer and validates everything (type conflicts,
special files, escaping symlinks), then copy_planned() copies the winners.
"""

import os
import shutil
import stat
import tarfile
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


class LayerError(RuntimeError):
    """A layer cannot be used; the message names `layer #N (<host_path>)`."""


class LayerTimeout(LayerError):
    """Acquisition passed its deadline. A bare instance gets run.py's generic message."""


@dataclass
class OverrideRecord:
    relpath: str
    winner_position: int
    loser_position: int


# relpath -> (kind, position, source path); kind is "dir", "file" or "symlink"
MergePlan = Dict[str, Tuple[str, int, str]]

_KIND_NAMES = {"dir": "directory", "file": "file", "symlink": "symbolic link"}


def _check_deadline(deadline: Optional[float]) -> None:
    if deadline is not None and time.time() > deadline:
        raise LayerTimeout()


def safe_extract(archive_path: str, dest_dir: str, label: str,
                 deadline: Optional[float] = None) -> None:
    """Extract a .tgz member by member with tarfile's "data" filter (FR-024).

    The deadline is checked before every member. Directory members are
    applied last, as extractall() does, so a read-only directory cannot block
    the members inside it.
    """
    os.makedirs(dest_dir, exist_ok=True)
    try:
        with tarfile.open(archive_path, mode="r:gz") as tar:
            directories = []
            for member in tar:
                _check_deadline(deadline)
                # The data filter silently strips a leading "/"; an absolute
                # member is still a malformed archive, so reject it (FR-024).
                if member.name.startswith("/"):
                    raise LayerError(f"{label}: absolute member path {member.name!r}")
                if member.isdir():
                    directories.append(member)
                    continue
                tar.extract(member, path=dest_dir, filter="data")
            _check_deadline(deadline)
            # Reverse name order, exactly as extractall(): children get their
            # attributes before a (possibly read-only) parent.
            for member in sorted(directories, key=lambda m: m.name, reverse=True):
                tar.extract(member, path=dest_dir, filter="data")
    except LayerTimeout:
        raise
    except (tarfile.FilterError, tarfile.TarError, OSError, EOFError) as exc:
        raise LayerError(f"{label}: {exc}") from exc


def _entry_kind(path: str, rel: str, label: str) -> str:
    mode = os.lstat(path).st_mode
    if stat.S_ISLNK(mode):
        target = os.readlink(path)
        resolved = os.path.normpath(os.path.join(os.path.dirname(rel), target))
        if os.path.isabs(target) or resolved == ".." or resolved.startswith("../"):
            raise LayerError(f"{label}: symbolic link {rel} -> {target} points outside the test tree")
        return "symlink"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISREG(mode):
        return "file"
    raise LayerError(f"{label}: {rel} is not a regular file, directory or symbolic link")


def plan_merge(roots: List[Tuple[int, str, str]],
               deadline: Optional[float] = None) -> Tuple[MergePlan, List[OverrideRecord]]:
    """Validate all layers and decide which source wins for every path.

    roots: (position, source root, label) in merge order. Raises LayerError
    before anything is copied, LayerTimeout once the deadline has passed.
    """
    plan: MergePlan = {}
    overrides: List[OverrideRecord] = []
    for position, src_root, label in roots:
        for dirpath, dirnames, filenames in os.walk(src_root, followlinks=False):
            dirnames.sort()
            for name in dirnames + sorted(filenames):
                _check_deadline(deadline)
                src = os.path.join(dirpath, name)
                rel = os.path.relpath(src, src_root).replace(os.sep, "/")
                kind = _entry_kind(src, rel, label)
                previous = plan.get(rel)
                if previous is None:
                    plan[rel] = (kind, position, src)
                    continue
                prev_kind, prev_position, _ = previous
                if (prev_kind == "dir") != (kind == "dir"):
                    raise LayerError(
                        f"type conflict at {rel} (layer #{prev_position} "
                        f"{_KIND_NAMES[prev_kind]}, layer #{position} {_KIND_NAMES[kind]})")
                if kind != "dir":
                    overrides.append(OverrideRecord(rel, position, prev_position))
                    plan[rel] = (kind, position, src)
    return plan, overrides


def copy_planned(plan: MergePlan, dest_root: str, deadline: Optional[float]) -> None:
    """Copy the planned winners into dest_root (dirs precede their contents)."""
    os.makedirs(dest_root, exist_ok=True)
    for rel, (kind, _, src) in plan.items():
        _check_deadline(deadline)
        dst = os.path.join(dest_root, rel)
        if kind == "dir":
            os.makedirs(dst, exist_ok=True)
            continue
        if os.path.lexists(dst):
            os.remove(dst)
        if kind == "file":
            shutil.copy2(src, dst)
        else:
            os.symlink(os.readlink(src), dst)


def merge_layers(roots: List[Tuple[int, str, str]], dest_root: str,
                 deadline: Optional[float]) -> List[OverrideRecord]:
    """Merge the layers into dest_root in order; later files win (FR-021/022)."""
    plan, overrides = plan_merge(roots, deadline)
    copy_planned(plan, dest_root, deadline)
    return overrides
