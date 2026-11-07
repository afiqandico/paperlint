"""Commands that need optional dependencies: figure, docx, zenodo."""

from __future__ import annotations

import pytest

FIGURE_SCRIPT = """\
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
ax.plot([0, 1], [0, 1])
ax.set_title("deterministic")
fig.savefig({target!r}, dpi=100)
plt.close(fig)
"""


def _figure_env(tmp_path):
    png = tmp_path / "fig.png"
    script = tmp_path / "gen.py"
    script.write_text(FIGURE_SCRIPT.format(target=str(png)))
    import subprocess
    import sys

    subprocess.run([sys.executable, str(script)], check=True)
    return script, png


def test_figure_gate_passes_on_a_clean_figure(tmp_path, run):
    pytest.importorskip("matplotlib")
    pytest.importorskip("PIL")
    script, png = _figure_env(tmp_path)
    code, out = run("manuscript", "figure", "--script", str(script), "--png", str(png))
    assert code == 0, out
    assert "byte-identical" in out


def test_figure_gate_detects_missing_fact(tmp_path, run):
    pytest.importorskip("matplotlib")
    pytest.importorskip("PIL")
    script, png = _figure_env(tmp_path)
    code, out = run(
        "manuscript",
        "figure",
        "--script",
        str(script),
        "--png",
        str(png),
        "--fact",
        "0.93 recall",
    )
    assert code == 1
    assert "drawn" in out


def test_figure_gate_detects_landscape_when_portrait_required(tmp_path, run):
    pytest.importorskip("matplotlib")
    pytest.importorskip("PIL")
    script, png = _figure_env(tmp_path)
    code, out = run(
        "manuscript",
        "figure",
        "--script",
        str(script),
        "--png",
        str(png),
        "--require-portrait",
    )
    assert code == 1
    assert "portrait" in out


def _make_docx(path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("A heading", level=1)
    document.add_paragraph("Body text for the paragraph.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "header"
    table.cell(1, 0).text = "value"
    document.save(str(path))
    return path


def test_docx_restyle_applies_and_verifies(tmp_path, run):
    pytest.importorskip("docx")
    path = _make_docx(tmp_path / "paper.docx")
    code, out = run("manuscript", "docx-restyle", str(path))
    assert code == 0, out
    assert "page size is A4" in out
    assert "footer page field present" in out


def test_docx_structure_is_informational(tmp_path, run):
    pytest.importorskip("docx")
    path = _make_docx(tmp_path / "paper.docx")
    code, out = run("manuscript", "docx-structure", str(path))
    assert code == 0
    assert "Total paragraphs" in out


def test_zenodo_reports_record_facts(tmp_path, run, monkeypatch):
    from paperlint import zenodo

    monkeypatch.setattr(
        zenodo,
        "fetch",
        lambda record, timeout=30: {
            "metadata": {"conceptrecid": "999", "version": "1.0.1",
                         "license": "MIT", "access_right": "restricted"},
            "files": [],
            "created": "2026-11-01T00:00:00+00:00",
        },
    )
    code, out = run("verify", "zenodo", "123")
    assert code == 0
    assert "anonymous_files=0" in out
    assert "overclaim" in out


def test_zenodo_unreachable_record_fails(run, monkeypatch):
    from paperlint import zenodo

    monkeypatch.setattr(zenodo, "fetch", lambda record, timeout=30: None)
    code, out = run("verify", "zenodo", "000")
    assert code == 1
    assert "reachable" in out


def test_zenodo_json_has_record_meta(monkeypatch, run_json):
    from paperlint import zenodo

    monkeypatch.setattr(
        zenodo,
        "fetch",
        lambda record, timeout=30: {
            "metadata": {"conceptrecid": "5", "version": None, "license": "cc-by-4.0",
                         "access_right": "open"},
            "files": [{"key": "a.zip"}],
            "created": "2026-10-01T00:00:00+00:00",
        },
    )
    code, payload = run_json("verify", "zenodo", "5")
    assert code == 0
    assert payload["records"] == ["5"]
    assert any("concept=5" in n for n in payload["notes"])
