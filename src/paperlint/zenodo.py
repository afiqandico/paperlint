"""Inspect a deposit record (Zenodo / InvenioRDM) through the public API.

No login, no token. Answers questions that are routinely answered from memory
and therefore wrong:

  * is this DOI the concept record or a version, and what is its parent
  * what the access setting actually is
  * how many files an anonymous visitor can actually see
  * the age of the record in days (the file-edit window is 30 days)

The last check matters: a record marked restricted with zero public files makes
any "archived in a public repository" claim in a manuscript an overclaim.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any

from .report import Report

API = "https://zenodo.org/api/records/{}"
FILE_WINDOW_DAYS = 30


def fetch(record: str, timeout: int = 30) -> dict | None:
    try:
        with urllib.request.urlopen(API.format(record), timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def run_zenodo(args: Any, report: Report) -> None:
    report.meta["records"] = list(args.records)
    for record in args.records:
        data = fetch(record, timeout=args.timeout)
        if data is None:
            report.fail(f"record {record} reachable", "HTTP error or timeout")
            continue

        metadata = data.get("metadata", {}) or {}
        concept = metadata.get("conceptrecid") or data.get("conceptrecid")
        is_concept = str(concept) == str(record) or metadata.get("version") is None
        files = data.get("files", []) or []
        created = (data.get("created") or "")[:10]
        age = None
        if created:
            age = (date.today() - datetime.strptime(created, "%Y-%m-%d").date()).days

        # the API returns the licence either as a string or as {"id": ...}
        licence = metadata.get("license")
        if isinstance(licence, dict):
            licence = licence.get("id") or licence.get("title")

        report.check(f"record {record} reachable", True, "concept" if is_concept else "version")
        report.note(
            f"{record}: concept={concept} version={metadata.get('version')} "
            f"license={licence} access={metadata.get('access_right')} "
            f"anonymous_files={len(files)} created={created} age={age}d"
        )

        if age is not None:
            remaining = FILE_WINDOW_DAYS - age
            report.note(
                f"{record}: file window "
                + (
                    f"open ({remaining} day(s) left)"
                    if remaining >= 0
                    else "closed (past 30 days: use New version or support)"
                )
            )

        if metadata.get("access_right") == "restricted" and not files:
            report.note(
                f"{record}: restricted with 0 public files — claiming it is "
                "publicly archived would be an overclaim"
            )


def render_json(data: dict) -> str:  # pragma: no cover - convenience only
    return json.dumps(data, indent=2)
