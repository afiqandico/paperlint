"""Sweep a document tree for dangling path references and stale-claim wording.

Both checks get hand-written every audit round, and hand-written regexes either
over-report (filename fragments inside prose) or miss wording variants. This
prints the raw hits; classifying them is still a human job.

Known limitation, deliberately not hidden: the path token regex matches anything
that looks like `something.ext`, so prose fragments such as "see config.yaml"
are reported even when no file is referenced. That is why unresolved tokens are
a *finding to check*, not automatically a defect -- pass --strict only when the
tree is meant to be link-clean.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path
from typing import Any

from .report import Report

PATH_RX = re.compile(
    r"[A-Za-z0-9_][A-Za-z0-9_./\u2014 -]*\."
    r"(?:md|txt|docx|pdf|json|csv|py|html|tex|sh|png|log|svg|yml|yaml|toml|bib|cff)"
)
URL_RX = re.compile(r"^(?:https?|mailto|ftp):")


def load_patterns(path: Path | None) -> list[tuple[str, re.Pattern[str]]]:
    """One rule per line: `name = regex`; blank lines and '#' comments ignored."""
    rules: list[tuple[str, re.Pattern[str]]] = []
    if path is None:
        return rules
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, regex = line.partition("=")
        if not regex.strip():
            continue
        try:
            rules.append((name.strip(), re.compile(regex.strip())))
        except re.error:
            continue
    return rules


def scan(
    root: Path,
    exts: tuple[str, ...],
    skips: tuple[str, ...],
    extra_roots: list[Path],
    rules: list[tuple[str, re.Pattern[str]]],
) -> tuple[dict[str, list[str]], dict[str, list[str]], int]:
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix in exts and not any(s in str(p) for s in skips)
    ]
    unresolved: dict[str, list[str]] = collections.defaultdict(list)
    hits: dict[str, list[str]] = collections.defaultdict(list)

    for path in files:
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for name, rx in rules:
                if rx.search(line):
                    hits[name].append(f"{rel}:{lineno}")
            for match in PATH_RX.finditer(line):
                token = match.group(0).strip()
                before = line[match.start() - 1] if match.start() else ""
                if (
                    "*" in token
                    or URL_RX.match(token)
                    or token.startswith(("/", "~"))
                    # a token glued to a slash is an absolute path or the tail of
                    # a URL; the regex cannot start on '/' so it begins mid-path
                    or before in ("/", "\\")
                ):
                    continue
                forms = token_forms(token)
                candidates: list[Path] = []
                for form in forms:
                    candidates += [
                        root / form,
                        path.parent / form,
                        path.parent / Path(form).name,
                        *(d / form for d in extra_roots),
                    ]
                if not any(c.exists() for c in candidates):
                    unresolved[rel].append(forms[-1])
    return unresolved, hits, len(files)


def token_forms(token: str) -> list[str]:
    """Progressively drop leading words from a matched token.

    The path regex allows spaces (so `results/final table.csv` matches as one
    token), which makes it swallow the prose in front of the filename too:
    "see figure.png" matches whole. Trying the word suffixes as well keeps a
    real reference resolvable instead of reporting every sentence as dangling.
    """
    words = token.split()
    if len(words) <= 1:
        return [token]
    return [" ".join(words[index:]) for index in range(len(words))]


def run(args: Any, report: Report) -> None:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        report.fail("root directory exists", str(root))
        return

    exts = tuple(e if e.startswith(".") else "." + e for e in args.ext.split(",") if e)
    skips = tuple(s for s in args.skip.split(",") if s)
    extra = [Path(d).expanduser() for d in (args.resolve or [])]
    rules = load_patterns(Path(args.patterns) if args.patterns else None)

    unresolved, hits, scanned = scan(root, exts, skips, extra, rules)
    report.meta.update({"root": str(root), "files_scanned": scanned})

    total = sum(len(v) for v in unresolved.values())
    detail = f"{total} token(s) in {len(unresolved)} file(s)" if total else "0"
    if total:
        rel, tokens = min(unresolved.items())
        detail += f"; e.g. {Path(rel).name}: {', '.join(sorted(set(tokens))[:3])}"
    report.check("no dangling path references", total == 0, detail)

    for name, _ in rules:
        rows = hits.get(name, [])
        label = f'stale claim "{name}"'
        if args.strict:
            report.check(label, not rows, f"{len(rows)} hit(s)")
        else:
            report.note(f'{label}: {len(rows)} hit(s)' + (f" — {rows[0]}" if rows else ""))

    if total:
        report.note(
            "prose fragments often match the path regex: classify before editing"
        )
