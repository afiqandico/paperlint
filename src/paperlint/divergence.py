"""Measure divergence between two git roots holding the same research project.

Read-only. Answers "which deliverable exists in only one of the two trees?" by
comparing the tracked file set and the content hash of every common path.

Why two roots is a legitimate state: a live working tree and a publication
snapshot are expected to differ. The point is to see *what* differs, not to
"clean it up" into one root.
"""

from __future__ import annotations

import collections
import hashlib
from pathlib import Path
from typing import Any

from .report import Report
from .shell import run


def tracked(root: Path) -> list[str]:
    """Tracked paths; -z keeps names with spaces and quotes intact."""
    result = run(["git", "-C", str(root), "ls-files", "-z"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return sorted(p for p in result.stdout.split("\0") if p)


def sha256(root: Path, rel: str) -> str:
    path = root / rel
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        return f"ERR:{exc.errno}"  # broken symlink / vanished file counts as differing


def area(rel: str) -> str:
    parts = rel.split("/")
    if parts[0] == "submissions" and len(parts) > 2:
        return "/".join(parts[:2])
    return parts[0]


def run_divergence(args: Any, report: Report) -> None:
    live = Path(args.live).expanduser().resolve()
    published = Path(args.published).expanduser().resolve()
    for label, root in (("live", live), ("published", published)):
        if not (root / ".git").exists():
            report.fail(f"{label} root is a git repo", str(root))
    if report.failures:
        return

    left, right = tracked(live), tracked(published)
    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))
    common = sorted(set(left) & set(right))
    differing = [rel for rel in common if sha256(live, rel) != sha256(published, rel)]

    report.allow_empty = True
    report.meta.update(
        {
            "live": str(live),
            "published": str(published),
            "tracked_live": len(left),
            "tracked_published": len(right),
            "common": len(common),
            "only_live": len(only_left),
            "only_published": len(only_right),
            "differing": len(differing),
        }
    )

    def summarize(label: str, rels: list[str]) -> None:
        if not rels:
            return
        counts = collections.Counter(area(r) for r in rels).most_common(10)
        report.note(f"{label}: {len(rels)} — per area {counts}")
        report.note(f"{label} sample: {rels[:8]}")

    report.note(
        f"tracked live={len(left)} published={len(right)} common={len(common)}"
    )
    summarize("only in live", only_left)
    summarize("only in published", only_right)
    summarize("content differs", differing)
    report.note(
        "the two roots are meant to diverge; use this to spot a deliverable "
        "that exists on only one side"
    )
