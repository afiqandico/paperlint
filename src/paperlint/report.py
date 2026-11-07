"""Structured PASS/FAIL reporting shared by every gate.

Why a shared object: every one of these checks started life as a throwaway
script printing ad-hoc lines, so "did it pass?" had to be re-derived by eye each
run. One report object gives three things for free: a stable human table, a JSON
form for CI, and an exit code that is a real gate.

Design rule: a report that ran ZERO checks is not a pass. Silent passes are the
failure mode this package exists to prevent, so an empty report exits non-zero.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import IO, Any

_NAME_WIDTH = 46


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    """A single gate run: an ordered list of checks plus free-form notes."""

    tool: str
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    # Set when a tool legitimately performs no pass/fail checks (informational
    # tools only). Gates must leave this False.
    allow_empty: bool = False

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(Check(str(name), bool(ok), str(detail)))
        return bool(ok)

    def fail(self, name: str, detail: str = "") -> bool:
        return self.check(name, False, detail)

    def note(self, msg: str) -> None:
        self.notes.append(str(msg))

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def passed(self) -> int:
        return len(self.checks) - len(self.failures)

    @property
    def ok(self) -> bool:
        if not self.checks and not self.allow_empty:
            return False
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "total": len(self.checks),
            "passed": self.passed,
            "failed": len(self.failures),
            "checks": [asdict(c) for c in self.checks],
            "notes": self.notes,
            **self.meta,
        }

    def render(self, stream: IO[str] | None = None) -> None:
        stream = sys.stdout if stream is None else stream
        head = f"paperlint {self.tool}: {self.passed}/{len(self.checks)} pass"
        if self.failures:
            head += f", {len(self.failures)} FAIL"
        elif not self.checks and not self.allow_empty:
            head += ", NO CHECKS RAN"
        print(head, file=stream)

        width = min(max((len(c.name) for c in self.checks), default=0), _NAME_WIDTH)
        for c in self.checks:
            flag = "PASS" if c.ok else "FAIL"
            name = c.name
            if len(name) > width:
                name = name[: width - 1] + "\u2026"
            line = f"  {flag}  {name:<{width}}"
            if c.detail:
                line += f"  {c.detail}"
            print(line.rstrip(), file=stream)

        for n in self.notes:
            print(f"  note: {n}", file=stream)

        if not self.checks and not self.allow_empty:
            print(
                "  note: no check executed — refusing to report success "
                "(an empty gate is not a pass)",
                file=stream,
            )

    def emit(self, as_json: bool = False) -> int:
        """Print the report and return the process exit code (0 pass, 1 fail)."""
        if as_json:
            print(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        else:
            self.render()
        return 0 if self.ok else 1
