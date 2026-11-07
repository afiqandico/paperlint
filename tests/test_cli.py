"""CLI surface: version, help, usage errors and the empty-gate rule."""

from __future__ import annotations

import pytest


def test_version_flag():
    from paperlint.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_no_arguments_prints_help(run):
    code, out = run()
    assert code == 2
    assert "usage: paperlint" in out


def test_group_without_command_is_usage_error(run):
    with pytest.raises(SystemExit) as exc:
        run("manuscript")
    assert exc.value.code == 2


def test_missing_base_directory_fails(run):
    code, out = run("manuscript", "package", "--base", "/nonexistent/paperlint")
    assert code == 1
    assert "base directory exists" in out


def test_json_report_shape(run_json):
    code, payload = run_json("manuscript", "package", "--base", "/nonexistent/paperlint")
    assert code == 1
    assert payload["ok"] is False
    assert payload["failed"] == 1
    assert payload["checks"][0]["ok"] is False


def test_empty_gate_is_not_a_pass(run):
    """A command that ran no checks must not exit 0."""
    code, out = run("manuscript", "package", "--base", ".")
    assert code == 1
    assert "NO CHECKS RAN" in out
