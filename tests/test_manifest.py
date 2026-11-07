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
    assert "2/2 pass" in out


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


def test_unrecognised_format_names_both_shapes(tmp_path, run):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{not json")
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 1
    assert "format recognised" in out
    assert "sha256sum" in out


def test_sha256sum_output_verifies(tmp_path, run):
    artefact = tmp_path / "bundle.zip"
    artefact.write_bytes(b"payload")
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(f"{_sha(artefact)}  bundle.zip\n")
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 0, out
    assert "2/2 pass" in out
    assert "sha256sum" in out


def test_sha256sum_binary_marker_is_parsed(tmp_path, run):
    artefact = tmp_path / "bundle.zip"
    artefact.write_bytes(b"payload")
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(f"{_sha(artefact)} *bundle.zip\n")
    code, _ = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 0


def test_sha256sum_drift_fails(tmp_path, run):
    (tmp_path / "bundle.zip").write_bytes(b"changed")
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(f"{'0' * 64}  bundle.zip\n")
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 1
    assert "bundle.zip" in out


def test_sha256sum_comments_and_blanks_ignored(tmp_path, run):
    artefact = tmp_path / "a.bin"
    artefact.write_bytes(b"x")
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(f"# generated 2026-11-07\n\n{_sha(artefact)}  a.bin\n\n")
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 0, out


def test_manifest_listing_itself_fails(tmp_path, run):
    """A file cannot contain its own digest; the record is unsound either way."""
    artefact = tmp_path / "a.bin"
    artefact.write_bytes(b"x")
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(f"{_sha(artefact)}  a.bin\n{'9' * 64}  SHA256SUMS\n")
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 1
    assert "cannot hash itself" in out


def test_single_space_sha256sum_line_is_parsed(tmp_path, run):
    artefact = tmp_path / "a.bin"
    artefact.write_bytes(b"x")
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(f"{_sha(artefact)} a.bin\n")
    code, _ = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 0


def test_bare_digest_without_target_fails_loudly(tmp_path, run):
    manifest = tmp_path / "bundle_sha.txt"
    manifest.write_text("a" * 64)
    code, out = run("verify", "manifest", str(manifest), "--root", str(tmp_path))
    assert code == 1
    assert "--digest-of" in out


def test_bare_digest_with_target_passes(tmp_path, run):
    artefact = tmp_path / "bundle.zip"
    artefact.write_bytes(b"payload")
    manifest = tmp_path / "bundle_sha.txt"
    manifest.write_text(_sha(artefact))
    code, out = run(
        "verify",
        "manifest",
        str(manifest),
        "--root",
        str(tmp_path),
        "--digest-of",
        "bundle.zip",
    )
    assert code == 0, out


def test_bare_digest_with_target_detects_drift(tmp_path, run):
    (tmp_path / "bundle.zip").write_bytes(b"rebuilt")
    manifest = tmp_path / "bundle_sha.txt"
    manifest.write_text("b" * 64)
    code, out = run(
        "verify",
        "manifest",
        str(manifest),
        "--root",
        str(tmp_path),
        "--digest-of",
        "bundle.zip",
    )
    assert code == 1
    assert "bundle.zip" in out

