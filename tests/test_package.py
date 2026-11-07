"""The whole-package gate: every check in isolation plus the config file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from conftest import make_pdf

TEX = r"""
\documentclass{article}
\begin{document}
Result \cite{alpha,beta} improves on prior work.
\begin{thebibliography}{9}
\bibitem{alpha} A. Author. 2024.
\bibitem{beta} B. Author. 2023.
\end{thebibliography}
\begin{IEEEkeywords}ids, adversarial ml, robustness\end{IEEEkeywords}
\end{document}
"""


def _package(tmp_path: Path) -> Path:
    base = tmp_path / "pkg"
    base.mkdir()
    (base / "paper.tex").write_text(TEX)
    make_pdf(base / "paper.pdf", "Results table")
    (base / "highlights.txt").write_text(
        "Adversarial traffic cuts evasion cost by 41%.\n"
        "Detection recall holds at 0.93 on CICIDS2017.\n"
    )
    from conftest import make_docx

    make_docx(base / "code.docx", text="Table 1 results", media=2)
    digest = hashlib.sha256((base / "paper.tex").read_bytes()).hexdigest()
    (base / "expects.json").write_text(json.dumps({"paper.tex": digest[:8]}))
    return base


def _base_args(base: Path) -> list[str]:
    return [
        "manuscript",
        "package",
        "--base",
        str(base),
        "--sha-json",
        str(base / "expects.json"),
        "--pages",
        "paper.pdf=1",
        "--tex",
        "paper.tex",
        "--voice",
        "we",
        "--stale",
        "TODO",
        "--docx",
        "code.docx",
        "--min-media",
        "2",
        "--pdf-figs",
        "paper.pdf:0",
        "--highlights",
        "highlights.txt",
        "--kwexpect",
        "3",
    ]


def test_clean_package_passes(tmp_path, run):
    code, out = run(*_base_args(_package(tmp_path)))
    assert code == 0, out
    assert "FAIL" not in out


def test_page_count_mismatch_fails(tmp_path, run):
    base = _package(tmp_path)
    args = _base_args(base)
    args[args.index("paper.pdf=1")] = "paper.pdf=15"
    code, out = run(*args)
    assert code == 1
    assert "pages paper.pdf" in out


def test_stale_string_fails(tmp_path, run):
    base = _package(tmp_path)
    (base / "paper.tex").write_text(TEX + "\n% TODO finish this\n")
    code, out = run(*_base_args(base))
    assert code == 1
    assert 'stale "TODO"' in out


def test_forbidden_voice_fails(tmp_path, run):
    base = _package(tmp_path)
    (base / "paper.tex").write_text(TEX.replace("Result", "We show"))
    code, out = run(*_base_args(base))
    assert code == 1
    assert 'voice "we"' in out


def test_sha_mismatch_fails(tmp_path, run):
    base = _package(tmp_path)
    (base / "expects.json").write_text(json.dumps({"paper.tex": "deadbeef"}))
    code, out = run(*_base_args(base))
    assert code == 1
    assert "sha paper.tex" in out


def test_cite_bibitem_mismatch_fails(tmp_path, run):
    base = _package(tmp_path)
    (base / "paper.tex").write_text(TEX.replace(r"\bibitem{beta} B. Author. 2023.", ""))
    code, out = run(*_base_args(base))
    assert code == 1
    assert "cites==bib" in out


def test_bibtex_bibliography_is_not_a_false_failure(tmp_path, run):
    base = _package(tmp_path)
    tex = TEX.replace(
        r"""\begin{thebibliography}{9}
\bibitem{alpha} A. Author. 2024.
\bibitem{beta} B. Author. 2023.
\end{thebibliography}""",
        r"\bibliography{refs}",
    )
    (base / "paper.tex").write_text(tex)
    digest = hashlib.sha256((base / "paper.tex").read_bytes()).hexdigest()
    (base / "expects.json").write_text(json.dumps({"paper.tex": digest[:8]}))
    code, out = run(*_base_args(base))
    assert code == 0, out
    assert "parity skipped" in out


def test_docx_placeholder_fails(tmp_path, run):
    base = _package(tmp_path)
    from conftest import make_docx

    make_docx(base / "code.docx", text="Table ?? results", media=2)
    code, out = run(*_base_args(base))
    assert code == 1
    assert "??=1" in out


def test_keyword_count_fails(tmp_path, run):
    base = _package(tmp_path)
    args = _base_args(base)
    args[-1] = "9"
    code, out = run(*args)
    assert code == 1
    assert "keywords paper.tex" in out


def test_highlights_over_limit_fails(tmp_path, run):
    base = _package(tmp_path)
    (base / "highlights.txt").write_text("x" * 90 + "\n")
    code, out = run(*_base_args(base))
    assert code == 1
    assert "highlights" in out


def test_git_dirty_worktree_fails(tmp_path, run):
    from conftest import git_init

    base = _package(tmp_path)
    tree = git_init(tmp_path / "tree", {"keep.txt": "x\n"})
    (tree / "untracked.txt").write_text("dirty\n")
    code, out = run(*_base_args(base), "--git", str(tree))
    assert code == 1
    assert "git clean" in out


def test_config_file_supplies_the_lists(tmp_path, run):
    base = _package(tmp_path)
    config = tmp_path / "paperlint.toml"
    config.write_text(
        f"""
[package]
base = "{base}"
sha_json = "{base / 'expects.json'}"
pages = ["paper.pdf=1"]
tex = ["paper.tex"]
stale = ["TODO"]
voice = ["we"]
docx = ["code.docx"]
min_media = 2
pdf_figs = ["paper.pdf:0"]
highlights = "highlights.txt"
kwexpect = 3
"""
    )
    code, out = run("manuscript", "package", "--config", str(config))
    assert code == 0, out


def test_unknown_config_key_is_rejected(tmp_path, run):
    config = tmp_path / "paperlint.toml"
    config.write_text('[package]\nbase = "."\nnot_a_real_key = 1\n')
    code, out = run("manuscript", "package", "--config", str(config))
    assert code == 1
    assert "unknown key" in out


def test_cli_flags_append_to_config(tmp_path, run):
    base = _package(tmp_path)
    config = tmp_path / "paperlint.toml"
    config.write_text(f'[package]\nbase = "{base}"\ntex = ["paper.tex"]\n')
    (base / "second.tex").write_text("clean\n")
    code, out = run(
        "manuscript", "package", "--config", str(config), "--tex", "second.tex"
    )
    assert code == 0, out
    assert "cites==bib second.tex" not in out
