"""File -> clauses. No LLM here. Tables become row records, repeated page furniture is removed,
headings are detected by numbering and sequence, with a page-level fallback."""
import re
import warnings
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from tpg.models import Clause

NUM = r"(?:\d+(?:\.\d+)*|[A-Z]\.\d+(?:\.\d+)*)"
# ponytail: a bare letter (no dotted digit after it) is excluded on purpose - "A" or "I" alone is an
# English word, not a clause id; a letter-only clause id must come through the "Annex [A-Z]" branch below
HEADING_RE = re.compile(rf"^({NUM}|(?:Annex|Appendix)[ \t\xa0]+[A-Z])\.?([ \t\xa0]+)([A-Za-z].*)$")
NUMBER_ONLY_RE = re.compile(r"^((?:\d+|[A-Z])\.\d+(?:\.\d+)*)\.?[ \t\xa0]*$")
# A comma, a semicolon, or a period that ends a word: punctuation that belongs to a sentence and
# not to a clause title. It is what tells a wrapped prose line opening on a cross-reference
# ("4.3.1 of [IEEE754]. Then, ...") from a clause whose title is a lowercase identifier.
SENTENCE_PUNCT_RE = re.compile(r"[,;]|\.(?:\s|$)")
MAX_HEADING_LEN = 90
JOINED = "\x0e"   # marks a heading rebuilt from a number-only line and the following title line
                  # ponytail: must not be Unicode-whitespace (str.strip() would eat it before _heading() sees it)
MIN_PAGES_FOR_REPETITION = 4
EDGE_LINES = 4
# Below this, one clause per page is a plausible document shape rather than an extraction failure,
# so the page fallback stays silent. ponytail: a fixed page count, not a share of the document - a
# share needs a heading count to divide by and in this situation there is none.
MIN_PAGES_TO_REPORT_NO_HEADING = 4

# ponytail: private-use glyph order is font-specific; extend the table if another PDF shows other control chars
LIGATURES = str.maketrans({"\x01": "fi", "\x02": "fl", "\x03": "ff", "\x04": "fl", "\x05": "ffi"})
# C0 controls except tab/lf/cr/ff, plus BOM and zero-width space: some PDF fonts emit a stray
# control byte (e.g. \x08) on alternating pages, which splits strip_repeated's repetition key in
# two and lets page furniture survive inside clause text.
CONTROL = {c: None for c in [*range(0, 9), 11, *range(14, 32), 0xFEFF, 0x200B]}

# Typographic punctuation: the ASCII character the author typed, restyled by a layout tool and then
# reported faithfully by the PDF. It is a typesetting artefact, not what the document says, and it
# defeats every formal notation that spells a construct with one of these characters - CDDL's and
# ABNF's and JSON Schema's and ASN.1's quoted strings, a CDDL or ABNF range written with an en dash,
# anything built on an apostrophe. The set is the quotation-mark and dash runs of the General
# Punctuation block (U+2000-U+206F), taken whole rather than per document: each differs from its
# ASCII counterpart only in how it is drawn - shape, width, or whether a line may break at it - so
# one ASCII character carries the same meaning: the dashes (category Pd) and the quotation marks bar
# the angle ones. What is left alone is what means more than its shape: a prime (a unit), a
# hyphenation point (where a word may break), an angle quotation mark (another language's quoting
# convention, not a restyled ASCII quote), an ellipsis and a bullet (no single ASCII character stands
# for either), and the fixed-width spaces, which `str.split`, `str.strip` and a Unicode `\s` already
# treat as the spaces they are.
TYPOGRAPHIC = ({c: "-" for c in range(0x2010, 0x2016)}      # hyphen through horizontal bar
               | {c: "'" for c in range(0x2018, 0x201C)}    # the four single quotation marks
               | {c: '"' for c in range(0x201C, 0x2020)})   # the four double quotation marks


def table_rows(rows: list[list[str]]) -> str:
    """Row records: 'Header: cell | Header: cell' per data row; an empty first cell inherits the
    previous row's first cell (merged cells); fully empty rows are dropped. A cell the extractor
    could not read at all (None, not just blank) anywhere but the first column means that row's
    column split failed - skip it rather than mis-render the merged text as a clean row or, worse,
    as unprefixed plain text that could be misread as something else entirely."""
    clean = [[" ".join(str(c).split()) if c else "" for c in row] for row in rows]
    if not clean:
        return ""
    if len(clean) < 2:
        return " | ".join(cell for cell in clean[0] if cell)
    header = clean[0]
    out: list[str] = []
    prev_first = ""
    for raw_row, row in zip(rows[1:], clean[1:]):
        if not any(row):
            continue
        if any(c is None for c in raw_row[1:]):
            continue
        if not row[0]:
            row[0] = prev_first
        prev_first = row[0]
        out.append(" | ".join((f"{h}: {c}" if h else c) for h, c in zip(header, row) if h or c))
    return "\n".join(out)


LINK = ("\x11", "\x12")   # brackets the text a hyperlink contributes, so that after the parse a
HEAD = "\x13"             # link can be told from the prose around it, a heading from a paragraph,
BOUND = "\x14"            # and one block element from the next - a newline cannot, since a block
                          # of prose is wrapped over as many source lines as the markup likes
LINKED_RE = re.compile(f"{LINK[0]}([^{LINK[1]}\n]*){LINK[1]}")
# ponytail: all four are C0 controls, so read_pages' CONTROL table erases any that an unclosed
# tag leaves behind - markup cannot smuggle them in either, they never survive into clause text


def _undecorate(text: str) -> str:
    """Drop the text of a hyperlink that carries no letter and no digit. A heading that links to
    itself with a pilcrow, a section sign, a link glyph or an upward arrow is a widespread
    convention across publishers; such a link is decoration for the eye, and no title or sentence
    is made of punctuation alone. A link with a word or a number in it is content and is kept."""
    return LINKED_RE.sub(lambda m: m.group(1) if any(c.isalnum() for c in m.group(1)) else "", text)


def _html_text(text: str) -> str:
    """Resolve the marks, one block element at a time. A block outside a heading whose every
    letter and digit comes from hyperlink text is navigation - a table of contents, an index, a
    menu, a breadcrumb - and not body text: it is written to be clicked, not read. Left in, a
    table of contents reads as a full run of numbered headings with nothing under them, and the
    body headings that follow are then out of sequence, so the whole document lands in one clause.
    A heading element is exempt, because a heading that links to itself is still a heading. The
    test is per block and not per line because a line of a paragraph can hold nothing but a
    bracketed cross-reference while the paragraph around it is prose."""
    out = []
    for block in text.split(BOUND):
        head = HEAD in block
        block = block.replace(HEAD, "")
        if not head and LINKED_RE.search(block) and not any(c.isalnum() for c in LINKED_RE.sub("", block)):
            out.append("\f" * block.count("\f") + "\n")   # the page break belongs to what follows
        else:
            out.append(_undecorate(block))
    return "".join(out)


class _Text(HTMLParser):
    BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "section"}
    HEADING = {"h1", "h2"}
    HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0
        self._rows: list[list[str]] | None = None
        self._cell: list[str] | None = None
        self._head: int | None = None

    def _emit(self, text):
        if self._cell is not None:
            self._cell.append(text)
        elif self._rows is None:
            self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            self._rows = []
        elif tag == "tr" and self._rows is not None:
            self._rows.append([])
        elif tag in ("td", "th") and self._rows is not None:
            self._cell = []
        elif tag == "a":
            self._emit(LINK[0])
        if tag in self.HEADING:
            self.parts.append("\f")
        if tag in self.BLOCK:
            self.parts.append(BOUND + "\n")
        if tag in self.HEADINGS and self._cell is None and self._rows is None:
            self._head = len(self.parts)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        elif tag in ("td", "th") and self._rows is not None and self._cell is not None:
            self._rows[-1].append(" ".join(_undecorate("".join(self._cell)).split()))
            self._cell = None
        elif tag == "table" and self._rows is not None:
            self.parts.append("\n" + table_rows(self._rows) + "\n")
            self._rows = None
        elif tag == "a":
            self._emit(LINK[1])
        if tag in self.HEADINGS and self._head is not None:
            # A heading element is one heading however its markup is laid out across lines.
            title = " ".join("".join(self.parts[self._head:]).replace(BOUND, " ").split())
            del self.parts[self._head:]
            self.parts.append(HEAD + title)
            self._head = None
        if tag in self.BLOCK:
            self.parts.append("\n" + BOUND)

    def handle_data(self, data):
        if self._skip:
            return
        self._emit(data)


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
        pages = _pages(_html_text("".join(parser.parts)))
    else:
        text = p.read_text(errors="replace")
        lines = []
        for line in _markdown_tables(text.splitlines()):
            if line.startswith("# ") or line.startswith("## "):
                lines.append("\f")
            lines.append(re.sub(r"^#+\s*", "", line))
        pages = _pages("\n".join(lines))
    return strip_repeated([pg.replace("\u00ad", "").translate(CONTROL | TYPOGRAPHIC) for pg in pages])


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
    number, title = re.sub(r"^(?:Annex|Appendix)[ \t\xa0]+", "", m.group(1)), m.group(3).strip()
    tab_separated = "\t" in m.group(2)
    if not joined and not tab_separated and not title[:1].isupper():
        # A lowercase title is prose unless the layout says otherwise. Coming from its own line
        # (joined) or separated by a tab, the layout alone settles it. Space separated, two
        # structural conditions have to hold: the number is multi-level, because a bare
        # single-level number opening a line is an ordered-list item or a page footer far more
        # often than a clause; and the title carries no sentence punctuation, because a clause
        # title does not. ponytail: the rest is left to follows() - "6.1 of" and "X.509
        # certificates" pass both conditions and only the sequence rule rejects them, so a
        # document in which no heading has been seen yet stays at the mercy of that rule.
        if "." not in number or SENTENCE_PUNCT_RE.search(title):
            return None
    return number, title


ANNEX_ONLY_RE = re.compile(r"^((?:Annex|Appendix)[ \t\xa0]+[A-Z])\.?[ \t\xa0]*$")
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


def follows(prev: str | None, new: str, prev_empty: bool = False) -> bool:
    """A heading number is plausible if it starts a new top level that succeeds the current top
    level (or is the first lettered annex after a numbered body, or is a bare "1" restarting a
    numbered body right after a cover page or a table of contents - both recognisable purely by
    layout: the previous heading was itself top-level, such as a cover-page date, or the previous
    heading has no body text yet, which is what a run of table-of-contents entries looks like), is
    the first descendant of the current heading at any depth (every component past the shared
    prefix is "1" - the very first entry into levels that have not been seen yet), or is the
    successor (increment 1 or 2, one heading may be missed) at the current level or at any ancestor
    level - even one whose own heading was never seen (an implied parent). A jump that skips a
    level, such as 1 followed by 5.1, is rejected; the parent heading must exist."""
    if prev is None:
        return True
    p, n = _parts(prev), _parts(new)
    if len(n) == 1:
        return (_succ(p[0], n[0]) or (p[0].isdigit() and n[0] == "A")
                or (n[0] == "1" and (len(p) == 1 or prev_empty)))
    if len(n) > len(p) and n[: len(p)] == p and all(c == "1" for c in n[len(p) :]):
        return True
    for k in range(1, len(p) + 1):
        anc = p[:k]
        if (len(n) >= len(anc) and n[:k - 1] == anc[:k - 1]
                and _succ(anc[-1], n[k - 1]) and all(c == "1" for c in n[k:])):
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
            if head and follows(last_number, head[0], prev_empty=(current is None or not current.text)):
                current = Clause(id=head[0], title=head[1], text="")
                clauses.append(current)
                last_number = head[0]
            elif current is not None and line:
                current.text = (current.text + "\n" + line.lstrip(JOINED)).strip()
    if not clauses:
        if len(pages) >= MIN_PAGES_TO_REPORT_NO_HEADING:
            # The page fallback keeps the text, but no clause structure reaches any later stage, so
            # the whole run is built on page-sized clauses. That is a result worth distrusting and
            # the only honest signal ingest can raise on its own: it cannot record a plan gap
            # without changing what it returns. A PDF that shows its headings as filled vector
            # outlines instead of text - what a browser's print-to-PDF does to bold runs - is the
            # case that looks healthy everywhere else, since its body text extracts perfectly
            # while its headings carry no character code for any extractor to read.
            warnings.warn(
                f"no clause heading found in {len(pages)} pages: every clause is a whole page, so "
                "later stages run with no clause structure. If the document does have headings, "
                "they are not extractable text - a PDF that draws them as vector outlines rather "
                "than showing them as text carries no characters for them.",
                stacklevel=2,
            )
        clauses = [Clause(id=f"p{n}", title="", text=page.strip()) for n, page in enumerate(pages, 1)]
    else:
        clauses = _dedupe_ids(clauses)
    for c in clauses:
        c.row_count = sum(" | " in line for line in c.text.splitlines())
    return clauses


def _dedupe_ids(clauses: list[Clause]) -> list[Clause]:
    groups: dict[str, list[Clause]] = {}
    for c in clauses:
        groups.setdefault(c.id, []).append(c)
    keep: set[int] = set()
    suffix: dict[int, str] = {}
    for cid, group in groups.items():
        nonempty = [c for c in group if c.text]
        survivors = sorted(nonempty, key=lambda c: -len(c.text)) if nonempty else [group[0]]
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
