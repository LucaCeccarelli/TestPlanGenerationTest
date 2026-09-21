"""File -> clauses. No LLM here. Heading detection with a page-level fallback."""
import re
from html.parser import HTMLParser
from pathlib import Path

from tpg.models import Clause

HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?[ \t\xa0]+([A-Z].*)$")
NUMBER_ONLY_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\.?[ \t\xa0]*$")
MAX_HEADING_LEN = 90


class _Text(HTMLParser):
    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br", "table", "section"}
    HEADING = {"h1", "h2"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in self.HEADING:
            self.parts.append("\f")
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _pages(text: str) -> list[str]:
    """Readers mark a top-level heading with a form feed; split into one page per heading
    (a single page if none was found), dropping empty leading chunks from a doc that opens
    with a heading."""
    parts = text.split("\f")
    while parts and not parts[0]:
        parts.pop(0)
    return parts


def read_pages(path: str) -> list[str]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        import fitz
        with fitz.open(path) as doc:
            return [page.get_text() for page in doc]
    if suffix == ".docx":
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        doc = Document(path)
        lines: list[str] = []
        for child in doc.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                para = Paragraph(child, doc)
                if para.style.name.startswith(("Heading 1", "Heading 2")):
                    lines.append("\f")
                lines.append(para.text)
            elif tag == "tbl":
                for row in Table(child, doc).rows:
                    lines.append(" | ".join(cell.text for cell in row.cells))
        return _pages("\n".join(lines))
    if suffix in (".html", ".htm"):
        parser = _Text()
        parser.feed(p.read_text(errors="replace"))
        return _pages("".join(parser.parts))
    # Markdown, .txt, anything else: plain text. Strip leading '#' so headings match.
    text = p.read_text(errors="replace")
    lines = []
    for line in text.splitlines():
        if line.startswith("# ") or line.startswith("## "):
            lines.append("\f")
        lines.append(re.sub(r"^#+\s*", "", line))
    return _pages("\n".join(lines))


def _heading(line: str) -> tuple[str, str] | None:
    if len(line) >= MAX_HEADING_LEN:
        return None
    m = HEADING_RE.match(line)
    if not m:
        return None
    number, title = m.group(1), m.group(2).strip()
    if title.lower().startswith("of "):  # "3 of 77" page footers
        return None
    return number, title


def _join_number_only_lines(lines: list[str]) -> list[str]:
    """ISO PDFs print '7.4.2\\t' on one line and the title on the next."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if NUMBER_ONLY_RE.match(line.strip()) and i + 1 < len(lines) and lines[i + 1].strip():
            out.append(line.strip().rstrip(".") + " " + lines[i + 1].strip())
            i += 2
        else:
            out.append(line)
            i += 1
    return out


def segment(pages: list[str]) -> list[Clause]:
    clauses: list[Clause] = []
    current: Clause | None = None
    for page in pages:
        for raw in _join_number_only_lines(page.splitlines()):
            line = raw.replace("\xa0", " ").strip()
            head = _heading(line)
            if head:
                current = Clause(id=head[0], title=head[1], text="")
                clauses.append(current)
            elif current is not None and line:
                current.text = (current.text + "\n" + line).strip()
    if clauses:
        return _dedupe_ids(clauses)
    return [Clause(id=f"p{n}", title="", text=page.strip()) for n, page in enumerate(pages, 1)]


def _dedupe_ids(clauses: list[Clause]) -> list[Clause]:
    """Table-of-contents stubs and running headers can repeat an id. Group by id in
    appearance order; drop empty-text duplicates when a non-empty one exists; suffix
    remaining non-empty duplicates "<id>#2", "<id>#3", ...; keep only the first if all
    are empty. Document order of survivors is preserved."""
    groups: dict[str, list[Clause]] = {}
    for c in clauses:
        groups.setdefault(c.id, []).append(c)
    keep: set[int] = set()
    suffix: dict[int, str] = {}
    for cid, group in groups.items():
        nonempty = [c for c in group if c.text]
        if nonempty:
            survivors = nonempty
        else:
            survivors = [group[0]]
        keep.update(id(c) for c in survivors)
        for n, c in enumerate(survivors[1:], 2):
            suffix[id(c)] = f"{cid}#{n}"
    out = []
    for c in clauses:
        if id(c) not in keep:
            continue
        if id(c) in suffix:
            c.id = suffix[id(c)]
        out.append(c)
    return out


def ingest(path: str) -> list[Clause]:
    return segment(read_pages(path))
