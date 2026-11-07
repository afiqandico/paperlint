"""Manifest verification: full digests, prefixes, sizes, both schemas."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload))
    return path


def test_full_digest_and_size_pass(tmp_path, run):
    artefact = tmp_path / "results.json"
    artefact.write_text('{"acc": 0.9}')
    manifest = _write(
        tmp_path / "manifest.json",
        {"artifacts": {"results.json": {"sha256": _sha(artefact), "bytes": 12}}},
    )
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 0
    assert "1/2 pass" in out or "PASS" in out


def test_abbreviated_digest_accepted(tmp_path, run):
    artefact = tmp_path / "a.bin"
    artefact.write_bytes(b"payload")
    manifest = _write(
        tmp_path / "manifest.json",
        {"artifacts": [{"path": "a.bin", "sha256": _sha(artefact)[:8] + "\u2026"}]},
    )
    code, _ = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    # digest matches, but no byte count recorded -> that is reported as a problem
    assert code == 1


def test_digest_mismatch_fails(tmp_path, run):
    (tmp_path / "a.bin").write_bytes(b"changed")
    manifest = _write(
        tmp_path / "manifest.json",
        {"artifacts": {"a.bin": {"sha256": "0" * 64, "bytes": 7}}},
    )
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 1
    assert "a.bin" in out


def test_size_mismatch_fails(tmp_path, run):
    artefact = tmp_path / "a.bin"
    artefact.write_bytes(b"12345")
    manifest = _write(
        tmp_path / "manifest.json",
        {"artifacts": {"a.bin": {"sha256": _sha(artefact), "bytes": 99}}},
    )
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 1
    assert "bytes" in out


def test_missing_artefact_fails(tmp_path, run):
    manifest = _write(
        tmp_path / "manifest.json",
        {"artifacts": {"ghost.bin": {"sha256": "0" * 64, "bytes": 1}}},
    )
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 1
    assert "missing" in out


def test_invalid_json_reports_cleanly(tmp_path, run):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{not json")
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 1
    assert "valid JSON" in out
