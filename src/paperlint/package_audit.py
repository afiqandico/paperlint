"""Whole-package manuscript gate: one PASS/FAIL table for every deliverable.

This is the gate that replaced ad-hoc greps. It answers "is the package you are
about to submit actually consistent?" by checking the deliverables against a
recorded state AND against each other:

  sha       sha256 of each file vs a recorded map (full digest or a prefix)
  pages     PDF page count vs an expected value
  stale     forbidden strings that survived an edit
  voice     first-person plural that a single-author venue forbids
  cites     \\cite vs \\bibitem parity (inline-bibliography documents only)
  keywords  IEEEkeywords item count
  docx      no literal '??' and at least N embedded media files
  figures   embedded image rows in the PDF, and no '??' in the text layer
  highlights at most six bullets, each within a character budget
  cover     required tokens present in the flattened cover letter
  git       listed working trees are clean

Every check is independent: a missing file or a broken PDF fails that one row
instead of aborting the run, because a half-run audit is worse than a red one.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
import zipfile
from pathlib import Path
from typing import Any

from .report import Report
from .shell import out, require

CONFIG_SECTION = "package"


class ConfigError(RuntimeError):
    """A config file is unreadable or contains unknown keys."""


DEFAULTS: dict[str, Any] = {
    "base": ".",
    "sha_json": None,
    "pages": [],
    "tex": [],
    "stale": [],
    "voice": [],
    "docx": [],
    "pdf_figs": [],
    "min_media": 1,
    "highlights": None,
    "max_highlight_chars": 85,
    "kwexpect": 0,
    "cover_pdf": None,
    "cover_tokens": [],
    "git": [],
}

LIST_KEYS = frozenset(
    {"pages", "tex", "stale", "voice", "docx", "pdf_figs", "cover_tokens", "git"}
)

CITE_RX = re.compile(r"\\cite[a-zA-Z]*\{([^}]+)\}")
BIBITEM_RX = re.compile(r"\\bibitem\{([^}]+)\}")
BIBLIOGRAPHY_RX = re.compile(r"\\(?:bibliography|printbibliography)\b")
KEYWORDS_RX = re.compile(
    r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}", re.S
)
IMAGE_ROW_RX = re.compile(r"^\s*\d+\s")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    section = data.get(CONFIG_SECTION, {})
    if not isinstance(section, dict):
        raise ConfigError(f"[{CONFIG_SECTION}] must be a table in {path}")
    unknown = sorted(set(section) - set(DEFAULTS))
    if unknown:
        raise ConfigError(
            f"unknown key(s) in [{CONFIG_SECTION}]: {', '.join(unknown)}"
        )
    return section


def resolve_config(args: Any) -> dict[str, Any]:
    """Config file first, then command-line flags.

    Scalars given on the command line win. List-valued flags are appended to the
    config list: the usual case is a saved config plus one extra artefact to
    check right now, and appending never silently drops a recorded check.
    """
    cfg = dict(DEFAULTS)
    for key, value in load_config(getattr(args, "config", None)).items():
        cfg[key] = list(value) if key in LIST_KEYS and value else value

    for key in LIST_KEYS:
        cli = getattr(args, key, None) or []
        cfg[key] = list(cfg.get(key) or []) + [v for v in cli]

    for key in ("base", "sha_json", "highlights", "cover_pdf", "min_media",
                "kwexpect", "max_highlight_chars"):
        cli = getattr(args, key, None)
        if cli is not None:
            cfg[key] = cli
    return cfg


def pdf_pages(path: Path) -> str:
    text = out(["pdfinfo", str(path)])
    for line in text.splitlines():
        if line.lower().startswith("pages:"):
            return line.split(":", 1)[1].strip()
    return "?"


def run(args: Any, report: Report) -> None:
    cfg = resolve_config(args)
    base = Path(cfg["base"]).expanduser()
    report.meta["base"] = str(base)

    if not base.is_dir():
        report.fail("base directory exists", str(base))
        return

    needs_poppler = bool(
        cfg["pages"] or cfg["pdf_figs"] or (cfg["cover_pdf"] and cfg["cover_tokens"])
    )
    if needs_poppler:
        require("pdfinfo", "pdftotext")

    _check_sha(cfg, base, report)
    _check_pages(cfg, base, report)
    texts = _load_tex(cfg, base, report)
    _check_stale(cfg, texts, report)
    _check_voice(cfg, texts, report)
    _check_cites(cfg, texts, report)
    _check_keywords(cfg, texts, report)
    _check_docx(cfg, base, report)
    _check_pdf_figures(cfg, base, report)
    _check_highlights(cfg, base, report)
    _check_cover(cfg, base, report)
    _check_git(cfg, report)


def _check_sha(cfg: dict[str, Any], base: Path, report: Report) -> None:
    if not cfg["sha_json"]:
        return
    try:
        expected = json.loads(Path(cfg["sha_json"]).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        report.fail("sha map readable", f"{cfg['sha_json']}: {exc}")
        return
    if not isinstance(expected, dict):
        report.fail("sha map is an object", type(expected).__name__)
        return
    for rel, want in expected.items():
        path = base / rel
        if not path.is_file():
            report.fail(f"sha {rel}", "file missing")
            continue
        got = sha256_file(path)
        want_s = str(want).rstrip("\u2026").lower()
        ok = got.startswith(want_s)
        report.check(
            f"sha {rel}",
            ok,
            got[:16] if ok else f"got {got[:16]} want {want_s[:16]}",
        )


def _check_pages(cfg: dict[str, Any], base: Path, report: Report) -> None:
    for spec in cfg["pages"]:
        rel, _, want = str(spec).rpartition("=")
        if not rel:
            report.fail(f"pages {spec}", "expected rel/PATH.pdf=N")
            continue
        path = base / rel
        if not path.is_file():
            report.fail(f"pages {Path(rel).name}", "file missing")
            continue
        got = pdf_pages(path)
        report.check(f"pages {Path(rel).name}", got == want, f"{got} (want {want})")


def _load_tex(cfg: dict[str, Any], base: Path, report: Report) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for rel in cfg["tex"]:
        path = base / rel
        try:
            texts.append((rel, path.read_text(encoding="utf-8", errors="replace")))
        except OSError as exc:
            report.fail(f"tex {Path(rel).name}", str(exc))
    return texts


def _check_stale(cfg: dict[str, Any], texts: list[tuple[str, str]], report: Report) -> None:
    for pattern in cfg["stale"]:
        hits = [rel for rel, text in texts if pattern in text]
        report.check(
            f'stale "{pattern}"',
            not hits,
            ",".join(Path(h).name for h in hits) or "0",
        )


def _check_voice(cfg: dict[str, Any], texts: list[tuple[str, str]], report: Report) -> None:
    for word in cfg["voice"]:
        rx = re.compile(r"\b" + re.escape(word) + r"\b", re.I)
        hits = [rel for rel, text in texts if rx.search(text)]
        report.check(
            f'voice "{word}"',
            not hits,
            ",".join(Path(h).name for h in hits) or "0",
        )


def _check_cites(cfg: dict[str, Any], texts: list[tuple[str, str]], report: Report) -> None:
    for rel, text in texts:
        cited: set[str] = set()
        for match in CITE_RX.findall(text):
            cited.update(key.strip() for key in match.split(","))
        if not cited:
            continue
        items = set(BIBITEM_RX.findall(text))
        if not items:
            # BibTeX builds keep keys in the .bib file, which this gate does not
            # parse; a real bibliography still present means "not applicable",
            # a document with citations and no bibliography at all is a defect.
            if BIBLIOGRAPHY_RX.search(text):
                report.note(
                    f"{Path(rel).name}: cite/bibitem parity skipped "
                    "(BibTeX bibliography, no inline \\bibitem)"
                )
            else:
                report.fail(f"cites==bib {Path(rel).name}", f"{len(cited)} cited, no bibliography")
            continue
        report.check(
            f"cites==bib {Path(rel).name}",
            cited == items,
            f"cited {len(cited)} bib {len(items)}"
            + ("" if cited == items else f"; only-cited {_sample(cited - items)}"
               f"; only-bib {_sample(items - cited)}"),
        )


def _sample(values: set[str], limit: int = 3) -> str:
    ordered = sorted(values)
    head = ",".join(ordered[:limit])
    return head + ("…" if len(ordered) > limit else "")


def _check_keywords(cfg: dict[str, Any], texts: list[tuple[str, str]], report: Report) -> None:
    expected = int(cfg["kwexpect"] or 0)
    if not expected:
        return
    for rel, text in texts:
        match = KEYWORDS_RX.search(text)
        if match is None:
            report.fail(f"keywords {Path(rel).name}", "no IEEEkeywords environment")
            continue
        items = [item for item in match.group(1).split(",") if item.strip()]
        report.check(
            f"keywords {Path(rel).name}",
            len(items) == expected,
            f"{len(items)} (want {expected})",
        )


def _check_docx(cfg: dict[str, Any], base: Path, report: Report) -> None:
    for rel in cfg["docx"]:
        path = base / rel
        if not path.is_file():
            report.fail(f"docx {Path(rel).name}", "file missing")
            continue
        try:
            with zipfile.ZipFile(path) as zf:
                xml = zf.read("word/document.xml").decode("utf-8", "replace")
                media = [n for n in zf.namelist() if n.startswith("word/media/")]
        except (zipfile.BadZipFile, KeyError, OSError) as exc:
            report.fail(f"docx {Path(rel).name}", f"unreadable: {exc}")
            continue
        placeholder = xml.count("??")
        ok = placeholder == 0 and len(media) >= int(cfg["min_media"])
        report.check(
            f"docx {Path(rel).name}",
            ok,
            f"??={placeholder} media={len(media)} (want >={cfg['min_media']})",
        )


def _check_pdf_figures(cfg: dict[str, Any], base: Path, report: Report) -> None:
    for spec in cfg["pdf_figs"]:
        rel, _, minimum = str(spec).rpartition(":")
        if not rel:
            report.fail(f"figures {spec}", "expected rel/PATH.pdf:N")
            continue
        path = base / rel
        name = Path(rel).name
        if not path.is_file():
            report.fail(f"figures {name}", "file missing")
            continue
        listing = out(["pdfimages", "-list", str(path)])
        # The type column contains the literal word "image", so filter on the
        # leading numeric row index, never on the presence of "image".
        rows = [ln for ln in listing.splitlines() if IMAGE_ROW_RX.match(ln)]
        gray = sum(1 for ln in rows if "gray" in ln.lower())
        report.check(
            f"figures {name} >= {minimum}",
            len(rows) >= int(minimum),
            f"{len(rows)} rows (gray={gray})",
        )
        text = out(["pdftotext", str(path), "-"])
        report.check(f"pdf text no ?? {name}", "??" not in text)


def _check_highlights(cfg: dict[str, Any], base: Path, report: Report) -> None:
    if not cfg["highlights"]:
        return
    path = base / cfg["highlights"]
    try:
        bullets = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError as exc:
        report.fail("highlights readable", str(exc))
        return
    limit = int(cfg["max_highlight_chars"])
    too_long = [b for b in bullets if len(b) > limit]
    report.check(
        f"highlights 1-6 bullets, each <={limit} chars",
        0 < len(bullets) <= 6 and not too_long,
        f"{len(bullets)} bullets, {len(too_long)} over limit",
    )


def _check_cover(cfg: dict[str, Any], base: Path, report: Report) -> None:
    if not (cfg["cover_pdf"] and cfg["cover_tokens"]):
        return
    path = base / cfg["cover_pdf"]
    if not path.is_file():
        report.fail("cover letter exists", str(path))
        return
    text = out(["pdftotext", str(path), "-"])
    if not text:
        report.fail("cover letter text layer", "empty (scanned image?)")
        return
    for token in cfg["cover_tokens"]:
        report.check(f'cover "{token}"', token in text)


def _check_git(cfg: dict[str, Any], report: Report) -> None:
    for directory in cfg["git"]:
        path = Path(directory).expanduser()
        label = path.resolve().name or str(path.resolve())
        if not (path / ".git").exists():
            report.fail(f"git clean ({label})", f"not a git work tree: {path}")
            continue
        status = out(["git", "-C", str(path), "status", "--short"])
        report.check(
            f"git clean ({label})",
            status == "",
            status.splitlines()[0][:40] if status else "clean",
        )
