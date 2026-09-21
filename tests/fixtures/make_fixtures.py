"""Regenerate sample.docx, sample.pdf and sample.html from sample.md. Run once; outputs are committed."""
import re
import textwrap
from pathlib import Path

import fitz  # pymupdf
from docx import Document

HERE = Path(__file__).parent
lines = (HERE / "sample.md").read_text().splitlines()

# DOCX: headings become paragraphs "5.1 Response time", body stays as is.
doc = Document()
for line in lines:
    if line.startswith("#"):
        doc.add_paragraph(line.lstrip("#").strip())
    elif line.strip():
        doc.add_paragraph(line)
doc.save(HERE / "sample.docx")

# PDF: mimic ISO layout: the clause number on its own line, title on the next.
pdf = fitz.open()
page = pdf.new_page()
y = 40
for line in lines:
    if line.startswith("#"):
        m = re.match(r"#+\s+(\d+(?:\.\d+)*)\s+(.*)", line)
        if m and "." in m.group(1):          # ISO layout: dotted number alone, title on the next line
            page.insert_text((40, y), m.group(1)); y += 14
            page.insert_text((40, y), m.group(2)); y += 14
            continue
        page.insert_text((40, y), line.lstrip("#").strip()); y += 14
    elif line.strip():
        for chunk in textwrap.wrap(line, 100):  # keep every line inside the page or get_text() drops it
            page.insert_text((40, y), chunk, fontsize=9); y += 14
pdf.save(HERE / "sample.pdf")

# HTML: headings as <h2>, paragraphs as <p>, plus a script that must be ignored.
html = ["<html><head><title>Sample</title><script>var x = 1;</script></head><body>"]
for line in lines:
    if line.startswith("#"):
        html.append(f"<h2>{line.lstrip('#').strip()}</h2>")
    elif line.strip():
        html.append(f"<p>{line}</p>")
html.append("</body></html>")
(HERE / "sample.html").write_text("\n".join(html))
print("fixtures written")
