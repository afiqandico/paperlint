"""Shared fixtures: a CLI runner, a tiny PDF builder, and a docx builder."""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from paperlint.cli import main


@pytest.fixture
def run(capsys):
    """Invoke the CLI in-process and return (exit_code, stdout)."""

    def _run(*argv: str) -> tuple[int, str]:
        code = main(list(argv))
        return code, capsys.readouterr().out

    return _run


@pytest.fixture
def run_json(run):
    def _run(*argv: str) -> tuple[int, dict]:
        code, out = run(*argv, "--json")
        return code, json.loads(out)

    return _run


def make_pdf(path: Path, text: str = "Hello") -> Path:
    """Write a minimal valid single-page PDF (poppler reads it)."""
    content = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET\n".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(out))
    return path


@pytest.fixture
def pdf(tmp_path):
    return make_pdf(tmp_path / "doc.pdf")


def make_docx(path: Path, text: str = "Body text", media: int = 1) -> Path:
    """Write a minimal DOCX (zip) without needing python-docx."""
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", document)
        for index in range(media):
            zf.writestr(f"word/media/image{index}.png", b"\x89PNG\r\n\x1a\n")
    return path


@pytest.fixture
def docx(tmp_path):
    return make_docx(tmp_path / "build.docx")


def git_init(path: Path, files: dict[str, str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    env = ["-c", "user.email=test@example.com", "-c", "user.name=test"]
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), *env, "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(path), *env, "commit", "-q", "-m", "init"], check=True
    )
    return path
