"""Command-line interface.

Every handler mutates a shared Report and never prints pass/fail lines itself, so
the exit code, the human table and the JSON form can never disagree. Anything
that goes wrong mid-run (missing binary, unreadable file, missing optional
dependency) becomes a FAIL row instead of a traceback: a half-finished audit
that exits with a stack trace is easy to mistake for a clean run.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .report import Report
from .shell import ToolMissing

EPILOG = """\
exit codes: 0 = every check passed, 1 = at least one check failed,
            2 = usage error.

A run that executed no checks also exits 1: an empty gate is not a pass.
Add --json to any command for a machine-readable report.
"""

TOOLS = {
    "package": "manuscript package",
    "refs": "manuscript refs",
    "paths": "manuscript paths",
    "docx-structure": "manuscript docx-structure",
    "docx-restyle": "manuscript docx-restyle",
    "figure": "manuscript figure",
    "ci": "repo ci",
    "divergence": "repo divergence",
    "manifest": "verify manifest",
    "zenodo": "verify zenodo",
}


def _handler(name: str):
    """Import the module lazily so a missing optional dependency only bites
    the subcommand that needs it."""

    if name == "package":
        from . import package_audit

        return package_audit.run
    if name == "refs":
        from . import refs

        return refs.run
    if name == "paths":
        from . import docpaths

        return docpaths.run
    if name == "docx-structure":
        from . import docx_tools

        return docx_tools.run_structure
    if name == "docx-restyle":
        from . import docx_tools

        return docx_tools.run_restyle
    if name == "figure":
        from . import figures

        return figures.run
    if name == "ci":
        from . import ci

        return ci.run_ci
    if name == "divergence":
        from . import divergence

        return divergence.run_divergence
    if name == "manifest":
        from . import manifest

        return manifest.run_manifest
    if name == "zenodo":
        from . import zenodo

        return zenodo.run_zenodo
    raise KeyError(name)


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit a JSON report")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperlint",
        description="Deterministic pre-submission gates for manuscripts and "
        "research repositories.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"paperlint {__version__}"
    )
    groups = parser.add_subparsers(dest="group", metavar="GROUP", title="groups")

    man = groups.add_parser("manuscript", help="manuscript-side gates")
    msub = man.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # --- manuscript package -------------------------------------------------
    pkg = msub.add_parser(
        "package",
        help="audit a whole submission package in one pass",
        description="Checks deliverables against a recorded state and against "
        "each other. Flags are additive; a TOML config can supply the long "
        "lists so repeat runs are one word.",
    )
    pkg.add_argument("--config", help="TOML file with a [package] table")
    pkg.add_argument("--base", help="directory relative paths resolve against (default: .)")
    pkg.add_argument("--sha-json", dest="sha_json", help='{"rel/path": "sha256"} map')
    pkg.add_argument("--pages", action="append", default=[], help="REL.pdf=N")
    pkg.add_argument("--tex", action="append", default=[], help="LaTeX source to scan")
    pkg.add_argument("--stale", action="append", default=[], help="forbidden substring")
    pkg.add_argument("--voice", action="append", default=[], help="forbidden word (e.g. we)")
    pkg.add_argument("--docx", action="append", default=[], help="DOCX to inspect")
    pkg.add_argument(
        "--pdf-figs", dest="pdf_figs", action="append", default=[], help="REL.pdf:MIN"
    )
    pkg.add_argument("--min-media", dest="min_media", type=int, help="min embedded media")
    pkg.add_argument("--highlights", help="highlights file (1-6 bullets)")
    pkg.add_argument(
        "--max-highlight-chars", dest="max_highlight_chars", type=int, help="default 85"
    )
    pkg.add_argument("--kwexpect", type=int, help="expected IEEEkeywords count")
    pkg.add_argument("--cover-pdf", dest="cover_pdf", help="cover letter PDF")
    pkg.add_argument(
        "--cover-token",
        dest="cover_tokens",
        action="append",
        default=[],
        help="string that must appear in the cover letter",
    )
    pkg.add_argument(
        "--git", action="append", default=[], help="git work tree that must be clean"
    )
    _add_json(pkg)
    pkg.set_defaults(command="package")

    # --- manuscript refs ----------------------------------------------------
    rfs = msub.add_parser(
        "refs",
        help="rewrite \\ref from the .aux so pandoc DOCX has no '??'",
    )
    rfs.add_argument("source", help=".tex file built at least twice with pdflatex")
    rfs.add_argument("--out", help="write the rewritten source here (default: dry run)")
    rfs.add_argument("--aux", help="explicit .aux path (default: alongside source)")
    rfs.add_argument(
        "--commands",
        default="ref",
        help="comma-separated macros to resolve, e.g. 'ref,eqref' (default: ref)",
    )
    _add_json(rfs)
    rfs.set_defaults(command="refs")

    # --- manuscript paths ---------------------------------------------------
    pts = msub.add_parser(
        "paths", help="find dangling path references and stale-claim wording"
    )
    pts.add_argument("root", help="document tree to scan")
    pts.add_argument("--patterns", help="rules file: one 'name = regex' per line")
    pts.add_argument("--ext", default=".md,.txt,.html", help="extensions (default .md,.txt,.html)")
    pts.add_argument("--skip", default=".git,archive,__pycache__,node_modules")
    pts.add_argument(
        "--resolve", action="append", default=[], help="extra root to resolve tokens against"
    )
    pts.add_argument(
        "--strict", action="store_true", help="also fail on any pattern hit"
    )
    _add_json(pts)
    pts.set_defaults(command="paths")

    # --- manuscript docx-* --------------------------------------------------
    dstruct = msub.add_parser(
        "docx-structure", help="dump paragraph formatting to compare template vs build"
    )
    dstruct.add_argument("template", help="reference DOCX")
    dstruct.add_argument("build", nargs="?", help="DOCX to compare against the template")
    dstruct.add_argument("--max-paragraphs", dest="max_paragraphs", type=int, default=10**9)
    _add_json(dstruct)
    dstruct.set_defaults(command="docx-structure")

    drestyle = msub.add_parser(
        "docx-restyle",
        help="restyle a pandoc DOCX into a formal document, then verify it",
    )
    drestyle.add_argument("path", help="DOCX to restyle in place")
    _add_json(drestyle)
    drestyle.set_defaults(command="docx-restyle")

    # --- manuscript figure --------------------------------------------------
    fig = msub.add_parser(
        "figure", help="measure a rendered figure instead of eyeballing it"
    )
    fig.add_argument("--script", required=True, help="plotting script")
    fig.add_argument("--png", required=True, help="rendered PNG")
    fig.add_argument("--min-w", dest="min_w", type=int, default=0)
    fig.add_argument("--min-h", dest="min_h", type=int, default=0)
    fig.add_argument("--require-mode", dest="require_mode", help="e.g. L for true grayscale")
    fig.add_argument("--require-portrait", dest="require_portrait", action="store_true")
    fig.add_argument("--fact", action="append", default=[], help="substring that must be drawn")
    fig.add_argument("--text-tol", dest="text_tol", type=float, default=0.05)
    _add_json(fig)
    fig.set_defaults(command="figure")

    # --- repo ---------------------------------------------------------------
    repo = groups.add_parser("repo", help="repository-side gates")
    rsub = repo.add_subparsers(dest="command", required=True, metavar="COMMAND")

    rci = rsub.add_parser(
        "ci", help="audit workflow placement, triggers and working directories"
    )
    rci.add_argument("root", nargs="?", default=".", help="repo root (default: .)")
    rci.add_argument(
        "--online",
        action="store_true",
        help="also query gh for the default branch and the CI runs of HEAD",
    )
    _add_json(rci)
    rci.set_defaults(command="ci")

    rdiv = rsub.add_parser("divergence", help="diff two git roots of the same project")
    rdiv.add_argument("live", help="working tree")
    rdiv.add_argument("published", help="snapshot / publication tree")
    _add_json(rdiv)
    rdiv.set_defaults(command="divergence")

    # --- verify -------------------------------------------------------------
    ver = groups.add_parser("verify", help="artefact and deposit verification")
    vsub = ver.add_subparsers(dest="command", required=True, metavar="COMMAND")

    vman = vsub.add_parser("manifest", help="recompute hashes and sizes from a manifest")
    vman.add_argument("manifest", help="manifest JSON or sha256sum file")
    vman.add_argument("--root", default=".", help="base directory (default: .)")
    vman.add_argument(
        "--digest-of",
        default=None,
        metavar="PATH",
        help="the artefact a bare 64-hex file refers to (it carries no filename)",
    )
    _add_json(vman)
    vman.set_defaults(command="manifest")

    vzen = vsub.add_parser("zenodo", help="inspect Zenodo records via the public API")
    vzen.add_argument("records", nargs="+", help="record id(s)")
    vzen.add_argument("--timeout", type=int, default=30)
    _add_json(vzen)
    vzen.set_defaults(command="zenodo")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2

    tool = TOOLS[args.command]
    report = Report(tool=tool)
    try:
        _handler(args.command)(args, report)
    except ToolMissing as exc:
        report.fail("required external tool available", str(exc))
    except RuntimeError as exc:
        report.fail("toolchain ready", str(exc))
    except KeyboardInterrupt:
        return 130
    return report.emit(getattr(args, "json", False))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
