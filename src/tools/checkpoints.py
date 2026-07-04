"""Shadow git checkpoint helper."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckpointResult:
    success: bool
    message: str
    stash_ref: str | None = None


def create_checkpoint(cwd: Path | None = None, message: str = "emperor checkpoint") -> CheckpointResult:
    """Create a git stash snapshot if in a git repo."""
    root = cwd or Path.cwd()
    git_dir = root / ".git"
    if not git_dir.exists():
        return CheckpointResult(False, "Not a git repository")

    try:
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "stash", "create", message],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        ref = result.stdout.strip()
        if ref:
            subprocess.run(["git", "stash", "store", "-m", message, ref], cwd=root, check=True, capture_output=True)
        return CheckpointResult(True, f"Checkpoint created: {message}", ref or None)
    except subprocess.CalledProcessError as exc:
        return CheckpointResult(False, exc.stderr or str(exc))
