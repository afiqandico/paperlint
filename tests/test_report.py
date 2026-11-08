"""Tests for `paperlint.report` — the object every gate's verdict goes through.

The behaviour with the highest stakes here is the negative one: an empty report
must NOT be a pass (`ok is False`, exit code 1). That rule is the whole reason
this module exists, and it was previously only covered indirectly by CLI tests.
"""

from __future__ import annotations

import io
import json

from paperlint.report import Report


def render(report: Report) -> str:
    buf = io.StringIO()
    report.render(buf)
    return buf.getvalue()


class TestEmptiness:
    def test_empty_gate_is_not_a_pass(self) -> None:
        report = Report("demo")
        assert report.ok is False
        assert report.emit(as_json=False) == 1

    def test_empty_gate_says_why(self) -> None:
        text = render(Report("demo"))
        assert "NO CHECKS RAN" in text
        assert "an empty gate is not a pass" in text

    def test_allow_empty_makes_an_informational_tool_pass(self) -> None:
        report = Report("zenodo", allow_empty=True)
        assert report.ok is True
        assert report.emit(as_json=False) == 0
        assert "NO CHECKS RAN" not in render(report)


class TestCounts:
    def test_failure_flips_verdict(self) -> None:
        report = Report("demo")
        report.check("ok one", True)
        report.fail("bad one", "because")
        assert (report.passed, len(report.failures)) == (1, 1)
        assert report.ok is False
        assert report.emit(as_json=False) == 1

    def test_all_passed_exits_zero(self) -> None:
        report = Report("demo")
        assert report.check("a", True) is True
        report.check("b", True, "detail")
        assert report.ok is True
        assert report.emit(as_json=False) == 0

    def test_check_returns_the_verdict_it_recorded(self) -> None:
        report = Report("demo")
        assert report.check("no", False) is False
        assert report.failures[0].name == "no"

    def test_checks_are_coerced_to_strings(self) -> None:
        report = Report("demo")
        report.check(123, 1, None)  # type: ignore[arg-type]
        check = report.checks[0]
        assert (check.name, check.ok, check.detail) == ("123", True, "None")


class TestJson:
    def test_shape_and_meta_merge(self) -> None:
        report = Report("demo")
        report.check("a", True)
        report.note("hello")
        report.meta["records"] = ["123"]
        data = report.to_dict()
        assert data["tool"] == "demo"
        assert data["ok"] is True
        assert (data["total"], data["passed"], data["failed"]) == (1, 1, 0)
        assert data["checks"][0] == {"name": "a", "ok": True, "detail": ""}
        assert data["notes"] == ["hello"]
        assert data["records"] == ["123"]

    def test_json_output_is_parseable(self, capsys) -> None:
        report = Report("demo")
        report.check("a", False, "boom")
        assert report.emit(as_json=True) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False and payload["failed"] == 1


class TestRender:
    def test_header_counts(self) -> None:
        report = Report("demo")
        report.check("a", True)
        report.fail("b")
        head = render(report).splitlines()[0]
        assert head == "paperlint demo: 1/2 pass, 1 FAIL"

    def test_long_names_are_truncated_with_ellipsis(self) -> None:
        report = Report("demo")
        report.check("x" * 120, True)
        line = [ln for ln in render(report).splitlines() if "PASS" in ln][0]
        assert "\u2026" in line
        # 46 (kolom nama) + "  PASS  " + "…" tidak boleh melebar tanpa batas
        assert len(line) <= len("  PASS  ") + 46

    def test_detail_only_when_present(self) -> None:
        report = Report("demo")
        report.check("with detail", True, "42 files")
        report.check("without detail", True)
        lines = render(report).splitlines()
        assert any("42 files" in ln for ln in lines)
        assert all(ln == ln.rstrip() for ln in lines)

    def test_notes_are_prefixed(self) -> None:
        report = Report("demo")
        report.check("a", True)
        report.note("satu catatan")
        assert "  note: satu catatan" in render(report)
