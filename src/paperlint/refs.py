"""Pre-resolve LaTeX \\ref (and friends) from the .aux file.

pandoc does not resolve \\ref: without this step the DOCX ships literal "??" or
"\\ref{...}" for every cross-reference. Resolve from the .aux after a two-pass
pdflatex build, then feed the rewritten source to pandoc.

The non-obvious part is the .aux parser. A naive `\\newlabel{name}{{...}}` regex
fails on labels whose number field contains nested braces -- for example
`\\newlabel{sec:x}{{\\mbox  {VII-C}}{5}{...}` -- because the pattern stops at the
first `}` inside `{VII-C}` and silently drops labels, shipping "??" into the
deliverable. The parser below tracks brace depth instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .report import Report

NEWLABEL_RX = re.compile(r"\\newlabel\{([^}]+)\}\{")
DEFAULT_COMMANDS = ("ref",)


def parse_aux(aux_text: str) -> dict[str, str]:
    """Return {label: display_number} from .aux text, tolerating nested braces."""
    labels: dict[str, str] = {}
    for match in NEWLABEL_RX.finditer(aux_text):
        name = match.group(1)
        start = match.end()
        if start >= len(aux_text) or aux_text[start] != "{":
            continue
        depth = 0
        index = start
        while index < len(aux_text):
            char = aux_text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        number = aux_text[start + 1 : index].lstrip("0") or "0"
        labels[name] = number
    return labels


def pre_resolve(
    tex: str, labels: dict[str, str], commands: tuple[str, ...] = DEFAULT_COMMANDS
) -> tuple[str, list[str], list[str]]:
    """Rewrite \\ref-like macros with their numbers.

    Returns (rewritten_text, unresolved_labels, missing_labels). `unresolved`
    are refs that ended up as "??"; `missing` are refs the .aux never defined.
    """
    pattern = re.compile(r"\\(" + "|".join(commands) + r")\{([^}]+)\}")

    def repl(match: re.Match[str]) -> str:
        command, label = match.group(1), match.group(2)
        number = labels.get(label)
        if number is None:
            return "??"
        return f"({number})" if command == "eqref" else number

    rewritten = pattern.sub(repl, tex)
    unresolved = [
        m.group(2) for m in re.finditer(r"\\(" + "|".join(commands) + r")\{([^}]+)\}", tex)
        if m.group(2) not in labels
    ]
    return rewritten, unresolved, sorted(set(unresolved))


def run(args: Any, report: Report) -> None:
    source = Path(args.source)
    if not source.is_file():
        report.fail("source tex exists", str(source))
        return

    aux = Path(args.aux).expanduser() if args.aux else source.with_suffix(".aux")
    report.meta.update({"source": str(source), "aux": str(aux)})

    if not aux.is_file():
        report.fail(
            "aux file exists",
            f"{aux} — run pdflatex twice before resolving references",
        )
        return

    labels = parse_aux(aux.read_text(encoding="utf-8", errors="replace"))
    commands = tuple(c.strip() for c in args.commands.split(",") if c.strip())
    rewritten, unresolved, missing = pre_resolve(
        source.read_text(encoding="utf-8", errors="replace"), labels, commands
    )

    report.check("labels found in aux", bool(labels), f"{len(labels)} labels")
    report.check(
        "every \\ref resolves",
        not missing,
        "all resolved" if not missing else f"missing from aux: {', '.join(missing[:6])}",
    )

    if args.out:
        Path(args.out).write_text(rewritten, encoding="utf-8")
        report.meta["out"] = str(args.out)
        report.note(f"rewritten source written to {args.out}")
    else:
        report.note("no --out given: dry run, nothing written")

    if unresolved:
        report.note(f"{len(unresolved)} unresolved reference(s)")
