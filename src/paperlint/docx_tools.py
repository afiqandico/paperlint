"""DOCX inspection and deterministic restyling.

Two jobs that always come up when a journal demands a Word file:

  structure  dump paragraph-level formatting of a template and a build so the
             two can be compared row by row (style, indent, spacing, blank
             paragraphs) instead of by eye.
  restyle    turn a pandoc-built DOCX into a formal document (A4, Times New
             Roman, black heading hierarchy, justified body, bordered tables
             with a shaded repeating header, centred page-number field).

`restyle` reopens the saved file and verifies the result: a style edit that
reports success without reading the file back is exactly the kind of claim this
package exists to stop. It also kills pandoc's blue headings, which is the
single most common "why does my DOCX look wrong" defect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .report import Report

A4_WIDTH_CM = 21.0
A4_HEIGHT_CM = 29.7
BODY_FONT = "Times New Roman"
BODY_PT = 11
CELL_PT = 10


def _docx():
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - depends on extras
        raise RuntimeError(
            "python-docx is required: pip install 'paperlint[docx]'"
        ) from exc
    return docx


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if hasattr(value, "cm"):
        return f"{value.cm:.2f}cm"
    if hasattr(value, "pt"):
        return f"{value.pt:.0f}pt"
    return str(value)


def dump(path: Path, max_paragraphs: int = 10**9) -> None:
    docx = _docx()
    document = docx.Document(str(path))
    print(f"\n===== {path} =====")
    for index, section in enumerate(document.sections):
        print(
            f"  sec{index}: page {section.page_width.cm:.1f}x{section.page_height.cm:.1f} | "
            f"margin T{section.top_margin.cm:.1f} R{section.right_margin.cm:.1f} "
            f"B{section.bottom_margin.cm:.1f} L{section.left_margin.cm:.1f}"
        )
    blanks = 0
    for index, paragraph in enumerate(document.paragraphs):
        if index >= max_paragraphs:
            break
        text = paragraph.text.strip()
        if not text:
            blanks += 1
            continue
        fmt = paragraph.paragraph_format
        print(
            f"  {index:3d} | {paragraph.style.name:18s} | {paragraph.alignment!s:8s} | "
            f"first={_fmt(fmt.first_line_indent):7s} | "
            f"before={_fmt(fmt.space_before):6s} | after={_fmt(fmt.space_after):6s} | "
            f"blanks_before={blanks:2d} | {text[:40]}"
        )
        blanks = 0
    print(f"\nTotal paragraphs: {len(document.paragraphs)}")


def run_structure(args: Any, report: Report) -> None:
    _docx()  # fail fast with a clear message before printing anything
    paths = [Path(args.template), Path(args.build)] if args.build else [Path(args.template)]
    for path in paths:
        if not path.is_file():
            report.fail(f"docx readable {path.name}", "file missing")
            continue
        dump(path, args.max_paragraphs)
        report.meta.setdefault("dumped", []).append(str(path))
    report.allow_empty = True
    report.note("informational dump: compare the two tables field by field")


def apply_style(path: Path) -> None:
    """Restyle the DOCX in place."""
    docx = _docx()
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    document = docx.Document(str(path))
    section = document.sections[0]
    section.page_width, section.page_height = Cm(A4_WIDTH_CM), Cm(A4_HEIGHT_CM)
    section.left_margin, section.right_margin = Cm(3.0), Cm(2.5)
    section.top_margin, section.bottom_margin = Cm(2.5), Cm(2.5)
    section.footer_distance = Cm(1.25)

    def set_font(style, size: int, bold: bool | None = None, color=None) -> None:
        style.font.name = BODY_FONT
        style.font.size = Pt(size)
        if bold is not None:
            style.font.bold = bold
        if color is not None:
            style.font.color.rgb = color
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs"):
            rfonts.set(qn(attr), BODY_FONT)

    black = RGBColor(0, 0, 0)
    normal = document.styles["Normal"]
    set_font(normal, BODY_PT)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = 1.15

    for name, size, before, after in (
        ("Heading 1", 14, 18, 10),
        ("Heading 2", 12, 12, 6),
    ):
        try:
            style = document.styles[name]
        except KeyError:
            continue
        set_font(style, size, bold=True, color=black)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    try:
        first = document.styles["First Paragraph"]
        set_font(first, BODY_PT)
        first.paragraph_format.space_after = Pt(6)
    except KeyError:
        pass

    for paragraph in document.paragraphs:
        if paragraph.style.name.startswith("Heading") or not paragraph.text.strip():
            continue
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for run in paragraph.runs:
            run.font.name = BODY_FONT
            run.font.size = Pt(BODY_PT)

    def shade(cell, fill: str) -> None:
        tcpr = cell._tc.get_or_add_tcPr()
        shd = tcpr.find(qn("w:shd"))
        if shd is None:
            shd = OxmlElement("w:shd")
            tcpr.append(shd)
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)

    def borders(table) -> None:
        tblpr = table._tbl.tblPr
        element = tblpr.find(qn("w:tblBorders"))
        if element is None:
            element = OxmlElement("w:tblBorders")
            tblpr.append(element)
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            line = element.find(qn("w:" + edge))
            if line is None:
                line = OxmlElement("w:" + edge)
                element.append(line)
            line.set(qn("w:val"), "single")
            line.set(qn("w:sz"), "4")
            line.set(qn("w:space"), "0")
            line.set(qn("w:color"), "000000")

    for table in document.tables:
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        borders(table)
        for row_index, row in enumerate(table.rows):
            if row_index == 0:
                trpr = row._tr.get_or_add_trPr()
                header = OxmlElement("w:tblHeader")
                header.set(qn("w:val"), "true")
                trpr.append(header)
            for cell in row.cells:
                if row_index == 0:
                    shade(cell, "D9D9D9")
                for paragraph in cell.paragraphs:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    paragraph.paragraph_format.space_after = Pt(2)
                    paragraph.paragraph_format.space_before = Pt(2)
                    for run in paragraph.runs:
                        run.font.name = BODY_FONT
                        run.font.size = Pt(CELL_PT)
                        if row_index == 0:
                            run.font.bold = True

    footer = section.footer
    target = footer.paragraphs[0]
    target.alignment = WD_ALIGN_PARAGRAPH.CENTER
    target.text = ""
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    run_element = OxmlElement("w:r")
    text_element = OxmlElement("w:t")
    text_element.text = "1"
    run_element.append(text_element)
    field.append(run_element)
    target.add_run()._r.addprevious(field)

    document.save(str(path))


def verify_style(path: Path) -> list[tuple[str, bool, str]]:
    """Reopen the file and confirm the style actually landed."""
    docx = _docx()
    document = docx.Document(str(path))
    section = document.sections[0]
    results: list[tuple[str, bool, str]] = []

    width_ok = abs(section.page_width.cm - A4_WIDTH_CM) < 0.1
    height_ok = abs(section.page_height.cm - A4_HEIGHT_CM) < 0.1
    results.append(
        ("page size is A4", width_ok and height_ok,
         f"{section.page_width.cm:.1f}x{section.page_height.cm:.1f}cm")
    )

    normal = document.styles["Normal"]
    results.append(
        ("body font applied", normal.font.name == BODY_FONT,
         f"{normal.font.name} {normal.font.size.pt if normal.font.size else '?'}pt")
    )

    footer_xml = section.footer.paragraphs[0]._p.xml if section.footer.paragraphs else ""
    results.append(("footer page field present", "PAGE" in footer_xml, "w:fldSimple PAGE"))

    bordered = 0
    for table in document.tables:
        if table._tbl.tblPr.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblBorders"
        ) is not None:
            bordered += 1
    results.append(
        ("tables have explicit borders",
         not document.tables or bordered == len(document.tables),
         f"{bordered}/{len(document.tables)}")
    )
    return results


def run_restyle(args: Any, report: Report) -> None:
    path = Path(args.path)
    if not path.is_file():
        report.fail("docx exists", str(path))
        return
    try:
        apply_style(path)
    except Exception as exc:
        report.fail("restyle applied", f"{type(exc).__name__}: {exc}")
        return
    report.check("restyle applied", True, path.name)
    for name, ok, detail in verify_style(path):
        report.check(name, ok, detail)
