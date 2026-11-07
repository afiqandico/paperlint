"""CI wiring audit."""

from __future__ import annotations

GOOD = """\
name: ci
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""

PATH_FILTERED_NO_SELF = """\
name: docs
on:
  push:
    branches: [main]
    paths:
      - "docs/**"
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""

MISSING_WORKDIR = """\
name: nested
on:
  push:
    branches: [main]
jobs:
  test:
    defaults:
      run:
        working-directory: does-not-exist
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
"""


def _workflow(root, name, body, subdir=""):
    target = root / subdir / ".github" / "workflows"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{name}.yml").write_text(body)


def test_correct_wiring_passes(tmp_path, run):
    _workflow(tmp_path, "ci", GOOD)
    code, out = run("repo", "ci", str(tmp_path))
    assert code == 0, out


def test_nested_workflow_dir_fails(tmp_path, run):
    _workflow(tmp_path, "ci", GOOD)
    _workflow(tmp_path, "sub", GOOD, subdir="packages/project")
    code, out = run("repo", "ci", str(tmp_path))
    assert code == 1
    assert "outside the root" in out


def test_path_filtered_without_self_trigger_fails(tmp_path, run):
    _workflow(tmp_path, "docs", PATH_FILTERED_NO_SELF)
    code, out = run("repo", "ci", str(tmp_path))
    assert code == 1
    assert "self-triggers" in out


def test_missing_working_directory_fails(tmp_path, run):
    _workflow(tmp_path, "nested", MISSING_WORKDIR)
    code, out = run("repo", "ci", str(tmp_path))
    assert code == 1
    assert "working-directory exists" in out


def test_malformed_yaml_fails(tmp_path, run):
    _workflow(tmp_path, "broken", "name: [unclosed\n")
    code, out = run("repo", "ci", str(tmp_path))
    assert code == 1
    assert "parses" in out


def test_no_workflows_fails(tmp_path, run):
    code, out = run("repo", "ci", str(tmp_path))
    assert code == 1
    assert "at least one workflow" in out


def test_duplicate_workflow_names_fail(tmp_path, run):
    _workflow(tmp_path, "a", GOOD)
    _workflow(tmp_path, "b", GOOD.replace("name: ci", "name: ci"))
    code, out = run("repo", "ci", str(tmp_path))
    assert code == 1
    assert "unique" in out
