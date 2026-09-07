#!/usr/bin/env python
"""Recover text from archive PDFs whose type was flattened to outlines.

    python tools/ocr_archive.py archive/2026-09-13-trinity-15 --out build/ocr

Trinity 15's PDFs contain no fonts and no text operators at all: 2.8 MB
of vector path drawing per file. The words were converted to shapes on
export, so no parser can read them back and OCR is the only route.

WHAT COMES OUT OF THIS IS NOT SOURCE OF TRUTH.

OCR guesses. It confuses quotation marks, drops diacritics, and breaks
lines in the wrong places. Output lands in build/ (ignored by git), never
in content/, and is only useful for comparison: run it beside the live
app's text for the same Sunday and the diff shows where the printed
handouts and the app disagree. Promoting any of it into content/ requires
a human reading it against the original.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DPI = 220  # enough for 8pt credits without making pages huge


def ocr_pdf(path: Path, engine, dpi: int = DPI) -> list[str]:
    import pymupdf

    doc = pymupdf.open(str(path))
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        png = pix.tobytes("png")
        import numpy as np
        from PIL import Image
        import io

        img = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
        result, _ = engine(img)
        if not result:
            pages.append("")
            continue
        # rapidocr returns [box, text, confidence]; keep reading order.
        lines = [r[1] for r in result]
        pages.append("\n".join(lines))
    doc.close()
    return pages


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="directory of PDFs, or a single PDF")
    ap.add_argument("--out", default="build/ocr")
    ap.add_argument("--dpi", type=int, default=DPI)
    args = ap.parse_args()

    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()

    src = Path(args.src)
    pdfs = sorted(src.glob("*.pdf")) if src.is_dir() else [src]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    index = {}
    for pdf in pdfs:
        print(f"OCR  {pdf.name} ...", flush=True)
        try:
            pages = ocr_pdf(pdf, engine, args.dpi)
        except Exception as e:
            print(f"     failed: {type(e).__name__}: {e}")
            continue
        text = "\n\n".join(pages)
        dest = out / (pdf.stem + ".txt")
        dest.write_text(text, encoding="utf-8")
        index[pdf.name] = {"pages": len(pages), "chars": len(text),
                           "text_file": dest.as_posix()}
        print(f"     {len(pages)} page(s), {len(text)} chars -> {dest}")

    (out / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nDone. {len(index)} file(s). This output is OCR, not source of truth.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
