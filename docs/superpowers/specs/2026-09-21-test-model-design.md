# Test Model Stage — Design Spec (addendum to the 2026-09-21 generator design)

Date: 2026-09-21
Status: approved in discussion, implementation pending
Supersedes: §3, §4.2–§4.4 and D4/D7 of `2026-09-21-test-plan-generator-design.md` where they conflict. Everything else in that spec stands.

## 1. Why

The evaluation against ISO/IEC TS 18013-6 (`docs/evaluation/2026-09-21-iso-18013-5-evaluation.md`) showed 4.2 % coverage of the official test suite although 87 % of generated cases were valid. The official suite is an enumeration of **objects** (data elements, structures, messages, parameters) × a fixed **check ladder** (presence, encoding, value domain, size, consistency), gated by applicability. The tool generated from **sentences**, so it could not reach that granularity, and it lost the most-tested clauses to whole-batch rejection and to ingest defects on ISO layout.

The literature points the same way [R17–R21]: extract an intermediate **test model** from the text, enumerate **coverage items** from the model deterministically, and let the LLM write only the test case wording. ISO/IEC/IEEE 29119-4 names these concepts (test model, test coverage items) and the techniques (equivalence partitioning, boundary values, syntax testing, decision tables).

Nothing below refers to a particular standard family. Objects, presence, encoding and value constraints exist in every technical specification (RFC field lists, OpenID parameter tables, ISO data-element tables, API schemas).

## 2. Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D13 | Ingest preserves tables as row records: one line per row, `Header: cell \| Header: cell`, a `Table: <caption>` line before it when a caption is found, empty leading cells inherit the previous row's value (merged cells) | Element tables carry presence and type columns; flattened text loses the column meaning. pymupdf `find_tables()` recovers headers and rows on real standards (probed). |
| D14 | Generic layout cleaning: lines in the top or bottom four of a page whose digit-normalised text repeats on at least half the pages are removed (documents of four or more pages); soft hyphens (U+00AD) removed; clause numbers may have a letter prefix (`B.1.2`, `Annex B`); a heading is accepted only if its number continues the current heading's sequence (successor at any ancestor level with increment 1 or 2, first child, or a new top level); a heading built by joining a number-only line with the next line is accepted whatever the case of its title | Running headers and footers were inside 120 clause texts and inside quotes; a table cell "5.2" absorbed 122 KB; 45 clause ids were lost to the uppercase rule on titles like "mDL Reader". All rules are layout-generic, none looks at content. |
| D15 | Extraction accepts drafts individually: valid drafts are kept, invalid ones are retried with feedback, after 3 attempts the still-invalid ones become the gap. Modalities gain `should_not`; "shall never" and "must never" ground `shall_not` | One bad draft discarded whole batches of 17 valid ones (≥196 drafts lost against 215 kept). Nine of fourteen gaps were "should not" sentences the schema could not express. |
| D16 | Oversized clauses are chunked for LLM calls at blank-line boundaries into pieces of at most 8 000 characters; ids and quotes still refer to the whole clause | A ~35B model degrades on long prompts (spec D7); a single mis-segmented clause must not sink a run. |
| D17 | New stage **model**: per clause, the LLM extracts the *objects* the clause defines or constrains, with attributes (kind, direction, presence, condition, type, value domain, size or range, relations, verbatim quote). Grounded and accepted per object like requirements | The intermediate representation of AUTOSPEC [R17] and RAFT [R18]; the unit the official suites enumerate. Direction (received / produced / internal by the system under test) decides whether invalid stimuli make sense. |
| D18 | New stage **derive**: coverage items are computed from requirements and objects by fixed rules, no LLM. Each item is a test purpose with a stable id and a check type | 29119-4 test coverage items. Deterministic enumeration gives the official granularity and makes coverage checkable by construction. |
| D19 | Generation is one LLM call per coverage item; verification is: every item has exactly one test case naming it, plus the existing field rules. The nominal/negative counting rules of §4.4 are replaced by the item kinds | One case per item is simpler to verify than counting kinds, and the negative/boundary rules become explicit items instead of prompt hopes. |
| D20 | Output gains `objects`, `coverage_items`; `test_cases` carry `coverage_item_id`; traceability links each source (requirement or object) to its items and cases | Traceability at the granularity of the official suites. |

## 3. Data model (additions and changes)

```
Modality = shall | shall_not | should | should_not | may

TestObject
  id: str                  # "OBJ-<clause id>-<n>", n in source order
  clause_id: str
  name: str                # as named in the text, e.g. "family_name", "SessionEstablishment", "nonce"
  kind: field | structure | message | parameter | value | behaviour
  direction: received | produced | internal      # relative to the system under test
  presence: mandatory | optional | conditional | unspecified
  condition: str | null    # when presence is conditional
  type: str | null         # encoding / data type constraint as stated, e.g. "CBOR text string", "UTF-8 string of at most 150 characters", "URI"
  value_domain: str | null # allowed values / format as stated
  size: str | null         # length, range or count constraint as stated, with numbers
  relations: list[str]     # constraints tying it to other objects, e.g. "same value as issuing_country"
  source_quote: str        # verbatim substring of the clause text (rows included)

TestObjectBatch { objects: list[TestObjectDraft] }     # LLM output schema per clause chunk

CoverageItem
  id: str                  # "CI-<source id>-<check>[-<n>]"
  source_id: str           # requirement id or object id
  clause_id: str
  check: presence | absence | encoding_valid | encoding_invalid | value_valid | value_invalid
       | boundary_min | boundary_max | boundary_outside | consistency
       | condition_true | condition_false | nominal | negative | boundary
  kind: nominal | negative | boundary          # 29119-3 kind for the resulting test case
  purpose: str             # one sentence, templated, e.g. "Verify that family_name is present in the produced mDL response"
  condition_assignment: dict[str, bool] | null # requirements with conditions (unchanged from D4)

TestCase: unchanged fields + coverage_item_id: str; requirement_id becomes source_id: str

TraceLink
  source_id: str           # requirement or object
  coverage_item_ids: list[str]
  test_case_ids: list[str]

TestPlan: + objects: list[TestObject], + coverage_items: list[CoverageItem]
Gap.stage: extract | model | generate
```

## 4. Pipeline changes

### 4.1 Ingest (D13, D14)

- PDF: per page, `find_tables()` first; table rows are emitted in place of the table's text region as `Header: cell | Header: cell` lines (headers from the table's first row; a caption line `Table <n>...` immediately above becomes `Table: ...`). Cells spanning several lines are joined with spaces. Empty first cells inherit the previous row's first cell.
- DOCX tables: same row-record format, headers from the first row.
- Header/footer removal by repetition; soft hyphens stripped; ligature mapping stays.
- Heading rules: `HEADING_RE` accepts `(\d+|[A-Z])(\.\d+)*` numbers and `Annex [A-Z]`; the sequence-plausibility check runs in `segment()`; joined number-only headings bypass the uppercase requirement. `test_page_footer_is_not_a_heading` and the RFC page-fallback test must still pass.

### 4.2 Extract (D15, D16)

- `check_requirements` returns per-draft results; `extract_clause` keeps valid drafts, re-prompts only the invalid ones with their failure messages, and gaps only what is still invalid after 3 attempts (gap reason lists the drafts' failures).
- Clause text is chunked (D16) for the prompt; candidates and quotes are checked against the full clause text.
- Modality regexes: `should_not`: `\bshould\s+not\b`; `shall_not` also matches `\b(shall|must)\s+never\b`.

### 4.3 Model (D17) — new `tpg/model.py`

- Per clause with at least one modal candidate **or** at least one table row, one LLM call per chunk with the clause text, asking for the objects the clause defines or constrains. Prompt rules: one object per named field/structure/message/parameter; attributes only when stated in the text (else null/unspecified); `direction` relative to the system under test named in the clause or the document title; `source_quote` verbatim (a table row line counts as text).
- Checks per object: name non-empty, quote verbatim in clause text, `condition` present iff presence is conditional. Per-object acceptance as in D15. Gap stage `model`.
- Objects whose name duplicates an earlier object of the same clause (case-insensitive) are merged: non-null attributes of the later one fill nulls of the earlier.

### 4.4 Derive (D18) — new `tpg/derive.py`, no LLM

For a **requirement** (unchanged intent of D4): `nominal`; `negative` if modality is shall/shall_not/should_not; `boundary` if the text contains a number followed by a unit or the words at most/at least/maximum/minimum/between/exceed; conditional requirements produce `condition_true` (kind nominal) and one `condition_false` per condition (kind negative) with the assignment, instead of nominal/negative.

For an **object**:

| Attribute present | Items (check → kind) |
|---|---|
| presence mandatory | `presence` → nominal; `absence` → negative if direction is received |
| presence optional | `presence` → nominal (accepted when present); `absence` → nominal (accepted when absent) |
| presence conditional | `condition_true` → nominal; `condition_false` → negative |
| type | `encoding_valid` → nominal; `encoding_invalid` → negative if received |
| value_domain | `value_valid` → nominal; `value_invalid` → negative if received |
| size | `boundary_min`, `boundary_max` → boundary; `boundary_outside` → negative if received |
| relations (each) | `consistency` → nominal |

`purpose` is templated from the object's name, attribute text and direction ("Verify that the produced <name> is <type>"). Item ids are `CI-<object id>-<check>` with `-<n>` only for repeated checks (relations).

### 4.5 Generate (D19)

- One LLM call per coverage item. Prompt: the item's purpose and check, the source (requirement text or object attributes), the clause context chunk containing the quote, the 29119-3 field definitions. The model returns one `TestCaseDraft`; `kind` is set by the tool from the item, not by the model.
- Verify: `steps` non-empty, `expected_result` non-empty and not a step, `pass_criteria` non-empty; for `*_invalid`, `absence` (mandatory), `boundary_outside`, `negative` and `condition_false` the expected result must describe a rejection, error, or the absence of the obligation's effect, which the verifier checks by requiring one of the words reject, error, fail, refuse, ignore, not, absent, invalid in `expected_result` or `pass_criteria` (a coarse rule; the reviewer may propose a better one). Retry 3, then gap with `stage=generate` and `requirement_id` set to the source id.

### 4.6 Emit

`objects` and `coverage_items` are written; traceability per source as in §3. Gapped items appear in traceability with no test case id.

## 5. CLI

Unchanged flags. `--no-model` skips the model and derive-from-objects stages (sentence-level behaviour only), for comparison runs.

## 6. Testing

- Unit tests per new function with `FakeLLM`; fixture `tests/fixtures/sample.md` gains a small parameter table (Markdown pipe table) so table row records and object extraction are exercised in the fast suite; `make_fixtures.py` renders it as a real table in the DOCX and as text rows in the PDF.
- `derive` is fully deterministic: table-driven tests over every attribute combination in §4.4.
- Ingest tests: repeated header removal on a synthetic 4-page PDF; sequence-plausibility rejects a table-cell number; letter-prefixed clauses; lowercase joined titles accepted; existing tests unchanged.
- e2e (slow) unchanged in spirit; assertions extended: every coverage item has a test case or a gap.

## 7. Evaluation after implementation

Re-run `docs/evaluation` scripts (adapted to `source_id`) on the same fixture and report coverage, precision and gaps against the 2026-09-21 baseline (4.2 %, 52/60, 14 gaps).

## 8. References (added)

- [R17] K. Liu, D. Chakraborty, A. Liggesmeyer, A. Zeller. *Synthesizing Precise Protocol Specs from Natural Language for Effective Test Generation* (AUTOSPEC). arXiv:2511.17977, 2025. — Extracts protocol elements into an I/O-grammar model, then generates tests from the model without further LLM calls; 92.8 % client message types recovered on five RFC protocols (D17, D18).
- [R18] Z. Xue, X. Chen, M. Zhang. *Explicating Tacit Regulatory Knowledge from LLMs to Auto-Formalize Requirements for Compliance Test Case Generation* (RAFT). arXiv:2601.09762, 2026. — Domain meta-model plus testability constraints injected into generation prompts (D17, D19).
- [R19] Y. Wei et al. *Automated Network Protocol Testing with LLM Agents* (NeTestLLM). arXiv:2510.13248, 2025. — Hierarchical protocol understanding and iterative generation; 4 632 tests, 41 historical bugs versus 11 found by the national suite (D17).
- [R20] X. Sun et al. *iPanda: An LLM-based Agent for Automated Conformance Testing of Communication Protocols.* arXiv:2507.00378, 2025. — Systematic keyword-driven case enumeration with the LLM writing the executable part; 4.7–10.8× pass@1 over a pure-LLM baseline (D18).
- [R21] M. Rodríguez, G. Rossi, A. Fernandez. *Evaluating Large Language Models for the Generation of Unit Tests with Equivalence Partitions and Boundary Values.* arXiv:2505.09830, JCC-BD&ET 2025. — Prompting for partitions and boundaries helps only with precise requirements as input (D18, D19).
- [S3] ISO/IEC/IEEE 29119-4:2021, *Software testing — Part 4: Test techniques.* — Test model, test coverage items, equivalence partitioning, boundary value analysis, syntax testing (D18).
- Observation source: ISO/IEC TS 18013-6:2025 appendices, analysed in `docs/evaluation/2026-09-21-iso-18013-5-evaluation.md`: 907 tests in 118 object families, check ladder presence / encoding / value / size / consistency, applicability by feature and profile.

Note: the paper-search MCP server stopped returning results during this session; [R17]–[R21] were located by web search and read from arXiv.
