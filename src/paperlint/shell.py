"""Subprocess helpers.

List-form argv only — never `shell=True`. These commands routinely run against
directories containing spaces, quotes and non-ASCII names; one `shell=True` with
an interpolated path is how an audit silently checks nothing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_TIMEOUT = 120


class ToolMissing(RuntimeError):
    """A required external binary is not on PATH."""

    def __init__(self, name: str):
        super().__init__(f"required executable not found on PATH: {name}")
        self.name = name


def which(name: str) -> str | None:
    return shutil.which(name)


def require(*names: str) -> None:
    missing = [n for n in names if shutil.which(n) is None]
    if missing:
        raise ToolMissing(missing[0])


def run(
    cmd: list[str | Path],
    cwd: str | Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """Run a command, capture text output, never raise on non-zero status."""
    argv = [str(c) for c in cmd]
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def out(cmd: list[str | Path], cwd: str | Path | None = None) -> str:
    """Return stripped stdout, or '' if the command failed or is unavailable."""
    try:
        return run(cmd, cwd=cwd).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
