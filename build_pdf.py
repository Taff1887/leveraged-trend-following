"""
build_pdf.py
============

Optional: render reports/research_paper.md to reports/research_paper.pdf
(with the charts embedded) and compress it.

This is a *convenience* step — the markdown file is the source of truth. It needs
two extra packages that are not required for the core analysis:

    pip install markdown-pdf pymupdf

Then:

    python build_pdf.py
"""

from __future__ import annotations

import os
from pathlib import Path

from src import config

PAPER_MD = config.REPORTS_DIR / "research_paper.md"
PAPER_PDF = config.REPORTS_DIR / "research_paper.pdf"

CSS = (
    "table{border-collapse:collapse} "
    "td,th{border:1px solid #999;padding:3px;font-size:8pt} "
    "h1{font-size:18pt} h2{font-size:13pt} "
    "body{font-family:sans-serif;font-size:9.5pt} img{width:90%}"
)


def main() -> None:
    try:
        from markdown_pdf import MarkdownPdf, Section
    except ImportError:
        print("markdown-pdf not installed. Run: pip install markdown-pdf pymupdf")
        return

    # The paper references charts as ../charts/...; rewrite to project-root-relative
    # so the PDF builder (rooted at the project root) can find the PNGs.
    text = PAPER_MD.read_text(encoding="utf-8").replace("](../charts/", "](charts/")

    pdf = MarkdownPdf(toc_level=2)
    pdf.add_section(Section(text, root=str(config.PROJECT_ROOT), toc=True),
                    user_css=CSS)
    pdf.meta["title"] = "Trend Following, Leveraged Re-Entry, and Volatility Decay"
    pdf.meta["author"] = "Taffy Jackson"
    pdf.save(str(PAPER_PDF))

    # markdown-pdf embeds images uncompressed; recompress to keep the file small.
    try:
        import fitz  # PyMuPDF
        d = fitz.open(str(PAPER_PDF))
        tmp = config.REPORTS_DIR / "_tmp_compressed.pdf"
        d.save(str(tmp), garbage=4, deflate=True, deflate_images=True,
               deflate_fonts=True, clean=True)
        d.close()
        os.replace(tmp, PAPER_PDF)
    except Exception as exc:  # compression is best-effort
        print(f"  (compression skipped: {exc})")

    size_mb = os.path.getsize(PAPER_PDF) / 1e6
    print(f"Wrote {PAPER_PDF}  ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
