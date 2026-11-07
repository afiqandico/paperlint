"""Recompute sha256 and byte size for every artefact named in a manifest.

Use it after regenerating a manifest, after restoring a deposited artefact, and
before quoting an artefact hash in prose.

Three shapes are accepted, auto-detected:

    {"artifacts": {"path/to/file": {"sha256": "...", "bytes": 1234}}}
    {"artifacts": [{"path": "path/to/file", "sha256": "...", "bytes": 1234}]}
    9c75cd08...f80  path/to/file          # sha256sum output, also ` *path`

Recorded digests may be full or abbreviated (a trailing ellipsis is stripped), so
a manifest written by hand with 8-char prefixes still verifies.

A manifest that lists its own digest can never pass: the digest is inside the
file whose digest it claims to record. That is reported as a defect instead of
being silently skipped, because the record is untrustworthy either way.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .report import Report

# `<64 hex>  <path>` or `<64 hex> *<path>` (sha256sum, also single-space variants)
SHA256SUM_RX = re.compile(r"^([0-9a-fA-F]{64})[ \t]+\*?(.+)$")
BARE_RX = re.compile(r"^[0-9a-fA-F]{64}$")


def rows(manifest: Any) -> list[tuple[str, dict]]:
    artefacts = manifest.get("artifacts", manifest) if isinstance(manifest, dict) else manifest
    if isinstance(artefacts, dict):
        return [
            (str(key), value if isinstance(value, dict) else {})
            for key, value in artefacts.items()
        ]
    return [
        (str(entry.get("path")), entry) for entry in artefacts if isinstance(entry, dict)
    ]


def read_manifest(text: str) -> tuple[list[tuple[str, dict]], str] | None:
    """Detect the manifest shape. Returns (items, shape) or None if unrecognised."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if data:
        try:
            items = rows(data)
        except (AttributeError, TypeError):
            items = []
        if items:
            return items, "json"

    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = SHA256SUM_RX.match(line)
        if match:
            items.append((match.group(2).strip(), {"sha256": match.group(1).lower()}))
    if items:
        return items, "sha256sum"
    stripped = text.strip()
    if BARE_RX.match(stripped):
        return [("<bare>", {"sha256": stripped.lower()})], "bare-digest"
    return None


def run_manifest(args: Any, report: Report) -> None:
    manifest_path = Path(args.manifest).expanduser()
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        report.fail("manifest readable", str(exc))
        return

    parsed = read_manifest(text)
    if parsed is None:
        report.fail(
            "manifest format recognised",
            "expected JSON {artifacts:...} or sha256sum lines '<64 hex>  <path>'",
        )
        return
    items, shape = parsed

    if shape == "bare-digest":
        target = getattr(args, "digest_of", None)
        if not target:
            report.fail(
                "bare digest has a target",
                "the file holds one 64-hex digest and no filename; pass --digest-of PATH",
            )
            return
        items = [(target, items[0][1])]

    root = Path(args.root).expanduser().resolve()
    report.meta.update(
        {"manifest": str(manifest_path), "root": str(root), "format": shape}
    )
    report.check(
        "manifest lists artefacts", bool(items), f"{len(items)} entr(y/ies), {shape}"
    )

    self_path = manifest_path.resolve()
    for rel, meta in items:
        path = Path(rel)
        if not path.is_absolute():
            path = root / rel
        if path.resolve() == self_path:
            report.fail(rel, "lists its own digest — a file cannot hash itself")
            continue
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
            # sha256sum output carries no size; that is a complete record, not a gap
            if shape == "json":
                problems.append("no bytes recorded")
        elif int(want_size) != size:
            problems.append(f"bytes {want_size} -> {size}")
        report.check(rel, not problems, "; ".join(problems) or digest[:16])
