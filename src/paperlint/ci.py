"""CI placement and wiring audit.

Written for the case that actually breaks: a repository that is one git repo but
several projects, so CI lands in a nested `.github/workflows` that GitHub never
reads, or a path filter excludes the workflow file itself so CI edits go
untested. Each failure below is a real defect, not a style preference.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .report import Report
from .shell import out, run


def _load_yaml():
    try:
        import yaml
    except ImportError:  # pragma: no cover - depends on extras
        return None
    return yaml


def run_ci(args: Any, report: Report) -> None:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        report.fail("repo root exists", str(root))
        return
    report.meta["root"] = str(root)

    yaml = _load_yaml()
    if yaml is None:
        report.fail("PyYAML installed", "pip install 'paperlint[ci]'")
        return

    workflows_dir = root / ".github" / "workflows"
    workflows = sorted(workflows_dir.glob("*.y*ml"))
    report.check("workflow directory exists", workflows_dir.is_dir(), str(workflows_dir))
    report.check(
        "at least one workflow at repo root",
        bool(workflows),
        f"{len(workflows)} file(s)",
    )

    nested = [
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.parent.name == "workflows"
        and p.parent.parent.name == ".github"
        and p.parents[2] != root
    ]
    report.check(
        "no workflow outside the root .github/workflows",
        not nested,
        ", ".join(str(p.relative_to(root)) for p in nested)
        or "none",
    )

    default_branch = "main"
    if args.online:
        raw = out(["gh", "repo", "view", "--json", "defaultBranchRef"], cwd=root)
        try:
            default_branch = json.loads(raw)["defaultBranchRef"]["name"]
        except (json.JSONDecodeError, KeyError, TypeError):
            report.note("gh unavailable: assuming default branch is 'main'")

    names: list[str] = []
    for workflow in workflows:
        base = workflow.name
        try:
            data = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 - malformed YAML never runs
            report.fail(f"{base} parses", str(exc).splitlines()[0][:80])
            continue

        triggers = data.get(True, data.get("on")) or {}
        if isinstance(triggers, str):
            triggers = {triggers: {}}
        push = triggers.get("push") or {}
        branches = push.get("branches") or []
        report.check(
            f"{base} triggers default branch",
            default_branch in branches or not branches,
            str(branches) if branches else "all branches",
        )

        names.append(str(data.get("name")))
        for job_name, job in (data.get("jobs") or {}).items():
            job = job or {}
            workdir = ((job.get("defaults") or {}).get("run") or {}).get(
                "working-directory"
            ) or ((data.get("defaults") or {}).get("run") or {}).get("working-directory")
            if workdir:
                report.check(
                    f"{base}/{job_name} working-directory exists",
                    (root / workdir).is_dir(),
                    workdir,
                )
            paths = push.get("paths")
            if paths:
                own = f".github/workflows/{base}"
                report.check(
                    f"{base} self-triggers when edited",
                    own in paths,
                    own if own in paths else f"{own} missing from paths",
                )

    report.check(
        "workflow names are unique",
        len(set(names)) == len(names),
        f"{len(names)} workflow(s)",
    )

    if args.online and workflows:
        head = out(["git", "rev-parse", "HEAD"], cwd=root)
        raw = out(["gh", "run", "list", "--limit", "30", "--json", "name,conclusion,headSha"], cwd=root)
        try:
            runs = [r for r in json.loads(raw) if r.get("headSha") == head]
        except json.JSONDecodeError:
            runs = []
            report.note("gh run list unavailable: CI outcome not checked")
        if runs:
            bad = {r["name"]: r["conclusion"] for r in runs if r["conclusion"] != "success"}
            report.check(
                f"every CI run for HEAD is green ({head[:8]})",
                not bad,
                str(bad) if bad else f"{len(runs)} run(s)",
            )
        else:
            report.note(f"no CI run recorded for HEAD {head[:8]} — nothing was triggered")
