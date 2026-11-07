"""Reference pre-resolution, including the nested-brace .aux regression.

Regression story: a flat `\\newlabel{name}{{...}}` regex stops at the first `}`
inside a nested number field such as `{\\mbox  {VII-C}}`, silently dropping
labels so the DOCX ships "??". These tests pin the depth-tracking parser.
"""

from __future__ import annotations

from paperlint.refs import parse_aux, pre_resolve


def test_plain_label_resolves():
    aux = r"\newlabel{fig:one}{{1}{2}{}{figure.1}{}}"
    assert parse_aux(aux) == {"fig:one": "1"}


def test_nested_braces_in_number_field():
    aux = r"\newlabel{sec:x}{{\mbox  {VII-C}}{5}{}{section.VII-C}{}}"
    assert parse_aux(aux)["sec:x"] == r"\mbox  {VII-C}"


def test_leading_zero_is_stripped():
    aux = r"\newlabel{eq:z}{{007}{1}{}{}{}}"
    assert parse_aux(aux)["eq:z"] == "7"


def test_multiple_labels():
    aux = (
        r"\newlabel{a}{{1}{1}{}{}{}}"
        r"\newlabel{b}{{2}{2}{}{}{}}"
        r"\newlabel{c}{{\mbox  {IX-B}}{3}{}{}{}}"
    )
    labels = parse_aux(aux)
    assert sorted(labels) == ["a", "b", "c"]
    assert labels["c"] == r"\mbox  {IX-B}"


def test_pre_resolve_reports_missing_labels():
    tex = r"See \ref{known} and \ref{ghost}."
    rewritten, unresolved, missing = pre_resolve(tex, {"known": "3"})
    assert "3" in rewritten
    assert "??" in rewritten
    assert unresolved == ["ghost"]
    assert missing == ["ghost"]


def test_eqref_gets_parentheses():
    rewritten, _, _ = pre_resolve(
        r"as in \eqref{eq:a}", {"eq:a": "4"}, commands=("ref", "eqref")
    )
    assert "(4)" in rewritten


def test_cli_writes_rewritten_source(tmp_path, run):
    source = tmp_path / "paper.tex"
    source.write_text(r"Section \ref{sec:x}.")
    aux = tmp_path / "paper.aux"
    aux.write_text(r"\newlabel{sec:x}{{\mbox  {VII-C}}{5}{}{}{}}")
    out = tmp_path / "resolved.tex"

    code, output = run("manuscript", "refs", str(source), "--out", str(out))
    assert code == 0
    assert r"\mbox  {VII-C}" in out.read_text()
    assert "labels found in aux" in output


def test_cli_fails_when_aux_missing(tmp_path, run):
    source = tmp_path / "paper.tex"
    source.write_text("no refs")
    code, output = run("manuscript", "refs", str(source))
    assert code == 1
    assert "pdflatex twice" in output


def test_cli_fails_on_unresolved_reference(tmp_path, run):
    source = tmp_path / "paper.tex"
    source.write_text(r"\ref{ghost}")
    (tmp_path / "paper.aux").write_text(r"\newlabel{other}{{1}{1}{}{}{}}")
    code, output = run("manuscript", "refs", str(source))
    assert code == 1
    assert "every \\ref resolves" in output
