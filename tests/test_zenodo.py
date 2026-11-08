"""Tests for `paperlint.zenodo` — the deposit-record gate.

This module exists to stop a specific mistake: writing "archived in a public
repository" when the record is restricted with zero public files, or when the
30-day file-edit window has closed. Those two branches were never covered by a
test, so they are pinned here with the network call monkeypatched out.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from paperlint.report import Report
from paperlint import zenodo


def args(*records: str, timeout: int = 5) -> SimpleNamespace:
    return SimpleNamespace(records=list(records), timeout=timeout)


def run(monkeypatch, payloads: dict[str, dict | None], records: list[str]) -> Report:
    monkeypatch.setattr(zenodo, "fetch", lambda record, timeout=30: payloads.get(record))
    report = Report("zenodo", allow_empty=True)
    zenodo.run_zenodo(args(*records), report)
    return report


def notes(report: Report) -> str:
    return "\n".join(report.notes)


def test_unreachable_record_is_a_failure(monkeypatch) -> None:
    report = run(monkeypatch, {"42": None}, ["42"])
    assert [c.name for c in report.failures] == ["record 42 reachable"]
    assert report.failures[0].detail == "HTTP error or timeout"


def test_restricted_with_no_public_files_warns_about_overclaim(monkeypatch) -> None:
    payload = {
        "metadata": {"conceptrecid": "7", "version": "1.0.0", "access_right": "restricted"},
        "files": [],
        "created": f"{date.today().isoformat()}T09:00:00",
    }
    report = run(monkeypatch, {"7": payload}, ["7"])
    assert "overclaim" in notes(report)


def test_open_record_with_files_has_no_overclaim_note(monkeypatch) -> None:
    payload = {
        "metadata": {"conceptrecid": "7", "version": "1.0.0", "access_right": "open"},
        "files": [{"key": "a.zip"}],
        "created": f"{date.today().isoformat()}T09:00:00",
    }
    report = run(monkeypatch, {"7": payload}, ["7"])
    assert "overclaim" not in notes(report)
    assert "anonymous_files=1" in notes(report)


def test_concept_record_is_labelled_concept(monkeypatch) -> None:
    payload = {"metadata": {"conceptrecid": "7"}, "files": [], "created": ""}
    report = run(monkeypatch, {"7": payload}, ["7"])
    assert report.checks[0].detail == "concept"


def test_versioned_record_is_labelled_version(monkeypatch) -> None:
    # conceptrecid != record dan version ada -> ini record versi, bukan konsep
    payload = {"metadata": {"conceptrecid": "70", "version": "1.0.1"}, "files": [], "created": ""}
    report = run(monkeypatch, {"7": payload}, ["7"])
    assert report.checks[0].detail == "version"


def test_licence_given_as_dict_is_reported_as_id(monkeypatch) -> None:
    payload = {
        "metadata": {"conceptrecid": "7", "version": "1", "license": {"id": "cc-by-4.0"}},
        "files": [],
        "created": "",
    }
    report = run(monkeypatch, {"7": payload}, ["7"])
    assert "license=cc-by-4.0" in notes(report)


@pytest.mark.parametrize(("age_days", "expected"), [(0, "open (30 day(s) left)"), (40, "closed")])
def test_file_window_branch(monkeypatch, age_days: int, expected: str) -> None:
    created = date.today() - timedelta(days=age_days)
    payload = {
        "metadata": {"conceptrecid": "7", "version": "1"},
        "files": [],
        "created": f"{created.isoformat()}T00:00:00",
    }
    report = run(monkeypatch, {"7": payload}, ["7"])
    assert f"file window {expected}" in notes(report)


def test_meta_records_every_requested_record(monkeypatch) -> None:
    report = run(monkeypatch, {"1": None, "2": None}, ["1", "2"])
    assert report.meta["records"] == ["1", "2"]
    assert len(report.failures) == 2
