"""Dangling path references and stale-claim patterns."""

from __future__ import annotations


def test_resolved_token_passes(tmp_path, run):
    (tmp_path / "figure.png").write_bytes(b"x")
    (tmp_path / "notes.md").write_text("See figure.png for the result.\n")
    code, out = run("manuscript", "paths", str(tmp_path))
    assert code == 0
    assert "no dangling path references" in out


def test_dangling_token_fails(tmp_path, run):
    (tmp_path / "notes.md").write_text("See missing.png for the result.\n")
    code, out = run("manuscript", "paths", str(tmp_path))
    assert code == 1
    assert "missing.png" in out


def test_token_resolved_in_extra_root(tmp_path, run):
    moved = tmp_path / "moved"
    moved.mkdir()
    (moved / "results.csv").write_text("a\n")
    (tmp_path / "notes.md").write_text("data in results.csv\n")
    code, _ = run("manuscript", "paths", str(tmp_path), "--resolve", str(moved))
    assert code == 0


def test_url_and_absolute_paths_ignored(tmp_path, run):
    (tmp_path / "notes.md").write_text(
        "https://example.org/paper.pdf and /etc/hosts.txt are not local refs\n"
    )
    code, _ = run("manuscript", "paths", str(tmp_path))
    assert code == 0


def test_patterns_are_reported_and_strict_gates_them(tmp_path, run):
    (tmp_path / "notes.md").write_text("accuracy of 100% is claimed here\n")
    rules = tmp_path / "patterns.txt"
    rules.write_text("# stale claims\noverclaim = 100%\n")

    code, out = run("manuscript", "paths", str(tmp_path), "--patterns", str(rules))
    assert code == 0
    assert "overclaim" in out

    code, out = run(
        "manuscript", "paths", str(tmp_path), "--patterns", str(rules), "--strict"
    )
    assert code == 1


def test_skip_directories_are_ignored(tmp_path, run):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "old.md").write_text("see gone.png\n")
    (tmp_path / "current.md").write_text("nothing here\n")
    code, _ = run("manuscript", "paths", str(tmp_path))
    assert code == 0


def test_missing_root_fails(tmp_path, run):
    code, out = run("manuscript", "paths", str(tmp_path / "nope"))
    assert code == 1
    assert "root directory exists" in out
