#!/usr/bin/env python3
"""Text extraction utilities for the file-organizer skill.

Supports: docx, pdf, pptx, xlsx, txt, md, csv, json, xml, html, php,
drawio (xml), otf (skip), images (skip), zip (skip), crswap (skip).

Returns extracted text as a string (truncated to MAX_CHARS for safety).
"""

import json
import os
import re
import zipfile
from pathlib import Path
from typing import Optional

MAX_CHARS = 8000  # generous cap; classification only needs a sample


def extract_text(file_path: str, max_chars: int = MAX_CHARS) -> str:
    """Extract readable text from any supported file type."""
    p = Path(file_path)
    suffix = p.suffix.lower()
    name = p.name.lower()

    # Fast-path: text-ish by extension
    if suffix in (".txt", ".md", ".csv", ".json", ".xml", ".html",
                  ".htm", ".php", ".js", ".py", ".css", ".sql", ".log"):
        return _read_plain_text(p, max_chars)

    # drawio files are XML inside a zip / .drawio is often plain xml
    if suffix == ".drawio" or name.endswith(".drawio"):
        return _extract_drawio(p, max_chars)

    # Office Open XML (docx/pptx/xlsx) are zips with XML inside
    if suffix in (".docx", ".pptx", ".xlsx"):
        return _extract_office_xml(p, suffix, max_chars)

    # PDF
    if suffix == ".pdf":
        return _extract_pdf(p, max_chars)

    # Legacy Office binary (doc/xls/ppt) — try python-magic-free heuristic
    if suffix in (".doc", ".xls", ".ppt"):
        return _extract_legacy_office(p, suffix, max_chars)

    # Everything else: try reading as text, fall back to empty
    return _read_plain_text(p, max_chars)


def _read_plain_text(p: Path, max_chars: int) -> str:
    """Read a file as text with chardet fallback."""
    try:
        raw = p.read_bytes()
    except OSError:
        return ""

    # Very small files: try utf-8 first
    if len(raw) < 500_000:
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                text = raw.decode(enc)
                return _clean_text(text, max_chars)
            except (UnicodeDecodeError, ValueError):
                continue
        # last resort
        return _clean_text(raw.decode("latin-1", errors="replace"), max_chars)

    # Large files: read head + tail
    head = raw[:max_chars * 2]
    for enc in ("utf-8", "utf-8-sig"):
        try:
            return _clean_text(head.decode(enc), max_chars)
        except UnicodeDecodeError:
            continue
    return _clean_text(head.decode("latin-1", errors="replace"), max_chars)


def _clean_text(text: str, max_chars: int) -> str:
    """Normalize whitespace and truncate."""
    if not text:
        return ""
    # collapse runs of whitespace
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars].strip()


def _extract_office_xml(p: Path, suffix: str, max_chars: int) -> str:
    """Extract text from docx/pptx/xlsx via zipfile + element parsing."""
    try:
        with zipfile.ZipFile(p, "r") as zf:
            if suffix == ".docx":
                xml_name = "word/document.xml"
            elif suffix == ".pptx":
                xml_name = "ppt/slides/slide1.xml"
                # try to grab a few slides
                slide_names = sorted([n for n in zf.namelist()
                                      if n.startswith("ppt/slides/slide")
                                      and n.endswith(".xml")])
                parts = []
                for sn in slide_names[:5]:
                    try:
                        parts.append(zf.read(sn).decode("utf-8", errors="replace"))
                    except Exception:
                        pass
                if parts:
                    combined = " ".join(parts)
                    return _clean_text(_strip_xml_tags(combined), max_chars)
                return ""
            elif suffix == ".xlsx":
                # grab shared strings + first sheet
                parts = []
                try:
                    ss = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
                    parts.append(ss)
                except Exception:
                    pass
                sheet_names = [n for n in zf.namelist()
                               if n.startswith("xl/worksheets/sheet")
                               and n.endswith(".xml")][:3]
                for sn in sheet_names:
                    try:
                        parts.append(zf.read(sn).decode("utf-8", errors="replace"))
                    except Exception:
                        pass
                if parts:
                    return _clean_text(_strip_xml_tags(" ".join(parts)), max_chars)
                return ""
            else:
                return ""

            try:
                xml_bytes = zf.read(xml_name)
                xml_text = xml_bytes.decode("utf-8", errors="replace")
                return _clean_text(_strip_xml_tags(xml_text), max_chars)
            except KeyError:
                return ""
    except (zipfile.BadZipFile, OSError):
        return ""


def _silence_stderr():
    """Context manager that redirects fd 2 (stderr) to /dev/null, so C-level
    PDF library errors (MuPDF 'object out of range', PyPDF2 warnings) don't
    flood the console during batch extraction."""
    import contextlib
    @contextlib.contextmanager
    def _cm():
        devnull = os.open(os.devnull, os.O_WRONLY)
        old = os.dup(2)
        os.dup2(devnull, 2)
        try:
            yield
        finally:
            os.dup2(old, 2)
            os.close(old)
            os.close(devnull)
    return _cm()


def _extract_pdf(p: Path, max_chars: int) -> str:
    """Extract text from PDF via PyPDF2; fall back to pymupdf.
    All stderr from the C libraries is silenced (corrupt-PDF spam)."""
    try:
        import PyPDF2
        with _silence_stderr():
            with open(p, "rb") as fh:
                reader = PyPDF2.PdfReader(fh)
                parts = []
                for page in reader.pages[:10]:
                    try:
                        t = page.extract_text()
                        if t:
                            parts.append(t)
                    except Exception:
                        pass
            if parts:
                return _clean_text(" ".join(parts), max_chars)
    except Exception:
        pass

    # pymupdf fallback
    try:
        import fitz
        with _silence_stderr():
            doc = fitz.open(str(p))
            parts = []
            for page in doc[:10]:
                t = page.get_text()
                if t:
                    parts.append(t)
            if parts:
                return _clean_text(" ".join(parts), max_chars)
    except Exception:
        pass

    return ""


def _extract_legacy_office(p: Path, suffix: str, max_chars: int) -> str:
    """Best-effort extraction of .doc/.xls/.ppt binary files.

    These are OLE2 compound documents. We do a cheap scan: look for
    readable ASCII/UTF-16LE strings inside the file. Not perfect, but
    enough to classify topic/client from embedded text fragments.
    """
    try:
        raw = p.read_bytes()
    except OSError:
        return ""

    # Try to decode as utf-16-le (common for legacy Office)
    for enc in ("utf-16-le", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc, errors="ignore")
            # filter: keep runs of printable chars at least 10 long
            runs = re.findall(r"[^\x00-\x08\x0B\x0C\x0E-\x1F]{10,}", text)
            if runs:
                cleaned = " ".join(runs)
                return _clean_text(cleaned, max_chars)
        except Exception:
            continue
    return ""


def _extract_drawio(p: Path, max_chars: int) -> str:
    """drawio files are XML; extract text from labels."""
    try:
        raw = p.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        return _clean_text(_strip_xml_tags(text), max_chars)
    except Exception:
        return ""


def _strip_xml_tags(xml: str) -> str:
    """Strip XML tags, leave text content. Handle common namespaces."""
    # Remove <?xml ...?>
    text = re.sub(r"<\?.*?\?>", " ", xml)
    # Remove <[^>]+> tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Unescape basic entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&apos;", "'")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: text_extract.py <file>")
        sys.exit(1)
    print(extract_text(sys.argv[1]))
