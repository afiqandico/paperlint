"""Recompute sha256 and byte size for every artefact named in a manifest.

Use it after regenerating a manifest, after restoring a deposited artefact, and
before quoting an artefact hash in prose.

Accepts both common shapes:

    {"artifacts": {"path/to/file": {"sha256": "...", "bytes": 1234}}}
    {"artifacts": [{"path": "path/to/file", "sha256": "...", "bytes": 1234}]}

Recorded digests may be full or abbreviated (a trailing ellipsis is stripped), so
a manifest written by hand with 8-char prefixes still verifies.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .report import Report


def rows(manifest: dict) -> list[tuple[str, dict]]:
    artefacts = manifest.get("artifacts", manifest)
    if isinstance(artefacts, dict):
        return [
            (str(key), value if isinstance(value, dict) else {})
            for key, value in artefacts.items()
        ]
    return [(str(e.get("path")), e) for e in artefacts if isinstance(e, dict)]


def run_manifest(args: Any, report: Report) -> None:
    manifest_path = Path(args.manifest)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        report.fail("manifest readable", str(exc))
        return
    except json.JSONDecodeError as exc:
        report.fail("manifest is valid JSON", str(exc))
        return

    root = Path(args.root).expanduser().resolve()
    report.meta.update({"manifest": str(manifest_path), "root": str(root)})

    items = rows(manifest)
    report.check("manifest lists artefacts", bool(items), f"{len(items)} entr(y/ies)")

    for rel, meta in items:
        path = Path(rel)
        if not path.is_absolute():
            path = root / rel
        if not path.is_file():
            report.fail(rel, "missing")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        size = path.stat().st_size
        want_hash = meta.get("sha256")
        want_size = meta.get("bytes", meta.get("size"))
        problems: list[str] = []
        if want_hash:
            want = str(want_hash).rstrip("\u2026").lower()
            if not digest.startswith(want):
                problems.append(f"sha {want[:16]}… -> {digest[:16]}…")
        else:
            problems.append("no sha256 recorded")
        if want_size is None:
            problems.append("no bytes recorded")
        elif int(want_size) != size:
            problems.append(f"bytes {want_size} -> {size}")
        report.check(rel, not problems, "; ".join(problems) or digest[:16])
