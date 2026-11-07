"""Figure layout gate: measure the rendered figure instead of looking at it.

Why this exists: real figure defects (content bounding box 1.91x the canvas
width, a PNG that came out landscape when it was meant to be portrait, a 'mode:
L' that was claimed while the file stayed RGBA) are invisible to a human glance,
and automatic transcription (OCR/vision) on 6-9 pt text invents values outright.
So this measures the matplotlib objects and the output file directly.

Checks:
  1. render twice -> identical output hash (determinism; also proves no
     bbox_inches="tight", which makes canvas size depend on content)
  2. file properties: colour mode, minimum footprint, portrait orientation
  3. every ax.text sits inside its container box, and the content bounding box
     does not exceed the canvas
  4. key facts are actually drawn -- read from the text objects, not from an
     escaped source file

Honest limits: to measure the live figure it executes your plotting script with
`fig.savefig(...)` / `plt.close(...)` lines neutralised. That is a heuristic on
top of trusted local code, not a sandbox -- never point it at a script you would
not run.
"""

from __future__ import annotations

import argparse  # noqa: F401  (kept for symmetry with sibling modules)
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .report import Report

SAVEFIG_RX = re.compile(r"^(fig\.savefig\(.*|plt\.close\(.*)$", re.MULTILINE)
FIGURE_NAMES = ("fig", "figure", "f")


def _deps():
    try:
        import matplotlib
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on extras
        raise RuntimeError(
            "matplotlib and Pillow are required: pip install 'paperlint[figures]'"
        ) from exc
    matplotlib.use("Agg")
    return matplotlib, Image


def load_figure(source: str) -> tuple[Any, Any]:
    """Execute the plotting script with savefig/close neutralised, return (fig, ax).

    plt.close has to be neutralised too: otherwise fig.canvas degrades to
    FigureCanvasBase, which has no get_renderer(), and measurement fails.
    """
    _deps()
    namespace: dict[str, Any] = {"__name__": "paperlint_layout_gate"}
    code = SAVEFIG_RX.sub("pass", source)
    exec(compile(code, "<figure-script>", "exec"), namespace)
    for name in FIGURE_NAMES:
        if name in namespace and hasattr(namespace[name], "axes"):
            figure = namespace[name]
            break
    else:
        raise RuntimeError(
            "no figure object found (looked for fig/figure/f at module level)"
        )
    axis = next(iter(figure.axes), None)
    if axis is None:
        raise RuntimeError("figure has no axes")
    return figure, axis


def run(args: Any, report: Report) -> None:
    script = Path(args.script)
    png = Path(args.png)
    if not script.is_file():
        report.fail("plot script exists", str(script))
        return
    if not png.is_file():
        report.fail("rendered png exists", f"{png} — render once first")
        return

    _, Image = _deps()

    hashes: list[str] = []
    for attempt in (1, 2):
        result = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, check=False
        )
        noisy = "Warning" in result.stderr or "Error" in result.stderr
        report.check(
            f"render {attempt} exits 0 without warnings",
            result.returncode == 0 and not noisy,
            f"rc={result.returncode}",
        )
        hashes.append(hashlib.sha256(png.read_bytes()).hexdigest())
    report.check(
        "two renders are byte-identical",
        len(set(hashes)) == 1,
        hashes[0][:12],
    )

    image = Image.open(png)
    report.meta["size"] = list(image.size)
    if args.require_mode:
        report.check(
            f"colour mode is {args.require_mode}",
            image.mode == args.require_mode,
            image.mode,
        )
    if args.min_w or args.min_h:
        report.check(
            f"footprint >= {args.min_w}x{args.min_h}",
            image.size[0] >= args.min_w and image.size[1] >= args.min_h,
            str(image.size),
        )
    if args.require_portrait:
        report.check(
            "portrait (height > width)",
            image.size[1] > image.size[0],
            str(image.size),
        )

    import matplotlib.pyplot as plt

    try:
        figure, axis = load_figure(script.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        report.fail("plot script yields a measurable figure", f"{type(exc).__name__}: {exc}")
        return

    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    inverse = axis.transData.inverted()
    boxes = [
        inverse.transform(patch.get_window_extent(renderer).get_points())
        for patch in axis.patches
        if patch.__class__.__name__ == "FancyBboxPatch"
    ]
    if not boxes:
        report.note("no FancyBboxPatch containers found — containment check is vacuous")

    inside = 0
    overflowing: list[str] = []
    for text in sorted(axis.texts, key=lambda t: -t.get_position()[1]):
        bbox = inverse.transform(text.get_window_extent(renderer).get_points())
        host = next(
            (
                b
                for b in boxes
                if b[0][0] - args.text_tol <= bbox[0][0]
                and b[1][0] + args.text_tol >= bbox[1][0]
                and b[0][1] - args.text_tol <= bbox[0][1]
                and b[1][1] + args.text_tol >= bbox[1][1]
            ),
            None,
        )
        if host is None:
            overflowing.append(f"outside any box: {text.get_text()[:40]!r}")
            continue
        if (bbox[1][0] - bbox[0][0]) > host[1][0] - host[0][0] or (
            bbox[1][1] - bbox[0][1]
        ) > host[1][1] - host[0][1]:
            overflowing.append(f"overflows: {text.get_text()[:34]!r}")
        inside += 1

    if boxes:
        report.check(
            "every label fits inside its container",
            not overflowing and inside > 0,
            f"{inside} inside" + (f"; {overflowing}" if overflowing else ""),
        )

    ratio = figure.get_tightbbox(renderer).width / figure.get_size_inches()[0]
    report.check("content bbox <= canvas width", ratio <= 1.0, f"{ratio:.2f}x")

    if args.fact:
        drawn = "\n".join(t.get_text() for t in axis.texts)
        for needle in args.fact:
            report.check(f"drawn: {needle[:38]!r}", needle in drawn)

    plt.close(figure)
