"""File -> clauses. No LLM here. Tables become row records, repeated page furniture is removed,
headings are detected by numbering and sequence, with a page-level fallback."""
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from tpg.models import Clause

NUM = r"(?:\d+(?:\.\d+)*|[A-Z]\.\d+(?:\.\d+)*)"
# ponytail: a bare letter (no dotted digit after it) is excluded on purpose - "A" or "I" alone is an
# English word, not a clause id; a letter-only clause id must come through the "Annex [A-Z]" branch below
HEADING_RE = re.compile(rf"^({NUM}|Annex[ \t\xa0]+[A-Z])\.?[ \t\xa0]+([A-Za-z].*)$")
NUMBER_ONLY_RE = re.compile(r"^((?:\d+|[A-Z])\.\d+(?:\.\d+)*)\.?[ \t\xa0]*$")
MAX_HEADING_LEN = 90
JOINED = "\x0e"   # marks a heading rebuilt from a number-only line and the following title line
                  # ponytail: must not be Unicode-whitespace (str.strip() would eat it before _heading() sees it)
MIN_PAGES_FOR_REPETITION = 4
EDGE_LINES = 4

# ponytail: private-use glyph order is font-specific; extend the table if another PDF shows other control chars
LIGATURES = str.maketrans({"\x01": "fi", "\x02": "fl", "\x03": "ff", "\x04": "fl", "\x05": "ffi"})


def table_rows(rows: list[list[str]]) -> str:
    """Row records: 'Header: cell | Header: cell' per data row; an empty first cell inherits the
    previous row's first cell (merged cells); fully empty rows are dropped."""
    clean = [[" ".join(str(c).split()) if c else "" for c in row] for row in rows]
    if len(clean) < 2:
        return ""
    header = clean[0]
    out: list[str] = []
    prev_first = ""
    for row in clean[1:]:
        if not any(row):
            continue
        if not row[0]:
            row[0] = prev_first
        prev_first = row[0]
        out.append(" | ".join(f"{h}: {c}" for h, c in zip(header, row) if h or c))
    return "\n".join(out)


class _Text(HTMLParser):
    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "section"}
    HEADING = {"h1", "h2"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0
        self._rows: list[list[str]] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._rows.append([])
        elif tag in ("td", "th") and self._rows is not None:
            self._cell = []
        if tag in self.HEADING:
            self.parts.append("\f")
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        elif tag in ("td", "th") and self._rows is not None and self._cell is not None:
            self._rows[-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "table" and self._rows is not None:
            self.parts.append("\n" + table_rows(self._rows) + "\n")
            self._rows = None
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._rows is None:
            self.parts.append(data)


def _pages(text: str) -> list[str]:
    parts = text.split("\f")
    while parts and not parts[0]:
        parts.pop(0)
    return parts


def _pdf_page_text(page) -> str:
    """Text blocks in reading order, with each detected table replaced by its row records at the
    table's position. ponytail: blocks are ordered by their top edge; multi-column layouts would
    need a column-aware sort."""
    import pymupdf
    tables = [t for t in page.find_tables().tables if t.row_count >= 2 and t.col_count >= 2]
    if not tables:
        return page.get_text()
    boxes = [pymupdf.Rect(t.bbox) for t in tables]
    items: list[tuple[float, str]] = []
    for b in page.get_text("blocks"):
        if b[6] != 0:
            continue
        rect = pymupdf.Rect(b[:4])
        if any(rect.intersects(box) for box in boxes):
            continue
        text = b[4]
        if text.lstrip().startswith("Table") and any(0 <= box.y0 - rect.y1 < 30 for box in boxes):
            text = "Table: " + " ".join(text.split())
        items.append((rect.y0, text))
    for t, box in zip(tables, boxes):
        items.append((box.y0, table_rows(t.extract())))
    items.sort(key=lambda it: it[0])
    return "\n".join(txt for _, txt in items)


def _markdown_tables(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                    block.append(cells)
                i += 1
            out.append(table_rows(block))
        else:
            out.append(lines[i])
            i += 1
    return out


def read_pages(path: str) -> list[str]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        import pymupdf
        with pymupdf.open(path) as doc:
            pages = [_pdf_page_text(page).translate(LIGATURES) for page in doc]
    elif suffix == ".docx":
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
                lines.append(table_rows([[cell.text for cell in row.cells] for row in Table(child, doc).rows]))
        pages = _pages("\n".join(lines))
    elif suffix in (".html", ".htm"):
        parser = _Text()
        parser.feed(p.read_text(errors="replace"))
        pages = _pages("".join(parser.parts))
    else:
        text = p.read_text(errors="replace")
        lines = []
        for line in _markdown_tables(text.splitlines()):
            if line.startswith("# ") or line.startswith("## "):
                lines.append("\f")
            lines.append(re.sub(r"^#+\s*", "", line))
        pages = _pages("\n".join(lines))
    return strip_repeated([pg.replace("\u00ad", "") for pg in pages])


def strip_repeated(pages: list[str]) -> list[str]:
    """Drop lines that sit in the first or last EDGE_LINES of a page and whose digit-normalised
    text recurs on at least half of the pages (running headers, footers, page numbers). Pages with
    fewer than MIN_PAGES_FOR_REPETITION distinct contents are left alone: a handful of identical
    pages give no reliable signal for which of their lines are furniture versus body text.
    ponytail: the edge window is capped so it never swallows a whole short page, ceiling is a
    document whose real header/footer block is taller than half its page - widen EDGE_LINES then."""
    if len(pages) < MIN_PAGES_FOR_REPETITION or len(set(pages)) < MIN_PAGES_FOR_REPETITION:
        return pages
    def edges(lines):
        idx = [i for i, l in enumerate(lines) if l.strip()]
        margin = min(EDGE_LINES, max(0, (len(idx) - 2) // 2))
        return set(idx[:margin] + idx[-margin:]) if margin else set()
    def key(line):
        return re.sub(r"\d+", "#", line.strip())
    counts: Counter[str] = Counter()
    for pg in pages:
        lines = pg.splitlines()
        counts.update({key(lines[i]) for i in edges(lines)})
    repeated = {k for k, n in counts.items() if n >= len(pages) / 2}
    out = []
    for pg in pages:
        lines = pg.splitlines()
        edge = edges(lines)
        out.append("\n".join(l for i, l in enumerate(lines) if not (i in edge and key(l) in repeated)))
    return out


def _heading(line: str) -> tuple[str, str] | None:
    joined = line.startswith(JOINED)
    line = line.lstrip(JOINED)
    if len(line) >= MAX_HEADING_LEN:
        return None
    m = HEADING_RE.match(line)
    if not m:
        return None
    number, title = re.sub(r"^Annex[ \t\xa0]+", "", m.group(1)), m.group(2).strip()
    if not joined and not title[:1].isupper():
        return None
    return number, title


ANNEX_ONLY_RE = re.compile(r"^(Annex[ \t\xa0]+[A-Z])\.?[ \t\xa0]*$")
BRACKETED_WORD_RE = re.compile(r"^\([A-Za-z]+\)[ \t\xa0]*$")


def _join_number_only_lines(lines: list[str]) -> list[str]:
    """Some layouts print '7.4.2' alone on a line and the title on the next; rebuild the heading
    and mark it so the title-case rule does not apply. Some layouts print an 'Annex A' marker alone,
    optionally followed by a one-word bracketed qualifier line, with the title after that."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if NUMBER_ONLY_RE.match(stripped) and i + 1 < len(lines) and lines[i + 1].strip():
            out.append(JOINED + stripped.rstrip(".") + " " + lines[i + 1].strip())
            i += 2
            continue
        m = ANNEX_ONLY_RE.match(stripped)
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and BRACKETED_WORD_RE.match(lines[j].strip()):
                j += 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
            if j < len(lines) and lines[j].strip():
                out.append(JOINED + m.group(1) + " " + lines[j].strip())
                i = j + 1
                continue
        out.append(line)
        i += 1
    return out


def _parts(num: str) -> list[str]:
    return num.split(".")


def _succ(a: str, b: str) -> bool:
    if a.isdigit() and b.isdigit():
        return 0 < int(b) - int(a) <= 2
    if len(a) == len(b) == 1 and a.isalpha() and b.isalpha():
        return 0 < ord(b) - ord(a) <= 2
    return False


def follows(prev: str | None, new: str) -> bool:
    """A heading number is plausible if it starts a new top level, is the first descendant of the
    current heading at any depth (every component past the shared prefix is "1" - the very first
    entry into levels that have not been seen yet), or is the successor (increment 1 or 2, one
    heading may be missed) at the current level or at any ancestor level."""
    if prev is None:
        return True
    p, n = _parts(prev), _parts(new)
    if len(n) == 1:
        return True
    if len(n) > len(p) and n[: len(p)] == p and all(c == "1" for c in n[len(p) :]):
        return True
    for k in range(1, len(p) + 1):
        anc = p[:k]
        if len(n) == len(anc) and n[:-1] == anc[:-1] and _succ(anc[-1], n[-1]):
            return True
    return False


def segment(pages: list[str]) -> list[Clause]:
    clauses: list[Clause] = []
    current: Clause | None = None
    last_number: str | None = None
    for page in pages:
        for raw in _join_number_only_lines(page.splitlines()):
            line = raw.replace("\xa0", " ").replace("\u00ad", "").strip()
            head = _heading(line)
            if head and follows(last_number, head[0]):
                current = Clause(id=head[0], title=head[1], text="")
                clauses.append(current)
                last_number = head[0]
            elif current is not None and line:
                current.text = (current.text + "\n" + line.lstrip(JOINED)).strip()
    if clauses:
        return _dedupe_ids(clauses)
    return [Clause(id=f"p{n}", title="", text=page.strip()) for n, page in enumerate(pages, 1)]


def _dedupe_ids(clauses: list[Clause]) -> list[Clause]:
    groups: dict[str, list[Clause]] = {}
    for c in clauses:
        groups.setdefault(c.id, []).append(c)
    keep: set[int] = set()
    suffix: dict[int, str] = {}
    for cid, group in groups.items():
        nonempty = [c for c in group if c.text]
        survivors = nonempty if nonempty else [group[0]]
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
