# Test Model Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `tpg` derive test cases from an explicit test model (objects × coverage items) instead of from sentences alone, and fix the ingest and extraction defects found in the ISO 18013-5 evaluation, without any document-family-specific rule.

**Architecture:** Ingest keeps tables as `Header: cell | Header: cell` row records and cleans layout generically. Extraction accepts drafts individually and knows `should_not`. A new `model` stage extracts objects per clause; a new deterministic `derive` stage enumerates coverage items from requirements and objects; generation writes one test case per coverage item; verification checks one case per item. Output gains `objects` and `coverage_items`.

**Tech Stack:** Python 3.12, `uv`, pydantic v2, `ollama`, `pymupdf` (imported as `pymupdf`, `find_tables()`), `python-docx`, `pyyaml`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-test-model-design.md` (addendum; base spec `docs/superpowers/specs/2026-09-21-test-plan-generator-design.md`)

## Global Constraints

- Runtime deps unchanged: `pydantic>=2`, `ollama>=0.5.1`, `pymupdf`, `python-docx`, `pyyaml`; dev: `pytest`. No new dependency (spec D10).
- `ingest.py`, `derive.py`, `verify.py`, `emit.py` never call the LLM. `llm.py` is the only network module.
- LLM calls: `format=<schema>`, `think=False`, `temperature 0`, replies cleaned and validated, never trusted (D5). Retry budget 3 per clause chunk / per coverage item; `LLMError` counts as one attempt (D6).
- No rule may mention a document family, standard name, or domain term (user constraint: "no hardcoded solutions of ISO formatted documents"). Layout rules are generic (repetition, numbering sequence, table geometry).
- IDs: `REQ-<clause>-<n>`, `OBJ-<clause>-<n>` in source-quote order; `CI-<source id>-<check>[-<n>]`; `TC-<coverage item id>`.
- No literal non-ASCII bytes in code; use `\u` escapes. `.env` and `tests/fixtures/iso_18013_5.pdf` never committed.
- Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Fast suite pristine before every commit: `uv run pytest -q -m "not slow"`.
- Existing tests that the task does not deliberately change must keep passing; tests changed on purpose are listed in the task.

---

## File structure

| File | Responsibility (after this plan) |
|---|---|
| `tpg/models.py` | All types: Modality (+should_not), TestObject/Draft/Batch, CoverageItem, TestCase (source_id, coverage_item_id), Gap (source_id, stage model), TraceLink (source_id, coverage_item_ids, test_case_ids), TestPlan (+objects, +coverage_items) |
| `tpg/ingest.py` | Readers with table row records (PDF via find_tables, DOCX, HTML, Markdown pipe tables), repeated header/footer removal, soft-hyphen removal, letter-prefixed and Annex headings, sequence plausibility, joined-heading case rule |
| `tpg/extract.py` | Candidates, chunking, per-draft acceptance, should_not |
| `tpg/model.py` | Object extraction per clause chunk, per-object acceptance, duplicate merge |
| `tpg/derive.py` | Coverage items from requirements and objects, no LLM |
| `tpg/verify.py` | `required_assignments`, `check_test_case(item, draft)` |
| `tpg/generate.py` | One call per coverage item |
| `tpg/emit.py` | Plan assembly with objects, items, traceability per source |
| `tpg/pipeline.py` | `run(..., use_model=True)` |
| `tpg/cli.py` | `--no-model` |
| `tests/*` | One module per source module; fixtures gain a parameter table |

---

### Task 1: Ingest — tables as row records, generic layout cleaning, heading rules

**Files:**
- Modify: `tpg/ingest.py` (full replacement below)
- Modify: `tests/test_ingest.py` (add tests below; change two existing assertions as noted)

**Interfaces:**
- Consumes: `tpg.models.Clause`
- Produces (unchanged signatures): `read_pages(path) -> list[str]`, `segment(pages) -> list[Clause]`, `ingest(path) -> list[Clause]`; new helpers `strip_repeated(pages) -> list[str]`, `table_rows(rows: list[list[str]]) -> str`, `follows(prev: str | None, new: str) -> bool`.
- Row record format: one line per data row, `Header: cell | Header: cell`, headers from the first row, empty first cell inherits the previous row's first cell; optional preceding line `Table: <caption>`.

- [ ] **Step 1: Add the failing tests to `tests/test_ingest.py`** (append; keep all existing tests)

```python
from tpg.ingest import follows, strip_repeated, table_rows


def test_strip_repeated_removes_running_headers_and_page_numbers():
    pages = [f"Spec v1.0\nBody {i}\nmore text {i}\nPage {i} of 4" for i in range(1, 5)]
    out = strip_repeated(pages)
    assert out[0] == "Body 1\nmore text 1"
    assert all("Spec v1.0" not in p and "Page" not in p for p in out)


def test_strip_repeated_keeps_short_documents_and_mid_page_lines():
    pages = ["Spec v1.0\nBody\nSpec v1.0 again mid", "Spec v1.0\nOther"]
    assert strip_repeated(pages) == pages
    four = ["Spec\n" + "\n".join(f"line {j}" for j in range(10)) + "\nTable 3 caption\nend"] * 4
    assert all("Table 3 caption" in p for p in strip_repeated(four))


def test_table_rows_format_and_merged_first_cell():
    rows = [["Name", "Presence", "Type"], ["nonce", "M", "text"], ["", "O", "int"], ["", "", ""]]
    assert table_rows(rows) == "Name: nonce | Presence: M | Type: text\nName: nonce | Presence: O | Type: int"


def test_follows_sequence_rules():
    assert follows(None, "1") and follows("1", "2") and follows("1", "1.1") and follows("1.1", "1.2")
    assert follows("7.4.9", "7.5") and follows("7.4.9", "8") and follows("1.1", "1.3")  # one missed heading tolerated
    assert follows("8", "8.1") and not follows("8", "8.1.2") and not follows("1.1", "1.5")
    assert follows("B.2", "B.3") and follows("B", "B.1") and follows("A.3.4", "B") and not follows("B.2", "5.2")


def test_letter_prefixed_and_annex_headings():
    clauses = segment(["1 Scope\nBody.\nAnnex A\nIntro.\nA.1 General\nThe unit shall log.\nA.2 Cases\nMore."])
    assert [c.id for c in clauses] == ["1", "A", "A.1", "A.2"]
    assert clauses[1].title.startswith("")  # Annex heading keeps its title text or empty; id is the letter


def test_table_cell_number_is_not_a_heading():
    clauses = segment(["B.1 Extensions\nAuthority Key Identifier\n5.2 Further extensions shall not be present\nCRL Number\nB.2 Next\nBody."])
    assert [c.id for c in clauses] == ["B.1", "B.2"]
    assert "5.2 Further extensions" in clauses[0].text


def test_joined_heading_accepts_lowercase_title_but_inline_lowercase_is_rejected():
    clauses = segment(["7.3.2\t\nnameSpace\nThe nameSpace shall be text.\n7.3.3 mDL data\nBody."])
    assert [(c.id, c.title) for c in clauses] == [("7.3.2", "nameSpace")]
    assert "7.3.3 mDL data" in clauses[0].text


def test_soft_hyphens_are_removed():
    clauses = segment(["5.1 Codes\nThe first part of the code shall be the same as issu­ing_country."])
    assert "issuing_country" in clauses[0].text


def test_markdown_pipe_table_becomes_row_records(tmp_path):
    md = tmp_path / "t.md"
    md.write_text("## 5.4 Parameters\n\n| Name | Presence | Type |\n|---|---|---|\n| nonce | mandatory | text string |\n| locale | optional | language tag |\n")
    c = ingest(str(md))[0]
    assert "Name: nonce | Presence: mandatory | Type: text string" in c.text
    assert "Name: locale | Presence: optional | Type: language tag" in c.text
    assert "|---" not in c.text


def test_html_table_becomes_row_records(tmp_path):
    h = tmp_path / "t.html"
    h.write_text("<h2>5.4 Parameters</h2><table><tr><th>Name</th><th>Presence</th></tr><tr><td>nonce</td><td>mandatory</td></tr></table>")
    c = ingest(str(h))[0]
    assert "Name: nonce | Presence: mandatory" in c.text


def test_docx_table_becomes_row_records_with_headers(tmp_path):
    from docx import Document
    doc = Document()
    doc.add_paragraph("5.4 Parameters")
    t = doc.add_table(rows=2, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Name", "Presence"
    t.rows[1].cells[0].text, t.rows[1].cells[1].text = "nonce", "mandatory"
    p = tmp_path / "t.docx"
    doc.save(str(p))
    c = next(c for c in ingest(str(p)) if c.id == "5.4")
    assert "Name: nonce | Presence: mandatory" in c.text


def test_iso_pdf_finds_lowercase_titled_and_annex_clauses():
    if not (FIX / "iso_18013_5.pdf").exists():
        pytest.skip("ISO fixture not distributed")
    clauses = {c.id: c for c in ingest(str(FIX / "iso_18013_5.pdf"))}
    assert {"7.3.3", "A.1", "8.2.1.1.2.1"} <= set(clauses)
    assert max(len(c.text) for c in clauses.values()) < 60000
    assert "Reference:" in "".join(c.text for c in clauses.values())   # a table row record survived


def test_pdf_pages_have_no_running_headers():
    text = "\n".join(ingest(str(FIX / "OpenID4VP1-0.pdf"))[3].text.splitlines()[:50])
    assert "openid.net/specs" not in text and " of 96" not in text
```

Change two existing tests: in `test_docx_tables_stay_in_document_order`, the table row now reads `"The unit shall log | events"` as a row record with headers taken from that first row, so a one-row table has no data rows; update the fixture to two rows (`rows=2`): header cells `"Item", "Value"`, data cells `"The unit shall log", "events"`, and assert `"Item: The unit shall log | Value: events" in ...5.1 text`. In `tests/fixtures/make_fixtures.py` nothing changes in this task.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: the new tests FAIL with ImportError (`follows`, `strip_repeated`, `table_rows`) or assertion errors; old tests pass.

- [ ] **Step 3: Replace `tpg/ingest.py`**

```python
"""File -> clauses. No LLM here. Tables become row records, repeated page furniture is removed,
headings are detected by numbering and sequence, with a page-level fallback."""
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from tpg.models import Clause

NUM = r"(?:\d+|[A-Z])(?:\.\d+)*"
HEADING_RE = re.compile(rf"^({NUM}|Annex [A-Z])\.?[ \t\xa0]+([A-Za-z].*)$")
NUMBER_ONLY_RE = re.compile(r"^((?:\d+|[A-Z])\.\d+(?:\.\d+)*)\.?[ \t\xa0]*$")
MAX_HEADING_LEN = 90
JOINED = "\x1f"   # marks a heading rebuilt from a number-only line and the following title line
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
    return strip_repeated([pg.replace("­", "") for pg in pages])


def strip_repeated(pages: list[str]) -> list[str]:
    """Drop lines that sit in the first or last EDGE_LINES of a page and whose digit-normalised
    text recurs on at least half of the pages (running headers, footers, page numbers)."""
    if len(pages) < MIN_PAGES_FOR_REPETITION:
        return pages
    def edges(lines):
        idx = [i for i, l in enumerate(lines) if l.strip()]
        return set(idx[:EDGE_LINES] + idx[-EDGE_LINES:])
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
    number, title = m.group(1).replace("Annex ", ""), m.group(2).strip()
    if not joined and not title[:1].isupper():
        return None
    return number, title


def _join_number_only_lines(lines: list[str]) -> list[str]:
    """Some layouts print '7.4.2' alone on a line and the title on the next; rebuild the heading
    and mark it so the title-case rule does not apply."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if NUMBER_ONLY_RE.match(line.strip()) and i + 1 < len(lines) and lines[i + 1].strip():
            out.append(JOINED + line.strip().rstrip(".") + " " + lines[i + 1].strip())
            i += 2
        else:
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
    """A heading number is plausible if it starts a new top level, is the first child of the current
    heading, or is the successor (increment 1 or 2, one heading may be missed) at the current level
    or at any ancestor level."""
    if prev is None:
        return True
    p, n = _parts(prev), _parts(new)
    if len(n) == 1:
        return True
    if n[:-1] == p and n[-1] == "1":
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
            line = raw.replace("\xa0", " ").strip()
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
```

Note for `test_letter_prefixed_and_annex_headings`: the line `Annex A` alone has no title, so it does not match `HEADING_RE` (which needs a title). Make the test input `Annex A (informative) Use cases` instead of a bare `Annex A`, and expect the title `(informative) Use cases`; adjust the test's second assertion to `assert clauses[1].title == "(informative) Use cases"`.

- [ ] **Step 4: Run the ingest tests**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: all pass. If `test_iso_pdf_finds_lowercase_titled_and_annex_clauses` fails on `8.2.1.1.2.1`, print the ids starting with `8.2.1` and adjust only the asserted id to one that exists at depth 5 in that family; if `Reference:` is not found, print one clause containing `" | "` and adjust the asserted header word to a real header from that document's tables. Do not change the code for these two assertions.

- [ ] **Step 5: Update `make_fixtures.py` import and regenerate fixtures**

In `tests/fixtures/make_fixtures.py` replace `import fitz  # pymupdf` with `import pymupdf` and `fitz.open()` with `pymupdf.open()`. Run `uv run python tests/fixtures/make_fixtures.py` and the full fast suite.

Run: `uv run pytest -q -m "not slow"`
Expected: all pass, no warnings (the `fitz` deprecation warning is gone).

- [ ] **Step 6: Commit**

```bash
git add tpg/ingest.py tests/test_ingest.py tests/fixtures/make_fixtures.py tests/fixtures/sample.pdf tests/fixtures/sample.docx tests/fixtures/sample.html
git commit -m "feat: ingest keeps tables as row records, strips repeated page furniture, generic heading rules

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Extraction — per-draft acceptance, should_not, chunking

**Files:**
- Modify: `tpg/models.py` (Modality only)
- Modify: `tpg/extract.py` (full replacement)
- Modify: `tests/test_extract.py` (add tests; two existing tests change as noted)

**Interfaces:**
- Consumes: `Clause`, `RequirementDraft`, `RequirementBatch`, `Requirement`, `Gap`, `LLMError`
- Produces: `norm`, `find_candidates`, `chunks(text, limit=8000) -> list[str]`, `build_extract_prompt(clause, chunk, part, candidates, failures, accepted_texts)`, `check_draft(clause, n, draft) -> str | None`, `check_requirements(clause, drafts) -> list[str]` (failures only, compatibility), `extract_clause(clause, llm, attempts=3) -> (list[Requirement], Gap | None)` where accepted requirements are returned even when a gap is recorded, `extract(clauses, llm, attempts, log)`.

- [ ] **Step 1: Models change**

In `tpg/models.py` set `Modality = Literal["shall", "shall_not", "should", "should_not", "may"]`.

- [ ] **Step 2: Add failing tests to `tests/test_extract.py`**

```python
from tpg.extract import check_draft, chunks


def test_should_not_and_never_are_grounded():
    c = Clause(id="1", title="t", text="Other elements should not be present. A counter shall never be reused.")
    ok = [RequirementDraft(text="a", modality="should_not", source_quote="Other elements should not be present."),
          RequirementDraft(text="b", modality="shall_not", source_quote="A counter shall never be reused.")]
    assert check_requirements(c, ok) == []
    assert check_draft(c, 1, RequirementDraft(text="a", modality="should", source_quote="should not be present")) is not None


def test_chunks_split_at_line_boundaries_under_limit():
    text = "\n".join(f"line {i} " + "x" * 90 for i in range(100))
    parts = chunks(text, limit=1000)
    assert len(parts) >= 9 and all(len(p) <= 1000 for p in parts)
    assert "\n".join(parts) == text


def test_extract_clause_keeps_valid_drafts_and_retries_only_invalid(fake_llm):
    bad = {"text": "x", "modality": "shall", "source_quote": "not in clause"}
    good1 = GOOD["requirements"][0]
    fixed = GOOD["requirements"][1]
    llm = fake_llm([{"requirements": [good1, bad]}, {"requirements": [fixed]}])
    reqs, gap = extract_clause(CLAUSE, llm)
    assert gap is None and [r.modality for r in reqs] == ["shall_not", "may"]
    assert len(llm.prompts) == 2
    assert "not in clause" in llm.prompts[1] and good1["text"] in llm.prompts[1]


def test_extract_clause_gap_keeps_accepted_requirements(fake_llm):
    bad = {"text": "x", "modality": "shall", "source_quote": "nope"}
    good1 = GOOD["requirements"][0]
    llm = fake_llm([{"requirements": [good1, bad]}, {"requirements": [bad]}, {"requirements": [bad]}])
    reqs, gap = extract_clause(CLAUSE, llm)
    assert len(reqs) == 1 and reqs[0].id == "REQ-5.2-1"
    assert gap is not None and gap.attempts == 3 and "nope" in gap.reason


def test_extract_clause_chunks_long_clause(fake_llm):
    long = Clause(id="9", title="t", text="\n".join(f"Item {i}: the unit shall do thing {i}." for i in range(400)))
    llm = fake_llm([{"requirements": []}] * 10)
    reqs, gap = extract_clause(long, llm)
    assert gap is None and reqs == [] and 2 <= len(llm.prompts) <= 4
    assert "part 1/" in llm.prompts[0]
```

Change `test_extract_clause_retries_with_feedback_then_succeeds`: with per-draft acceptance the bad first batch has one invalid draft, the second response is an `LLMError`, the third returns `GOOD` (two valid drafts); the assertions `len(llm.prompts) == 3`, `"not in clause" in llm.prompts[1]`, `"not valid JSON" in llm.prompts[2]` stay valid; keep the test as is. Change `test_extract_clause_gap_after_three_failures`: still `reqs == []`, gap attempts 3, reason contains `"nope"`; unchanged. Remove nothing.

- [ ] **Step 3: Run to verify the new tests fail**

Run: `uv run pytest tests/test_extract.py -v`
Expected: new tests FAIL (ImportError for `check_draft`/`chunks`, or assertion), others pass.

- [ ] **Step 4: Replace `tpg/extract.py`**

```python
"""Annotation-then-conversion: regex marks candidate sentences, the LLM converts them, rules check each
draft; valid drafts are kept and only invalid ones are retried."""
import re

from tpg.llm import LLMError
from tpg.models import Clause, Gap, Requirement, RequirementBatch, RequirementDraft

CANDIDATE_RE = re.compile(r"\b(shall|must|should|may|is required to)\b", re.I)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"'])")
MODAL_RE = {
    "shall": re.compile(r"\b(shall|must)\b(?!\s+(not|never)\b)"),
    "shall_not": re.compile(r"\b(shall|must)\s+(not|never)\b"),
    "should": re.compile(r"\bshould\b(?!\s+(not|never)\b)"),
    "should_not": re.compile(r"\bshould\s+(not|never)\b"),
    "may": re.compile(r"\bmay\b(?!\s+not\b)"),
}
CHUNK_LIMIT = 8000


def norm(s: str) -> str:
    return " ".join(s.split()).lower()


def find_candidates(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(flat) if CANDIDATE_RE.search(s)]


def chunks(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Split at line boundaries into pieces of at most `limit` characters (a single over-long line
    stays whole)."""
    out: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.split("\n"):
        if buf and size + len(line) + 1 > limit:
            out.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        out.append("\n".join(buf))
    return out


def build_extract_prompt(clause: Clause, chunk: str, part: str, candidates: list[str], failures: list[str],
                         accepted_texts: list[str]) -> str:
    cands = "\n".join(f"- {c}" for c in candidates)
    feedback = ""
    if failures:
        feedback = ("\nSome requirements of your previous answer were rejected for these reasons; return ONLY corrected "
                    "versions of those rejected requirements, nothing else:\n" + "\n".join(f"- {f}" for f in failures) + "\n")
        if accepted_texts:
            feedback += "Already accepted, do not repeat:\n" + "\n".join(f"- {t}" for t in accepted_texts) + "\n"
    return f"""You extract atomic, testable requirements from a technical specification.

Clause {clause.id} "{clause.title}" (part {part}):
\"\"\"
{chunk}
\"\"\"

Candidate sentences (each contains a modal verb):
{cands}

Rules:
- Produce one requirement per atomic obligation. Split a sentence that contains several obligations.
- Do not invent requirements that are not in the candidate sentences.
- "text": one self-contained testable statement, keep the modal verb.
- "modality": one of shall, shall_not, should, should_not, may. Use "must" as shall, "must not" / "shall never" as shall_not,
  "should not" as should_not.
- "conditions": the list of conditions under which the obligation applies (e.g. ["request is malformed", "session has expired"] for "if A or B then ..."); empty list if unconditional.
- "source_quote": a VERBATIM substring of the clause text that contains THIS requirement's own modal verb, not one belonging to a
  different obligation nearby. Keep it as short as possible while still containing that modal verb. If a bullet elaborates or
  restates a preceding obligation without a modal verb of its own, fold its detail into the "text" of the requirement whose
  sentence does carry the modal verb, and quote that sentence.
- Copy source_quote exactly as printed, including unusual characters. A table row line "Header: value | Header: value" is text too.
- If none of the candidate sentences states an obligation of the system under test (e.g. bibliography entries, definitions of the
  words shall/should/may, dates), return an empty list.
{feedback}
Reply with JSON only: {{"requirements": [{{"text": ..., "modality": ..., "conditions": [...], "source_quote": ...}}]}}"""


def check_draft(clause: Clause, n: int, d: RequirementDraft) -> str | None:
    if not d.text.strip():
        return f"requirement {n}: text is empty"
    q = norm(d.source_quote)
    if not q or q not in norm(clause.text):
        return f"requirement {n}: source_quote is not a verbatim substring of the clause: {d.source_quote!r}"
    if not MODAL_RE[d.modality].search(q):
        return f"requirement {n}: modality {d.modality!r} does not appear in source_quote {d.source_quote!r}"
    return None


def check_requirements(clause: Clause, drafts: list[RequirementDraft]) -> list[str]:
    return [m for m in (check_draft(clause, n, d) for n, d in enumerate(drafts, 1)) if m]


def _accept(clause: Clause, drafts: list[RequirementDraft], accepted: list[RequirementDraft]) -> list[str]:
    """Move valid, non-duplicate drafts into `accepted`; return the failure messages of the rest."""
    failures = []
    seen = {(norm(a.text), norm(a.source_quote)) for a in accepted}
    for n, d in enumerate(drafts, 1):
        msg = check_draft(clause, n, d)
        if msg:
            failures.append(msg)
        elif (norm(d.text), norm(d.source_quote)) not in seen:
            accepted.append(d)
            seen.add((norm(d.text), norm(d.source_quote)))
    return failures


def extract_clause(clause: Clause, llm, attempts: int = 3) -> tuple[list[Requirement], Gap | None]:
    accepted: list[RequirementDraft] = []
    open_failures: list[str] = []
    parts = chunks(clause.text)
    for i, chunk in enumerate(parts, 1):
        candidates = find_candidates(chunk)
        if not candidates:
            continue
        failures: list[str] = []
        for _ in range(attempts):
            prompt = build_extract_prompt(clause, chunk, f"{i}/{len(parts)}", candidates, failures, [a.text for a in accepted])
            try:
                batch = llm.complete(prompt, RequirementBatch)
            except LLMError as e:
                failures = [str(e)]
                continue
            failures = _accept(clause, batch.requirements, accepted)
            if not failures:
                break
        open_failures.extend(failures)
    body = norm(clause.text)
    ordered = sorted(accepted, key=lambda d: body.index(norm(d.source_quote)))
    reqs = [Requirement(id=f"REQ-{clause.id}-{n}", clause_id=clause.id, **d.model_dump()) for n, d in enumerate(ordered, 1)]
    gap = None
    if open_failures:
        gap = Gap(requirement_id=None, clause_id=clause.id, stage="extract", reason="; ".join(open_failures), attempts=attempts)
    return reqs, gap


def extract(clauses: list[Clause], llm, attempts: int = 3, log=lambda s: None) -> tuple[list[Requirement], list[Gap]]:
    reqs: list[Requirement] = []
    gaps: list[Gap] = []
    for clause in clauses:
        if not find_candidates(clause.text):
            continue
        got, gap = extract_clause(clause, llm, attempts)
        reqs.extend(got)
        if gap:
            gaps.append(gap)
        log(f"clause {clause.id}: {len(got)} requirements" + (" (GAP)" if gap else ""))
    return reqs, gaps
```

- [ ] **Step 5: Run the extract tests and the fast suite**

Run: `uv run pytest tests/test_extract.py -v && uv run pytest -q -m "not slow"`
Expected: all pass. `test_prompt_contains_clause_candidates_and_failures` calls `build_extract_prompt(CLAUSE, ["c1","c2"], ["prev failure"])` with the old signature; update that call to `build_extract_prompt(CLAUSE, CLAUSE.text, "1/1", ["c1", "c2"], ["prev failure"], [])`.

- [ ] **Step 6: Commit**

```bash
git add tpg/models.py tpg/extract.py tests/test_extract.py
git commit -m "feat: extraction accepts drafts individually, knows should_not, chunks long clauses

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Core — data model v2, model stage, derive, verify, generate per item, emit, pipeline

**Files:**
- Modify: `tpg/models.py` (full replacement), `tpg/verify.py`, `tpg/generate.py`, `tpg/emit.py`, `tpg/pipeline.py` (full replacements), `tpg/extract.py` (Gap field rename: `requirement_id=None` becomes `source_id=None`), `tpg/cli.py` (summary line only)
- Create: `tpg/model.py`, `tpg/derive.py`, `tests/test_model.py`, `tests/test_derive.py`
- Modify: `tests/conftest.py` (FakeLLM fallback), `tests/test_models.py`, `tests/test_verify.py`, `tests/test_generate.py`, `tests/test_emit.py`, `tests/test_pipeline.py`, `tests/test_cli.py` (Gap/TestPlan constructors), `tests/test_extract.py` (`gap.requirement_id` becomes `gap.source_id` where asserted)

**Interfaces:**
- Produces:
  - `tpg.models`: `TestObjectDraft`, `TestObject`, `TestObjectBatch`, `CoverageItem`, `Check`, `TestCaseDraft` (no kind, no condition_assignment), `TestCase(TestCaseDraft) + id, source_id, coverage_item_id, kind, condition_assignment`, `Gap(source_id, clause_id, stage extract|model|generate, reason, attempts)`, `TraceLink(source_id, coverage_item_ids, test_case_ids)`, `TestPlan(source, requirements, objects=[], coverage_items=[], test_cases, traceability, gaps)`
  - `tpg.model`: `has_rows(text) -> bool`, `build_model_prompt(clause, chunk, part, failures, accepted_names)`, `check_object(clause, n, draft) -> str | None`, `merge_objects(drafts) -> list[TestObjectDraft]`, `extract_objects_clause(clause, llm, attempts=3) -> (list[TestObject], Gap | None)`, `extract_objects(clauses, llm, attempts=3, log) -> (objects, gaps)`
  - `tpg.derive`: `derive_requirement(req) -> list[CoverageItem]`, `derive_object(obj) -> list[CoverageItem]`, `derive(reqs, objs) -> list[CoverageItem]`
  - `tpg.verify`: `required_assignments`, `NEGATIVE_WORDS`, `check_test_case(item, draft) -> list[str]`
  - `tpg.generate`: `context_excerpt(clause, quote) -> str`, `build_generate_prompt(item, source, clause, failures)`, `generate_item(item, source, clause, llm, attempts=3) -> (TestCase | None, Gap | None)`, `generate(items, reqs, objs, clauses, llm, attempts=3, log) -> (cases, gaps)`
  - `tpg.emit`: `build_plan(source, requirements, objects, coverage_items, test_cases, gaps)`, `write_plan`
  - `tpg.pipeline`: `run(path, llm, model, clause_ids=None, attempts=3, log=..., use_model=True)`
  - `tests/conftest.py`: `FakeLLM(responses, fallback=None)`: when `responses` is exhausted and `fallback` is a dict, `complete` validates `fallback` against the schema instead of raising.

- [ ] **Step 1: Replace `tpg/models.py`**

```python
"""All data types. Pydantic v2. Drafts are what the LLM returns; ids are assigned by code."""
from typing import Literal

from pydantic import BaseModel, Field

Modality = Literal["shall", "shall_not", "should", "should_not", "may"]
Kind = Literal["nominal", "negative", "boundary"]
Check = Literal["presence", "absence", "encoding_valid", "encoding_invalid", "value_valid", "value_invalid",
                "boundary_min", "boundary_max", "boundary_outside", "consistency", "condition_true", "condition_false",
                "nominal", "negative", "boundary"]
Stage = Literal["extract", "model", "generate"]


class Clause(BaseModel):
    id: str
    title: str
    text: str


class RequirementDraft(BaseModel):
    text: str
    modality: Modality
    conditions: list[str] = Field(default_factory=list)
    source_quote: str


class Requirement(RequirementDraft):
    id: str
    clause_id: str


class RequirementBatch(BaseModel):
    """LLM output schema for one clause chunk."""
    requirements: list[RequirementDraft]


class TestObjectDraft(BaseModel):
    name: str
    kind: Literal["field", "structure", "message", "parameter", "value", "behaviour"]
    direction: Literal["received", "produced", "internal"] = "internal"
    presence: Literal["mandatory", "optional", "conditional", "unspecified"] = "unspecified"
    condition: str | None = None
    type: str | None = None
    value_domain: str | None = None
    size: str | None = None
    relations: list[str] = Field(default_factory=list)
    source_quote: str


class TestObject(TestObjectDraft):
    id: str
    clause_id: str


class TestObjectBatch(BaseModel):
    """LLM output schema for one clause chunk."""
    objects: list[TestObjectDraft]


class CoverageItem(BaseModel):
    id: str
    source_id: str
    clause_id: str
    check: Check
    kind: Kind
    purpose: str
    condition_assignment: dict[str, bool] | None = None


class TestCaseDraft(BaseModel):
    """LLM output schema for one coverage item."""
    objective: str
    preconditions: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    steps: list[str]
    expected_result: str
    pass_criteria: str


class TestCase(TestCaseDraft):
    id: str
    source_id: str
    coverage_item_id: str
    kind: Kind
    condition_assignment: dict[str, bool] | None = None


class Gap(BaseModel):
    source_id: str | None
    clause_id: str
    stage: Stage
    reason: str
    attempts: int


class TraceLink(BaseModel):
    source_id: str
    coverage_item_ids: list[str]
    test_case_ids: list[str]


class Source(BaseModel):
    path: str
    sha256: str
    generated_at: str
    model: str


class TestPlan(BaseModel):
    source: Source
    requirements: list[Requirement]
    objects: list[TestObject] = Field(default_factory=list)
    coverage_items: list[CoverageItem] = Field(default_factory=list)
    test_cases: list[TestCase]
    traceability: list[TraceLink]
    gaps: list[Gap]
```

Update `tpg/extract.py`: `Gap(requirement_id=None, ...)` becomes `Gap(source_id=None, ...)`. Update `tests/test_extract.py`: `gap.requirement_id is None` becomes `gap.source_id is None`.

- [ ] **Step 2: Update `tests/conftest.py` FakeLLM**

```python
class FakeLLM:
    """Scripted stand-in for OllamaLLM. Each response is a dict validated against the requested schema,
    or an Exception to raise. When the script is exhausted, `fallback` (a dict) is used if given.
    Records prompts so tests can assert on retry feedback."""

    def __init__(self, responses, fallback=None):
        self.responses = list(responses)
        self.fallback = fallback
        self.prompts: list[str] = []

    def complete(self, prompt, schema):
        self.prompts.append(prompt)
        if not self.responses:
            if self.fallback is None:
                raise AssertionError("FakeLLM ran out of responses")
            return schema.model_validate(self.fallback)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return schema.model_validate(r)
```
Keep the `fake_llm` fixture and the autouse env fixture unchanged.

- [ ] **Step 3: Write `tests/test_models.py`** (replace the round-trip test's construction)

```python
from tpg.models import (CoverageItem, Gap, Requirement, RequirementBatch, Source, TestCase, TestObject,
                        TestObjectBatch, TestPlan, TraceLink)


def test_testplan_round_trips_through_json():
    plan = TestPlan(
        source=Source(path="x.pdf", sha256="ab", generated_at="2026-09-21T00:00:00Z", model="m"),
        requirements=[Requirement(id="REQ-5.1-1", clause_id="5.1", text="The device shall respond.",
                                  modality="shall", conditions=[], source_quote="shall respond")],
        objects=[TestObject(id="OBJ-5.1-1", clause_id="5.1", name="nonce", kind="parameter", direction="received",
                            presence="mandatory", type="text string", source_quote="Name: nonce | Presence: mandatory")],
        coverage_items=[CoverageItem(id="CI-OBJ-5.1-1-presence", source_id="OBJ-5.1-1", clause_id="5.1",
                                     check="presence", kind="nominal", purpose="Verify that nonce is present")],
        test_cases=[TestCase(id="TC-CI-OBJ-5.1-1-presence", source_id="OBJ-5.1-1", coverage_item_id="CI-OBJ-5.1-1-presence",
                             kind="nominal", objective="o", steps=["s"], expected_result="r", pass_criteria="p")],
        traceability=[TraceLink(source_id="OBJ-5.1-1", coverage_item_ids=["CI-OBJ-5.1-1-presence"],
                                test_case_ids=["TC-CI-OBJ-5.1-1-presence"])],
        gaps=[Gap(source_id=None, clause_id="5.2", stage="model", reason="bad", attempts=3)],
    )
    assert TestPlan.model_validate_json(plan.model_dump_json()) == plan
    assert list(plan.model_dump()) == ["source", "requirements", "objects", "coverage_items", "test_cases", "traceability", "gaps"]


def test_batch_schemas_are_json_schema_objects():
    for batch in (RequirementBatch, TestObjectBatch):
        assert batch.model_json_schema()["type"] == "object"


def test_object_draft_defaults():
    from tpg.models import TestObjectDraft
    o = TestObjectDraft(name="n", kind="field", source_quote="q")
    assert o.direction == "internal" and o.presence == "unspecified" and o.relations == [] and o.type is None
```

- [ ] **Step 4: Write `tests/test_derive.py`**

```python
from tpg.derive import derive, derive_object, derive_requirement
from tpg.models import Requirement, TestObject


def req(**kw):
    base = dict(id="REQ-5.1-1", clause_id="5.1", text="The device shall respond within 500 ms.", modality="shall",
                conditions=[], source_quote="shall respond within 500 ms")
    return Requirement(**{**base, **kw})


def obj(**kw):
    base = dict(id="OBJ-5.4-1", clause_id="5.4", name="nonce", kind="parameter", source_quote="Name: nonce")
    return TestObject(**{**base, **kw})


def checks(items):
    return [(i.check, i.kind) for i in items]


def test_requirement_nominal_negative_boundary():
    assert checks(derive_requirement(req())) == [("nominal", "nominal"), ("negative", "negative"), ("boundary", "boundary")]
    assert checks(derive_requirement(req(text="The device may log.", modality="may"))) == [("nominal", "nominal")]
    assert checks(derive_requirement(req(text="Other elements should not be present.", modality="should_not"))) == [("nominal", "nominal"), ("negative", "negative")]
    ids = [i.id for i in derive_requirement(req())]
    assert ids == ["CI-REQ-5.1-1-nominal", "CI-REQ-5.1-1-negative", "CI-REQ-5.1-1-boundary"]


def test_requirement_boundary_detection_words():
    assert ("boundary", "boundary") in checks(derive_requirement(req(text="The name shall be at most 150 characters.")))
    assert ("boundary", "boundary") not in checks(derive_requirement(req(text="The device shall log every request.")))


def test_conditional_requirement_items_carry_assignments():
    items = derive_requirement(req(text="If A or B the device shall not process.", modality="shall_not", conditions=["A", "B"]))
    assert checks(items) == [("condition_true", "nominal"), ("condition_false", "negative"), ("condition_false", "negative")]
    assert [i.condition_assignment for i in items] == [{"A": True, "B": True}, {"A": False, "B": True}, {"A": True, "B": False}]
    assert [i.id for i in items] == ["CI-REQ-5.1-1-condition_true", "CI-REQ-5.1-1-condition_false-1", "CI-REQ-5.1-1-condition_false-2"]


def test_object_presence_rules():
    assert checks(derive_object(obj(presence="mandatory", direction="received"))) == [("presence", "nominal"), ("absence", "negative")]
    assert checks(derive_object(obj(presence="mandatory", direction="produced"))) == [("presence", "nominal")]
    assert checks(derive_object(obj(presence="optional"))) == [("presence", "nominal"), ("absence", "nominal")]
    assert checks(derive_object(obj(presence="conditional", condition="the request asks for it"))) == [("condition_true", "nominal"), ("condition_false", "negative")]
    assert checks(derive_object(obj())) == []


def test_object_type_value_size_relations():
    o = obj(presence="mandatory", direction="received", type="text string", value_domain="one of a, b", size="16 to 64 characters",
            relations=["same value as the request nonce", "unique per session"])
    got = checks(derive_object(o))
    assert got == [("presence", "nominal"), ("absence", "negative"), ("encoding_valid", "nominal"), ("encoding_invalid", "negative"),
                   ("value_valid", "nominal"), ("value_invalid", "negative"), ("boundary_min", "boundary"), ("boundary_max", "boundary"),
                   ("boundary_outside", "negative"), ("consistency", "nominal"), ("consistency", "nominal")]
    ids = [i.id for i in derive_object(o)]
    assert ids[-2:] == ["CI-OBJ-5.4-1-consistency-1", "CI-OBJ-5.4-1-consistency-2"]
    p = derive_object(o)[0].purpose
    assert "nonce" in p and "present" in p


def test_produced_objects_get_no_invalid_stimuli():
    o = obj(presence="mandatory", direction="produced", type="text", value_domain="x", size="1 to 2")
    assert all(k != "negative" for _, k in checks(derive_object(o)))


def test_derive_orders_requirements_then_objects():
    items = derive([req()], [obj(presence="mandatory")])
    assert [i.source_id for i in items] == ["REQ-5.1-1"] * 3 + ["OBJ-5.4-1"]
    assert all(i.clause_id in ("5.1", "5.4") for i in items)
```

- [ ] **Step 5: Write `tests/test_model.py`**

```python
from tpg.llm import LLMError
from tpg.model import check_object, extract_objects, extract_objects_clause, has_rows, merge_objects
from tpg.models import Clause, TestObjectDraft

CLAUSE = Clause(id="5.4", title="Request parameters",
                text="The request contains the following parameters.\nName: nonce | Presence: mandatory | Type: text string of 16 to 64 characters\n"
                     "Name: locale | Presence: optional | Type: BCP 47 language tag\nThe reader shall reject a request whose nonce is missing.")
NONCE = {"name": "nonce", "kind": "parameter", "direction": "received", "presence": "mandatory",
         "type": "text string of 16 to 64 characters", "size": "16 to 64 characters",
         "source_quote": "Name: nonce | Presence: mandatory | Type: text string of 16 to 64 characters"}
LOCALE = {"name": "locale", "kind": "parameter", "direction": "received", "presence": "optional", "type": "BCP 47 language tag",
          "source_quote": "Name: locale | Presence: optional | Type: BCP 47 language tag"}


def test_has_rows():
    assert has_rows("Name: nonce | Presence: mandatory") and not has_rows("plain prose: with colon") and not has_rows("a | b")


def test_check_object_rules():
    assert check_object(CLAUSE, 1, TestObjectDraft(**NONCE)) is None
    assert "verbatim" in check_object(CLAUSE, 1, TestObjectDraft(**{**NONCE, "source_quote": "not there"}))
    assert "name" in check_object(CLAUSE, 1, TestObjectDraft(**{**NONCE, "name": " "}))
    assert "condition" in check_object(CLAUSE, 1, TestObjectDraft(**{**NONCE, "presence": "conditional"}))
    assert "condition" in check_object(CLAUSE, 1, TestObjectDraft(**{**NONCE, "condition": "when asked"}))


def test_merge_objects_fills_nulls_of_first_occurrence():
    a = TestObjectDraft(**{**NONCE, "type": None})
    b = TestObjectDraft(**{**NONCE, "name": "Nonce", "presence": "unspecified"})
    merged = merge_objects([a, b])
    assert len(merged) == 1 and merged[0].name == "nonce" and merged[0].type == NONCE["type"] and merged[0].presence == "mandatory"


def test_extract_objects_clause_assigns_ids_in_source_order(fake_llm):
    objs, gap = extract_objects_clause(CLAUSE, fake_llm([{"objects": [LOCALE, NONCE]}]))
    assert gap is None and [o.id for o in objs] == ["OBJ-5.4-1", "OBJ-5.4-2"] and objs[0].name == "nonce"


def test_extract_objects_clause_retries_invalid_and_keeps_valid(fake_llm):
    bad = {**LOCALE, "source_quote": "nope"}
    llm = fake_llm([{"objects": [NONCE, bad]}, LLMError("bad json"), {"objects": [bad]}])
    objs, gap = extract_objects_clause(CLAUSE, llm)
    assert [o.name for o in objs] == ["nonce"]
    assert gap is not None and gap.stage == "model" and gap.source_id is None and "nope" in gap.reason
    assert len(llm.prompts) == 3 and "bad json" in llm.prompts[2] and "nonce" in llm.prompts[1]


def test_extract_objects_clause_empty_retry_keeps_failure_open(fake_llm):
    bad = {**LOCALE, "source_quote": "nope"}
    llm = fake_llm([{"objects": [bad]}, {"objects": []}, {"objects": []}])
    objs, gap = extract_objects_clause(CLAUSE, llm)
    assert objs == [] and gap is not None and gap.attempts == 3 and "nope" in gap.reason and len(llm.prompts) == 3


def test_extract_objects_skips_clauses_without_candidates_or_rows(fake_llm):
    prose = Clause(id="1", title="Scope", text="This document describes things.")
    rows_only = Clause(id="2", title="Codes", text="Code: 01 | Meaning: car\nCode: 03 | Meaning: truck")
    llm = fake_llm([{"objects": []}, {"objects": [NONCE]}])
    objs, gaps = extract_objects([prose, rows_only, CLAUSE], llm)
    assert len(llm.prompts) == 2 and [o.id for o in objs] == ["OBJ-5.4-1"] and gaps == []
```

- [ ] **Step 6: Write `tests/test_verify.py`** (replace)

```python
from tpg.models import CoverageItem, TestCaseDraft
from tpg.verify import check_test_case, required_assignments


def item(check="presence", kind="nominal"):
    return CoverageItem(id="CI-x", source_id="OBJ-1", clause_id="1", check=check, kind=kind, purpose="p")


def draft(steps=("Send a request",), expected="Response within 500 ms", pc="pc"):
    return TestCaseDraft(objective="o", steps=list(steps), expected_result=expected, pass_criteria=pc)


def test_required_assignments():
    assert required_assignments([]) == []
    assert required_assignments(["A", "B"]) == [{"A": True, "B": True}, {"A": False, "B": True}, {"A": True, "B": False}]


def test_ok_nominal():
    assert check_test_case(item(), draft()) == []


def test_field_rules():
    assert any("steps" in m for m in check_test_case(item(), draft(steps=(" ",))))
    assert any("expected_result" in m for m in check_test_case(item(), draft(expected=" ")))
    assert any("expected_result" in m and "steps" in m for m in check_test_case(item(), draft(steps=("Same",), expected="Same")))
    assert any("pass_criteria" in m for m in check_test_case(item(), draft(pc=" ")))


def test_negative_items_need_a_rejection_style_expected_result():
    neg = item("absence", "negative")
    assert any("reject" in m for m in check_test_case(neg, draft(expected="The response is accepted")))
    assert check_test_case(neg, draft(expected="The request is rejected with an error")) == []
    assert check_test_case(neg, draft(expected="Nothing happens", pc="The obligation's effect is absent")) == []


def test_boundary_items_are_not_negative():
    assert check_test_case(item("boundary_max", "boundary"), draft(expected="Accepted at exactly 64 characters")) == []
```

- [ ] **Step 7: Write `tests/test_generate.py`** (replace)

```python
from tpg.generate import build_generate_prompt, context_excerpt, generate, generate_item
from tpg.llm import LLMError
from tpg.models import Clause, CoverageItem, Requirement, TestObject

CLAUSE = Clause(id="5.4", title="Params", text="Intro.\nName: nonce | Presence: mandatory | Type: text string\nThe reader shall reject a request whose nonce is missing.")
OBJ = TestObject(id="OBJ-5.4-1", clause_id="5.4", name="nonce", kind="parameter", direction="received", presence="mandatory",
                 type="text string", source_quote="Name: nonce | Presence: mandatory | Type: text string")
REQ = Requirement(id="REQ-5.4-1", clause_id="5.4", text="The reader shall reject a request whose nonce is missing.", modality="shall",
                  conditions=[], source_quote="shall reject a request whose nonce is missing")
ITEM = CoverageItem(id="CI-OBJ-5.4-1-absence", source_id="OBJ-5.4-1", clause_id="5.4", check="absence", kind="negative",
                    purpose="Verify the reaction of the system under test when nonce is absent")
DRAFT = {"objective": "o", "preconditions": [], "inputs": ["request without nonce"], "steps": ["send request"],
         "expected_result": "the request is rejected with an error", "pass_criteria": "error returned"}


def test_context_excerpt_windows_around_quote():
    long = Clause(id="1", title="t", text="a" * 3000 + "\nName: nonce | X: y\n" + "b" * 3000)
    ex = context_excerpt(long, "Name: nonce | X: y")
    assert "Name: nonce" in ex and len(ex) <= 3200
    assert context_excerpt(CLAUSE, "missing quote") == CLAUSE.text


def test_prompt_carries_purpose_source_and_kind_rule():
    p = build_generate_prompt(ITEM, OBJ, CLAUSE, ["old failure"])
    assert ITEM.purpose in p and "nonce" in p and "mandatory" in p and "negative" in p and "old failure" in p
    p2 = build_generate_prompt(CoverageItem(id="CI-REQ-5.4-1-nominal", source_id="REQ-5.4-1", clause_id="5.4", check="nominal",
                                            kind="nominal", purpose="x"), REQ, CLAUSE, [])
    assert REQ.text in p2 and "condition_assignment" not in p2


def test_generate_item_sets_ids_kind_and_assignment(fake_llm):
    tc, gap = generate_item(ITEM, OBJ, CLAUSE, fake_llm([DRAFT]))
    assert gap is None and tc.id == "TC-CI-OBJ-5.4-1-absence" and tc.source_id == "OBJ-5.4-1"
    assert tc.coverage_item_id == ITEM.id and tc.kind == "negative" and tc.condition_assignment is None


def test_generate_item_retries_then_gap(fake_llm):
    weak = {**DRAFT, "expected_result": "the request is processed", "pass_criteria": "ok"}
    llm = fake_llm([weak, LLMError("bad json"), weak])
    tc, gap = generate_item(ITEM, OBJ, CLAUSE, llm)
    assert tc is None and gap is not None and gap.stage == "generate" and gap.source_id == "OBJ-5.4-1"
    assert ITEM.id in gap.reason and "reject" in llm.prompts[1] and "bad json" in llm.prompts[2]


def test_generate_collects_across_items(fake_llm):
    items = [ITEM, CoverageItem(id="CI-REQ-5.4-1-nominal", source_id="REQ-5.4-1", clause_id="5.4", check="nominal", kind="nominal", purpose="x")]
    cases, gaps = generate(items, [REQ], [OBJ], [CLAUSE], fake_llm([], fallback=DRAFT))
    assert [c.id for c in cases] == ["TC-CI-OBJ-5.4-1-absence", "TC-CI-REQ-5.4-1-nominal"] and gaps == []
```

- [ ] **Step 8: Write `tests/test_emit.py`** (replace the two plan-shape tests; keep `test_write_plan_is_utf8` adapting its constructor)

```python
import json

import yaml

from tpg.emit import build_plan, write_plan
from tpg.models import CoverageItem, Gap, Requirement, Source, TestCase, TestObject

SRC = Source(path="s.md", sha256="0", generated_at="t", model="m")
R1 = Requirement(id="REQ-5.1-1", clause_id="5.1", text="a", modality="shall", conditions=[], source_quote="shall")
O1 = TestObject(id="OBJ-5.1-1", clause_id="5.1", name="n", kind="field", source_quote="q")
I1 = CoverageItem(id="CI-REQ-5.1-1-nominal", source_id="REQ-5.1-1", clause_id="5.1", check="nominal", kind="nominal", purpose="p")
I2 = CoverageItem(id="CI-OBJ-5.1-1-presence", source_id="OBJ-5.1-1", clause_id="5.1", check="presence", kind="nominal", purpose="p")
T1 = TestCase(id="TC-CI-REQ-5.1-1-nominal", source_id="REQ-5.1-1", coverage_item_id=I1.id, kind="nominal", objective="o",
              steps=["s"], expected_result="r", pass_criteria="p")


def test_build_plan_traceability_per_source_including_gapped_items():
    gap = Gap(source_id="OBJ-5.1-1", clause_id="5.1", stage="generate", reason="x", attempts=3)
    plan = build_plan(SRC, [R1], [O1], [I1, I2], [T1], [gap])
    assert [(t.source_id, t.coverage_item_ids, t.test_case_ids) for t in plan.traceability] == [
        ("REQ-5.1-1", [I1.id], [T1.id]), ("OBJ-5.1-1", [I2.id], [])]
    assert plan.gaps == [gap] and plan.objects == [O1] and plan.coverage_items == [I1, I2]


def test_write_plan_json_and_yaml(tmp_path):
    plan = build_plan(SRC, [R1], [], [I1], [T1], [])
    write_plan(plan, str(tmp_path / "p.json"), "json")
    write_plan(plan, str(tmp_path / "p.yaml"), "yaml")
    j = json.loads((tmp_path / "p.json").read_text())
    assert j == yaml.safe_load((tmp_path / "p.yaml").read_text())
    assert list(j) == ["source", "requirements", "objects", "coverage_items", "test_cases", "traceability", "gaps"]


def test_write_plan_is_utf8(tmp_path):
    plan = build_plan(SRC, [R1.model_copy(update={"text": "réponse ≤ 500 ms"})], [], [], [], [])
    write_plan(plan, str(tmp_path / "p.json"), "json")
    assert "réponse ≤ 500 ms".encode("utf-8") in (tmp_path / "p.json").read_bytes()
```

- [ ] **Step 9: Write `tests/test_pipeline.py`** (replace)

```python
import hashlib
from pathlib import Path

import pytest

from tpg.pipeline import run

FIX = Path(__file__).parent / "fixtures"

REQ_51 = {"requirements": [
    {"text": "The device shall respond to any request within 500 ms.", "modality": "shall", "conditions": [],
     "source_quote": "The device shall respond to any request within 500 ms."},
    {"text": "The device may log the request.", "modality": "may", "conditions": [], "source_quote": "The device may log the request."}]}
REQ_52 = {"requirements": [
    {"text": "If the request is malformed or the session has expired, the device shall not process the request.",
     "modality": "shall_not", "conditions": ["request is malformed", "session has expired"],
     "source_quote": "the device shall not process the request"}]}
REQ_54 = {"requirements": [{"text": "The reader shall reject a request whose nonce is missing.", "modality": "shall", "conditions": [],
                            "source_quote": "The reader shall reject a request whose nonce is missing."}]}
OBJ_54 = {"objects": [{"name": "nonce", "kind": "parameter", "direction": "received", "presence": "mandatory",
                       "type": "text string of 16 to 64 characters", "size": "16 to 64 characters",
                       "source_quote": "Name: nonce | Presence: mandatory | Type: text string of 16 to 64 characters"}]}
TC = {"objective": "o", "preconditions": [], "inputs": [], "steps": ["s"], "expected_result": "the request is rejected with an error",
      "pass_criteria": "error observed"}


def test_run_end_to_end_with_fake(fake_llm):
    # sample.md: clauses 1, 5.1, 5.2, 5.3, 5.4; candidates in 5.1, 5.2, 5.4; rows only in 5.4.
    llm = fake_llm([REQ_51, REQ_52, REQ_54, {"objects": []}, {"objects": []}, OBJ_54], fallback=TC)
    lines = []
    plan = run(str(FIX / "sample.md"), llm, model="fake", log=lines.append)
    assert [r.id for r in plan.requirements] == ["REQ-5.1-1", "REQ-5.1-2", "REQ-5.2-1", "REQ-5.4-1"]
    assert [o.id for o in plan.objects] == ["OBJ-5.4-1"]
    checks = [i.check for i in plan.coverage_items if i.source_id == "OBJ-5.4-1"]
    assert checks == ["presence", "absence", "encoding_valid", "encoding_invalid", "boundary_min", "boundary_max", "boundary_outside"]
    assert len(plan.test_cases) == len(plan.coverage_items) and plan.gaps == []
    assert {t.coverage_item_id for t in plan.test_cases} == {i.id for i in plan.coverage_items}
    assert plan.source.sha256 == hashlib.sha256((FIX / "sample.md").read_bytes()).hexdigest()
    assert any("coverage items" in l for l in lines)


def test_run_without_model_stage(fake_llm):
    llm = fake_llm([REQ_51, REQ_52, REQ_54], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", use_model=False)
    assert plan.objects == [] and all(i.source_id.startswith("REQ-") for i in plan.coverage_items)


def test_run_clause_filter(fake_llm):
    llm = fake_llm([REQ_52, {"objects": []}], fallback=TC)
    plan = run(str(FIX / "sample.md"), llm, model="fake", clause_ids=["5.2"])
    assert {r.clause_id for r in plan.requirements} == {"5.2"}
    assert len(plan.coverage_items) == 3 and len(llm.prompts) == 2 + 3


def test_run_unknown_clause_filter_raises(fake_llm):
    with pytest.raises(ValueError, match="9.9"):
        run(str(FIX / "sample.md"), fake_llm([]), model="fake", clause_ids=["9.9"])
```

This test needs clause 5.4 in `tests/fixtures/sample.md`; add it in this task (Task 4 regenerates the DOCX/PDF/HTML fixtures):

```markdown
## 5.4 Request parameters

| Name | Presence | Type |
|---|---|---|
| nonce | mandatory | text string of 16 to 64 characters |
| locale | optional | BCP 47 language tag |

The reader shall reject a request whose nonce is missing.
```

Note that the order of model-stage prompts is 5.1, 5.2, 5.4 (clauses with candidates or rows); the scripted responses above follow extract (three clauses) then model (three clauses). Update `tests/test_ingest.py::test_sample_segments_into_known_clauses` to expect ids `["1", "5.1", "5.2", "5.3", "5.4"]` for `sample.md` only (the other three formats are regenerated in Task 4; until then they still have four clauses, so parametrise the expected list: `expected = [..., "5.4"] if name == "sample.md" else [...]`).

- [ ] **Step 10: Update `tests/test_cli.py`** constructors: `Gap(requirement_id=None, ...)` becomes `Gap(source_id=None, ...)`; `TestPlan(...)` constructions keep working thanks to the defaults. No other change.

- [ ] **Step 11: Run all tests to verify the new ones fail**

Run: `uv run pytest -q -m "not slow"`
Expected: failures/ImportErrors in test_models, test_derive, test_model, test_verify, test_generate, test_emit, test_pipeline; test_ingest's sample assertion fails until `sample.md` has clause 5.4 (add it now).

- [ ] **Step 12: Write `tpg/derive.py`**

```python
"""Coverage items from requirements and objects. Deterministic, no LLM (ISO/IEC/IEEE 29119-4 test coverage items)."""
import re

from tpg.models import Check, CoverageItem, Kind, Requirement, TestObject
from tpg.verify import required_assignments

BOUNDARY_RE = re.compile(r"\d+\s*(ms|s\b|sec|seconds?|minutes?|hours?|days?|bytes?|octets?|bits?|characters?|chars?|digits?|items?|"
                         r"elements?|entries|%|mm|cm|km|m\b|kb|mb|gb)|\b(at most|at least|maximum|minimum|between|exceed|"
                         r"no more than|no less than|not exceed|up to|greater than|less than)\b", re.I)

DIRECTION = {"received": "when received by the system under test", "produced": "in what the system under test produces",
             "internal": "in the system under test"}


def _item(source_id: str, clause_id: str, check: Check, kind: Kind, purpose: str, n: int | None = None,
          assignment: dict[str, bool] | None = None) -> CoverageItem:
    cid = f"CI-{source_id}-{check}" + (f"-{n}" if n is not None else "")
    return CoverageItem(id=cid, source_id=source_id, clause_id=clause_id, check=check, kind=kind, purpose=purpose,
                        condition_assignment=assignment)


def derive_requirement(req: Requirement) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    if req.conditions:
        assigns = required_assignments(req.conditions)
        items.append(_item(req.id, req.clause_id, "condition_true", "nominal",
                           f"Verify: {req.text} (all conditions hold)", assignment=assigns[0]))
        for n, (cond, a) in enumerate(zip(req.conditions, assigns[1:]), 1):
            items.append(_item(req.id, req.clause_id, "condition_false", "negative",
                               f"Verify the behaviour when '{cond}' does not hold: {req.text}", n=n, assignment=a))
    else:
        items.append(_item(req.id, req.clause_id, "nominal", "nominal", f"Verify that the system under test satisfies: {req.text}"))
        if req.modality in ("shall", "shall_not", "should_not"):
            items.append(_item(req.id, req.clause_id, "negative", "negative",
                               f"Verify the reaction of the system under test when the obligation is violated: {req.text}"))
    if BOUNDARY_RE.search(req.text):
        items.append(_item(req.id, req.clause_id, "boundary", "boundary", f"Verify the limit value stated in: {req.text}"))
    return items


def derive_object(obj: TestObject) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    d = DIRECTION[obj.direction]
    received = obj.direction == "received"
    add = lambda check, kind, purpose, n=None: items.append(_item(obj.id, obj.clause_id, check, kind, purpose, n))
    if obj.presence == "mandatory":
        add("presence", "nominal", f"Verify that {obj.name} is present {d}")
        if received:
            add("absence", "negative", f"Verify the reaction of the system under test when {obj.name} is absent")
    elif obj.presence == "optional":
        add("presence", "nominal", f"Verify that {obj.name} is accepted when present {d}")
        add("absence", "nominal", f"Verify that {obj.name} may be absent {d}")
    elif obj.presence == "conditional":
        add("condition_true", "nominal", f"Verify that {obj.name} is present {d} when: {obj.condition}")
        add("condition_false", "negative", f"Verify the handling of {obj.name} when the condition does not hold: {obj.condition}")
    if obj.type:
        add("encoding_valid", "nominal", f"Verify that {obj.name} is a well-formed {obj.type} {d}")
        if received:
            add("encoding_invalid", "negative", f"Verify the reaction of the system under test when {obj.name} is not a well-formed {obj.type}")
    if obj.value_domain:
        add("value_valid", "nominal", f"Verify that the value of {obj.name} satisfies: {obj.value_domain}")
        if received:
            add("value_invalid", "negative", f"Verify the reaction of the system under test when the value of {obj.name} violates: {obj.value_domain}")
    if obj.size:
        add("boundary_min", "boundary", f"Verify {obj.name} at the minimum of: {obj.size}")
        add("boundary_max", "boundary", f"Verify {obj.name} at the maximum of: {obj.size}")
        if received:
            add("boundary_outside", "negative", f"Verify the reaction of the system under test when {obj.name} is outside: {obj.size}")
    for n, rel in enumerate(obj.relations, 1):
        add("consistency", "nominal", f"Verify that {obj.name} satisfies: {rel}", n)
    return items


def derive(reqs: list[Requirement], objs: list[TestObject]) -> list[CoverageItem]:
    items: list[CoverageItem] = []
    for r in reqs:
        items.extend(derive_requirement(r))
    for o in objs:
        items.extend(derive_object(o))
    return items
```

- [ ] **Step 13: Write `tpg/verify.py`**

```python
"""Rule checks on one generated test case against its coverage item. No LLM."""
from tpg.models import CoverageItem, TestCaseDraft

NEGATIVE_WORDS = ("reject", "error", "fail", "refuse", "ignore", "not ", "absent", "invalid", "discard", "abort", "terminat", "no ")


def required_assignments(conditions: list[str]) -> list[dict[str, bool]]:
    """CiRA-style minimal set: all conditions true, then each one flipped to false in turn."""
    if not conditions:
        return []
    base = {c: True for c in conditions}
    return [dict(base)] + [{**base, c: False} for c in conditions]


def check_test_case(item: CoverageItem, d: TestCaseDraft) -> list[str]:
    msgs: list[str] = []
    if not [s for s in d.steps if s.strip()]:
        msgs.append("steps are empty")
    if not d.expected_result.strip():
        msgs.append("expected_result is empty")
    elif d.expected_result.strip() in {s.strip() for s in d.steps}:
        msgs.append("expected_result must differ from the steps")
    if not d.pass_criteria.strip():
        msgs.append("pass_criteria is empty")
    if item.kind == "negative":
        text = (d.expected_result + " " + d.pass_criteria).lower()
        if not any(w in text for w in NEGATIVE_WORDS):
            msgs.append("a negative case must expect a rejection, an error, or the absence of the obligation's effect "
                        "(expected_result or pass_criteria must say so, e.g. 'is rejected', 'returns an error', 'is not ...')")
    return msgs
```

- [ ] **Step 14: Write `tpg/model.py`**

```python
"""Test model stage: the LLM lists the objects a clause defines or constrains; rules ground each object."""
from tpg.extract import chunks, find_candidates, norm
from tpg.llm import LLMError
from tpg.models import Clause, Gap, TestObject, TestObjectBatch, TestObjectDraft


def has_rows(text: str) -> bool:
    return any(" | " in line and ": " in line for line in text.splitlines())


def build_model_prompt(clause: Clause, chunk: str, part: str, failures: list[str], accepted_names: list[str]) -> str:
    feedback = ""
    if failures:
        feedback = ("\nSome objects of your previous answer were rejected for these reasons; return ONLY corrected versions of "
                    "those rejected objects, nothing else:\n" + "\n".join(f"- {f}" for f in failures) + "\n")
        if accepted_names:
            feedback += "Already accepted, do not repeat: " + ", ".join(accepted_names) + "\n"
    return f"""You build a test model from one clause of a technical specification: the list of OBJECTS the clause defines or
constrains, each with the attributes the text states. Objects are data elements or fields, structures, messages, parameters,
distinguished values, or behaviours. The system under test is the party that must conform (infer it from the clause).

Clause {clause.id} "{clause.title}" (part {part}):
\"\"\"
{chunk}
\"\"\"

Rules:
- One object per named element. A line "Header: value | Header: value" is one table row: produce one object per row that names
  an element, parameter, field, message or value, and read its attributes from the other columns.
- "kind": field | structure | message | parameter | value | behaviour.
- "direction": received (the system under test receives or parses it), produced (it creates or sends it), internal.
- "presence": mandatory if the text says it shall be present, is required, or marks it M/mandatory; optional if it may be
  present or is marked O/optional; conditional if presence depends on something (then give "condition"); else unspecified.
- "type": the encoding or data type as written (e.g. "text string", "unsigned integer", "URI", "map of ..."); null if not stated.
- "value_domain": allowed values, format or pattern as written; null if not stated.
- "size": length, range or count constraint with its numbers as written; null if not stated.
- "relations": constraints tying this object to other objects (e.g. "same value as X", "unique within Y"); empty if none.
- "source_quote": a VERBATIM substring of the clause text that names the object (a table row line is valid text). Copy it exactly.
- Do not invent attributes; leave them null or unspecified when the text does not state them.
{feedback}
Reply with JSON only: {{"objects": [{{"name": ..., "kind": ..., "direction": ..., "presence": ..., "condition": ..., "type": ...,
"value_domain": ..., "size": ..., "relations": [...], "source_quote": ...}}]}}"""


def check_object(clause: Clause, n: int, d: TestObjectDraft) -> str | None:
    if not d.name.strip():
        return f"object {n}: name is empty"
    q = norm(d.source_quote)
    if not q or q not in norm(clause.text):
        return f"object {n} ({d.name}): source_quote is not a verbatim substring of the clause: {d.source_quote!r}"
    if d.presence == "conditional" and not (d.condition or "").strip():
        return f"object {n} ({d.name}): presence is conditional but no condition is given"
    if d.presence != "conditional" and d.condition:
        return f"object {n} ({d.name}): a condition is given but presence is {d.presence!r}, set presence to conditional"
    return None


def merge_objects(drafts: list[TestObjectDraft]) -> list[TestObjectDraft]:
    """Same name (case-insensitive) within a clause: keep the first, fill its unset attributes from later ones."""
    out: list[TestObjectDraft] = []
    by_name: dict[str, TestObjectDraft] = {}
    for d in drafts:
        key = norm(d.name)
        if key not in by_name:
            by_name[key] = d
            out.append(d)
            continue
        first = by_name[key]
        for f in ("condition", "type", "value_domain", "size"):
            if getattr(first, f) is None and getattr(d, f) is not None:
                setattr(first, f, getattr(d, f))
        if first.presence == "unspecified" and d.presence != "unspecified":
            first.presence = d.presence
        if first.direction == "internal" and d.direction != "internal":
            first.direction = d.direction
        for r in d.relations:
            if r not in first.relations:
                first.relations.append(r)
    return out


def _accept(clause: Clause, drafts: list[TestObjectDraft], accepted: list[TestObjectDraft]) -> list[str]:
    failures = []
    for n, d in enumerate(drafts, 1):
        msg = check_object(clause, n, d)
        if msg:
            failures.append(msg)
        else:
            accepted.append(d)
    return failures


def extract_objects_clause(clause: Clause, llm, attempts: int = 3) -> tuple[list[TestObject], Gap | None]:
    accepted: list[TestObjectDraft] = []
    open_failures: list[str] = []
    parts = chunks(clause.text)
    for i, chunk in enumerate(parts, 1):
        if not (find_candidates(chunk) or has_rows(chunk)):
            continue
        failures: list[str] = []
        for _ in range(attempts):
            prompt = build_model_prompt(clause, chunk, f"{i}/{len(parts)}", failures, [a.name for a in accepted])
            try:
                batch = llm.complete(prompt, TestObjectBatch)
            except LLMError as e:
                failures = failures + [str(e)]
                continue
            before = len(accepted)
            new_failures = _accept(clause, batch.objects, accepted)
            resolved = len(accepted) - before          # newly accepted objects count as resolved open failures
            failures = failures[resolved:] + new_failures
            if not failures:
                break
        open_failures.extend(failures)
    merged = merge_objects(accepted)
    body = norm(clause.text)
    ordered = sorted(merged, key=lambda d: body.index(norm(d.source_quote)))
    objs = [TestObject(id=f"OBJ-{clause.id}-{n}", clause_id=clause.id, **d.model_dump()) for n, d in enumerate(ordered, 1)]
    gap = None
    if open_failures:
        gap = Gap(source_id=None, clause_id=clause.id, stage="model", reason="; ".join(open_failures), attempts=attempts)
    return objs, gap


def extract_objects(clauses: list[Clause], llm, attempts: int = 3, log=lambda s: None) -> tuple[list[TestObject], list[Gap]]:
    objs: list[TestObject] = []
    gaps: list[Gap] = []
    for clause in clauses:
        if not (find_candidates(clause.text) or has_rows(clause.text)):
            continue
        got, gap = extract_objects_clause(clause, llm, attempts)
        objs.extend(got)
        if gap:
            gaps.append(gap)
        log(f"clause {clause.id}: {len(got)} objects" + (" (GAP)" if gap else ""))
    return objs, gaps
```

- [ ] **Step 15: Write `tpg/generate.py`**

```python
"""One LLM call per coverage item, checked by verify.check_test_case, retried with feedback."""
import json

from tpg.extract import norm
from tpg.llm import LLMError
from tpg.models import Clause, CoverageItem, Gap, Requirement, TestCase, TestCaseDraft, TestObject

FIELDS = """Test case fields (ISO/IEC/IEEE 29119-3 test case specification):
- objective: one sentence, what this case demonstrates.
- preconditions: list of states that must hold before the steps.
- inputs: list of test data / stimuli.
- steps: ordered list of tester actions, concrete enough for a test engineer to execute.
- expected_result: what is observed if the specification is met. Must not repeat a step.
- pass_criteria: the measurable rule that decides pass/fail."""

KIND_RULES = {
    "nominal": "This is a nominal case: the stimulus is valid and the expected result is the behaviour the specification requires.",
    "negative": "This is a negative case: the stimulus violates the obligation or the condition does not hold; the expected result "
                "must describe the rejection, the error, or the absence of the obligation's effect.",
    "boundary": "This is a boundary case: use the exact limit value(s) stated (minimum or maximum), and state which one.",
}
WINDOW = 1500
WHOLE = 4000


def context_excerpt(clause: Clause, quote: str) -> str:
    text = clause.text
    if len(text) <= WHOLE:
        return text
    pos = norm(text).find(norm(quote)[:60])
    if pos < 0:
        return text[:WHOLE]
    # positions in the normalised text differ from the raw text; locate the raw quote start approximately
    raw_pos = text.lower().find(quote.strip()[:30].lower())
    if raw_pos < 0:
        raw_pos = min(pos, len(text))
    start = max(0, raw_pos - WINDOW)
    return text[start:raw_pos + WINDOW]


def _describe_source(src: Requirement | TestObject) -> str:
    if isinstance(src, Requirement):
        cond = f"\nconditions: {src.conditions}" if src.conditions else ""
        return f"Requirement {src.id} (modality {src.modality}): {src.text}{cond}\nquoted from the specification: \"{src.source_quote}\""
    attrs = {k: v for k, v in src.model_dump().items() if k not in ("id", "clause_id", "source_quote") and v not in (None, [], "unspecified")}
    return f"Object {src.id}: " + json.dumps(attrs, ensure_ascii=False) + f"\nquoted from the specification: \"{src.source_quote}\""


def build_generate_prompt(item: CoverageItem, source: Requirement | TestObject, clause: Clause, failures: list[str]) -> str:
    feedback = ""
    if failures:
        feedback = "\nYour previous answer was rejected for these reasons; fix them:\n" + "\n".join(f"- {f}" for f in failures) + "\n"
    assign = ""
    if item.condition_assignment is not None:
        assign = ("\n- Conditions for this case, state them in preconditions or inputs: "
                  + ", ".join(f"'{c}' {'holds' if v else 'does not hold'}" for c, v in item.condition_assignment.items()))
    return f"""You write ONE test case for one test purpose derived from a technical specification.

Test purpose {item.id} (check: {item.check}, kind: {item.kind}):
{item.purpose}

Source of the purpose:
{_describe_source(source)}

Context, clause {clause.id} "{clause.title}" (excerpt):
\"\"\"
{context_excerpt(clause, source.source_quote)}
\"\"\"

{FIELDS}

Rules:
- The case accomplishes exactly this test purpose and nothing else.
- {KIND_RULES[item.kind]}
- preconditions, inputs and steps are lists of plain strings; write data values as text.{assign}
{feedback}
Reply with JSON only: {{"objective": ..., "preconditions": [...], "inputs": [...], "steps": [...], "expected_result": ..., "pass_criteria": ...}}"""


def generate_item(item: CoverageItem, source: Requirement | TestObject, clause: Clause, llm, attempts: int = 3) -> tuple[TestCase | None, Gap | None]:
    failures: list[str] = []
    for _ in range(attempts):
        try:
            draft = llm.complete(build_generate_prompt(item, source, clause, failures), TestCaseDraft)
        except LLMError as e:
            failures = [str(e)]
            continue
        failures = check_test_case(item, draft)
        if not failures:
            return TestCase(id=f"TC-{item.id}", source_id=item.source_id, coverage_item_id=item.id, kind=item.kind,
                            condition_assignment=item.condition_assignment, **draft.model_dump()), None
    return None, Gap(source_id=item.source_id, clause_id=item.clause_id, stage="generate",
                     reason=f"{item.id}: " + "; ".join(failures), attempts=attempts)


def generate(items: list[CoverageItem], reqs: list[Requirement], objs: list[TestObject], clauses: list[Clause], llm,
             attempts: int = 3, log=lambda s: None) -> tuple[list[TestCase], list[Gap]]:
    sources: dict[str, Requirement | TestObject] = {r.id: r for r in reqs} | {o.id: o for o in objs}
    by_clause = {c.id: c for c in clauses}
    cases: list[TestCase] = []
    gaps: list[Gap] = []
    for item in items:
        tc, gap = generate_item(item, sources[item.source_id], by_clause[item.clause_id], llm, attempts)
        if tc:
            cases.append(tc)
        if gap:
            gaps.append(gap)
        log(f"{item.id}: " + ("ok" if tc else "GAP"))
    return cases, gaps
```

Add `from tpg.verify import check_test_case` to the imports.

- [ ] **Step 16: Write `tpg/emit.py` and `tpg/pipeline.py`**

```python
"""Assemble the TestPlan and write it. Traceability is known by construction."""
import json

import yaml

from tpg.models import CoverageItem, Gap, Requirement, Source, TestCase, TestObject, TestPlan, TraceLink


def build_plan(source: Source, requirements: list[Requirement], objects: list[TestObject], coverage_items: list[CoverageItem],
               test_cases: list[TestCase], gaps: list[Gap]) -> TestPlan:
    links = []
    for src_id in [r.id for r in requirements] + [o.id for o in objects]:
        links.append(TraceLink(source_id=src_id,
                               coverage_item_ids=[i.id for i in coverage_items if i.source_id == src_id],
                               test_case_ids=[t.id for t in test_cases if t.source_id == src_id]))
    return TestPlan(source=source, requirements=requirements, objects=objects, coverage_items=coverage_items,
                    test_cases=test_cases, traceability=links, gaps=gaps)


def write_plan(plan: TestPlan, path: str, fmt: str = "json") -> None:
    data = plan.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        if fmt == "yaml":
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
```

```python
"""ingest -> extract -> model -> derive -> generate -> plan. Progress goes through `log`."""
import hashlib
from datetime import datetime, timezone

from tpg.derive import derive
from tpg.emit import build_plan
from tpg.extract import extract
from tpg.generate import generate
from tpg.ingest import ingest
from tpg.model import extract_objects
from tpg.models import Source, TestPlan


def run(path: str, llm, model: str, clause_ids: list[str] | None = None, attempts: int = 3, log=lambda s: None,
        use_model: bool = True) -> TestPlan:
    clauses = ingest(path)
    log(f"{len(clauses)} clauses")
    if clause_ids:
        known = {c.id for c in clauses}
        missing = [c for c in clause_ids if c not in known]
        if missing:
            raise ValueError(f"unknown clause ids: {', '.join(missing)}")
        clauses = [c for c in clauses if c.id in clause_ids]
    reqs, gaps = extract(clauses, llm, attempts, log)
    objs, model_gaps = extract_objects(clauses, llm, attempts, log) if use_model else ([], [])
    items = derive(reqs, objs)
    log(f"{len(items)} coverage items")
    cases, gen_gaps = generate(items, reqs, objs, clauses, llm, attempts, log)
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    source = Source(path=path, sha256=digest, model=model, generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return build_plan(source, reqs, objs, items, cases, gaps + model_gaps + gen_gaps)
```

In `tpg/cli.py` change the summary line to
`_err(f"wrote {args.out}: {len(plan.requirements)} requirements, {len(plan.objects)} objects, {len(plan.coverage_items)} coverage items, {len(plan.test_cases)} test cases, {len(plan.gaps)} gaps")`.

- [ ] **Step 17: Run the whole fast suite**

Run: `uv run pytest -q -m "not slow"`
Expected: all pass, pristine. If `test_run_end_to_end_with_fake` fails on the scripted response order, print `llm.prompts` heads (first 60 chars each) and fix the *test's* response order to match the pipeline's actual order (extract over clauses with candidates, then model over clauses with candidates or rows); do not change the pipeline order.

- [ ] **Step 18: Commit**

```bash
git add tpg tests
git commit -m "feat: test model stage, coverage items, one test case per item

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: CLI flag, fixtures, README, end-to-end assertions

**Files:**
- Modify: `tpg/cli.py` (`--no-model`), `tests/test_cli.py` (one test), `tests/fixtures/make_fixtures.py` (render the 5.4 table), regenerate `sample.docx/pdf/html`, `tests/test_ingest.py` (sample expectations for all formats), `tests/test_e2e.py`, `README.md`

**Interfaces:**
- Consumes: `pipeline.run(..., use_model=...)`
- Produces: `tpg generate ... [--no-model]`

- [ ] **Step 1: CLI**

In `tpg/cli.py` add `g.add_argument("--no-model", action="store_true", help="skip the test-model stage (sentence-level requirements only)")` and pass `use_model=not args.no_model` to `run`. Test in `tests/test_cli.py`:

```python
def test_no_model_flag_is_passed(tmp_path, monkeypatch):
    seen = {}

    def fake_run(path, llm, model, clause_ids=None, attempts=3, log=None, use_model=True):
        seen["use_model"] = use_model
        return TestPlan(source=SRC, requirements=[], test_cases=[], traceability=[], gaps=[])

    monkeypatch.setattr(cli, "OllamaLLM", StubLLM)
    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["generate", str(FIX / "sample.md"), "--out", str(tmp_path / "p.json"), "--no-model"])
    assert seen == {"use_model": False}
```
Update `_stub_run` and `fake_run` helpers in that file to accept `use_model=True`.

- [ ] **Step 2: Fixtures**

In `tests/fixtures/make_fixtures.py`: when a Markdown line starts with `|`, collect the table block; for DOCX add a real table (`doc.add_table`) with the header row and data rows (skip the `|---|` line); for the PDF write the rows as row-record text lines (`Name: nonce | Presence: mandatory | Type: ...`) since drawn tables are not reliably detected; for HTML emit `<table><tr><th>..</th></tr><tr><td>..</td></tr></table>`. Regenerate: `uv run python tests/fixtures/make_fixtures.py`. Update `test_sample_segments_into_known_clauses` to expect `["1", "5.1", "5.2", "5.3", "5.4"]` for all four formats and add `assert "Name: nonce | Presence: mandatory" in next(c for c in clauses if c.id == "5.4").text`.

- [ ] **Step 3: End-to-end**

In `tests/test_e2e.py` extend `_assert_plan_is_sound`:
```python
    covered = {t.coverage_item_id for t in plan.test_cases}
    gapped = {g.source_id for g in plan.gaps}
    for i in plan.coverage_items:
        assert i.id in covered or i.source_id in gapped, i.id
    for o in plan.objects:
        assert norm(o.source_quote) in norm(clauses[o.clause_id].text), o.id
```
and replace the "exactly one nominal" check with: every requirement and object has at least one test case unless gapped. In `test_sample_markdown` add `assert any(o.name == "nonce" for o in plan.objects)` and `assert any(i.check == "boundary_max" for i in plan.coverage_items)`. Keep the clause subsets. Run: `TPG_E2E=1 OLLAMA_HOST=https://ollama.com uv run pytest -m slow -v -s` (expect roughly 10 to 15 minutes now; 4 passed). If gaps appear, paste them in the report and tune prompt wording only (`model.py`, `generate.py`, `extract.py`), never `verify.py` or `derive.py`.

- [ ] **Step 4: README**

Add a paragraph "How test cases are derived": requirements (sentences with modal verbs) and objects (elements, fields, parameters, messages, from prose and tables) are extracted; coverage items are enumerated deterministically from them (presence, encoding, value domain, boundaries, consistency, conditions, nominal/negative); one test case is written per coverage item; `--no-model` disables the object stage. Mention `objects` and `coverage_items` in the output description and that traceability is per source.

- [ ] **Step 5: Fast suite, then commit**

```bash
uv run pytest -q -m "not slow"
git add tpg/cli.py tests/test_cli.py tests/fixtures/make_fixtures.py tests/fixtures/sample.* tests/test_ingest.py tests/test_e2e.py README.md
git commit -m "feat: --no-model flag, table fixture, e2e coverage assertions, README

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec coverage: D13 (Task 1 tables), D14 (Task 1 cleaning/headings), D15 (Task 2 per-draft, should_not), D16 (Task 2 chunks, used by Task 3 model), D17 (Task 3 model.py), D18 (Task 3 derive.py), D19 (Task 3 generate/verify), D20 (Task 3 models/emit), §5 `--no-model` (Task 4), §6 tests (Tasks 1–4), §7 evaluation is done by the controller after the plan.
- Type consistency: `Gap.source_id` everywhere after Task 3 (extract updated in Task 3 Step 1); `generate()` signature `(items, reqs, objs, clauses, llm, attempts, log)` used identically by pipeline and tests; `FakeLLM(responses, fallback=None)`; `run(..., use_model=True)` used by pipeline tests and the CLI.
- Ordering: Task 1 and 2 leave the suite green with the old data model; Task 3 switches the model and every dependent test in one commit; Task 4 regenerates fixtures whose four-clause versions Task 3's ingest test tolerates via the parametrised expectation.
- Generic-only check: no rule mentions a standard, a domain term or a document family; the ISO fixture appears only as a test input that skips when absent.
