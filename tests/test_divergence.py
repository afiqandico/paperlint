"""Divergence measurement between two git roots."""

from __future__ import annotations

from conftest import git_init


def test_identical_roots_report_zero_divergence(tmp_path, run_json):
    files = {"src/a.py": "print(1)\n", "README.md": "# x\n"}
    left = git_init(tmp_path / "live", files)
    right = git_init(tmp_path / "pub", files)
    code, payload = run_json("repo", "divergence", str(left), str(right))
    assert code == 0
    assert payload["only_live"] == 0
    assert payload["only_published"] == 0
    assert payload["differing"] == 0
    assert payload["common"] == 2


def test_divergent_roots_are_counted(tmp_path, run_json):
    left = git_init(
        tmp_path / "live", {"src/a.py": "new\n", "src/only_live.py": "x\n"}
    )
    right = git_init(
        tmp_path / "pub", {"src/a.py": "old\n", "src/only_pub.py": "y\n"}
    )
    code, payload = run_json("repo", "divergence", str(left), str(right))
    assert code == 0
    assert payload["only_live"] == 1
    assert payload["only_published"] == 1
    assert payload["differing"] == 1


def test_non_git_root_fails(tmp_path, run):
    left = git_init(tmp_path / "live", {"a.txt": "x\n"})
    plain = tmp_path / "plain"
    plain.mkdir()
    code, out = run("repo", "divergence", str(left), str(plain))
    assert code == 1
    assert "is a git repo" in out


def test_filenames_with_spaces_are_handled(tmp_path, run_json):
    files = {"results/final table.csv": "a,b\n"}
    left = git_init(tmp_path / "live", files)
    right = git_init(tmp_path / "pub", {"results/final table.csv": "a,b\n1,2\n"})
    code, payload = run_json("repo", "divergence", str(left), str(right))
    assert code == 0
    assert payload["differing"] == 1
