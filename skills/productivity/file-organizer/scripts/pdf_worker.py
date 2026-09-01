#!/usr/bin/env python3
"""PDF text-extraction worker.

Runs in a subprocess so a corrupt PDF that hangs PyMuPDF (fitz) at the C level
can be hard-killed by the parent after a timeout. Reads the PDF path from
argv[1] and prints extracted text to stdout (up to ~8000 chars).
"""
import sys
import re


def _clean(s):
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def main():
    path = sys.argv[1]
    out = []
    try:
        import fitz
        doc = fitz.open(path)
        try:
            for page in doc[:10]:
                t = page.get_text()
                if t:
                    out.append(t)
        finally:
            doc.close()
    except Exception:
        pass

    text = _clean(" ".join(out))
    # cap at 8000 chars
    print(text[:8000])


if __name__ == "__main__":
    main()
