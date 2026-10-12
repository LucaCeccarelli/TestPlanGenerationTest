# Conformance Methodology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Put the tool on the ISO/IEC 9646-2 conformance methodology: an auditable ICS proforma with a coverage rule, applicability predicates, the four test groups, formal-declaration harvesting, generic test suites, and an evaluation that does not depend on an LLM judge.

**Architecture:** `ingest -> grammar (deterministic objects) -> extract requirements -> model (LLM objects) -> ics -> derive (coverage items, groups, deflation) -> generate (batched per source) -> verify -> emit`.

**Spec:** `docs/superpowers/specs/2026-10-12-conformance-methodology-design.md`. Read it; its decision table D21 to D29 is binding and its §3 and §4 define the data model and the stage behaviour.

## Global Constraints

- Python >= 3.12, `uv`. Runtime deps unchanged: `pydantic>=2`, `ollama>=0.5.1`, `pymupdf`, `python-docx`, `pyyaml`. No new dependency.
- `ingest.py`, `grammar.py`, `ics.py`, `derive.py`, `verify.py`, `emit.py` never call the LLM. `llm.py` is the only network module.
- **Nothing may be specific to a document family, a standard or a domain.** Notation handlers are keyed on the notation's own syntax, never on a standard's name. Applicability conditions are stored as verbatim text, never as a controlled vocabulary.
- No literal non-ASCII in code; use `\u` escapes.
- IDs: `OBJ-<clause>-<n>`, `REQ-<clause>-<n>`, `ICS-<source id>`, `CI-<source id>-<check>[-<n>]`, `TC-<coverage item id>`.
- Fast suite pristine before every commit: `uv run pytest -q -m "not slow"`. Never run the slow suite without being told to.
- Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- `.env` and `tests/fixtures/iso_18013_5.pdf` are never committed.

---

### Task 1: Robustness and row accounting (D28)

**Files:** modify `tpg/extract.py`, `tpg/llm.py`, `tpg/ingest.py`, `tpg/models.py`, `tpg/model.py`; tests in `tests/test_llm.py`, `tests/test_ingest.py`, `tests/test_model.py`, `tests/test_extract.py`.

**Changes**
1. `CHUNK_LIMIT` becomes 3000 in `tpg/extract.py`.
2. `tpg/llm.py` gains `salvage_json_array(text, key)` returning the complete elements of a truncated array: find `"<key>": [`, then walk elements with the existing brace matcher, keeping those that close, and return `{"<key>": [...]}`. `complete()` uses it when `clean_json` raises and the schema has exactly one list field, so a truncated reply yields its complete elements rather than nothing. A salvaged reply is still validated.
3. `Clause` gains `row_count: int = 0`; `ingest.segment` sets it to the number of lines containing `" | "`.
4. `tpg/model.py`: after the per-chunk loop, if `clause.row_count > 0` and the number of accepted objects whose `source_quote` contains `" | "` is less than `row_count`, re-prompt once per remaining attempt with the row records that no accepted object quotes, asking only for those. Residue becomes a gap whose reason names `<got>/<row_count> rows`.

**Tests**
- `salvage_json_array` on `'{"objects": [{"a": 1}, {"b": 2}, {"c":'` returns two elements; on no complete element returns None; braces inside strings respected.
- `complete()` returns the two elements for a truncated `TestObjectBatch` reply instead of raising.
- `segment` sets `row_count` to 2 for a clause with two row-record lines, 0 otherwise; the ISO fixture's clause `7.4.1` has `row_count == 33`.
- `extract_clause` chunking unchanged in behaviour but `chunks(text)` now splits at 3000; assert the limit constant is 3000 and that `tests/fixtures/iso_18013_5.pdf` clause `7.4.1` yields 4 chunks whose largest is under 3000.
- A `FakeLLM` scripted to return 2 objects for a clause with `row_count=5` re-prompts with the missing rows and gaps naming `2/5 rows`.

---

### Task 2: Data model v3, ICS proforma, groups, applicability (D21, D22, D23)

**Files:** modify `tpg/models.py`, `tpg/derive.py`, `tpg/emit.py`, `tpg/extract.py`, `tpg/model.py`; create `tpg/ics.py`, `tests/test_ics.py`; modify `tests/test_models.py`, `tests/test_derive.py`, `tests/test_emit.py`, `tests/test_extract.py`, `tests/test_model.py`.

**Model additions** exactly as spec §3: `Origin`, `Status`, `Group` literals; `applies_when: list[str] = []` on `RequirementDraft` and `TestObjectDraft` with the same lenient list coercion as the other list fields; `origin: Origin = "prose"` on `TestObject` only (not the draft); `ICSItem`; `CoverageItem` gains `group: Group`, `applies_when: list[str] = []`, `generic_group: str | None = None`; `Check` gains `capability`, `inopportune`, `reference`; `TestPlan` gains `ics: list[ICSItem] = []` positioned between `objects` and `coverage_items`.

**`tpg/ics.py`**: `build_ics(reqs, objs) -> list[ICSItem]`. One item per object whose `presence != "unspecified"` and per requirement, in that order: objects first, then requirements. `feature` is the object's name, or the requirement's text truncated at 160 characters. Status: object presence straight through; requirement modality shall and shall_not to `mandatory`, should, should_not and may to `optional`. Skip sources with an empty feature. `id = "ICS-" + source_id`.

**`tpg/derive.py`**: `derive(reqs, objs, ics)` now takes the ICS list and emits, in order:
1. one `capability` item per ICS item of status `mandatory` or `optional`, `kind="nominal"`, purpose templated as `Verify that the implementation supports <feature>`, `group="capability"`, `applies_when` from the ICS item;
2. the existing requirement and object ladders, each item gaining `group` from a fixed map (`presence`, `encoding_valid`, `value_valid`, `consistency`, `condition_true`, `nominal`, `boundary_min`, `boundary_max`, `capability`, `reference` to `valid_behaviour`; `absence`, `encoding_invalid`, `value_invalid`, `boundary_outside`, `negative`, `condition_false` to `invalid_behaviour`; `boundary` to `valid_behaviour`; `inopportune` to `inopportune_behaviour`) and `applies_when` from its source;
3. one `inopportune` item, `kind="negative"`, for each object with `direction == "received"`, `kind in ("message", "structure")` and a non-empty `condition`, purpose `Verify the handling of <name> supplied when <condition> does not hold`.

A helper `group_for(check) -> Group` is exported and table-tested over every member of `Check`.

**`tpg/emit.py`**: `build_plan` takes `ics` and writes it; key order becomes `source, requirements, objects, ics, coverage_items, test_cases, traceability, gaps`.

**Prompts**: the extract and model prompts gain one rule each asking for `applies_when`, described as the conditions under which the obligation or the element applies, quoted from the clause, empty when it always applies. No vocabulary is suggested.

**Tests**
- `build_ics`: status mapping for all five modalities and all four presences; ordering objects then requirements; empty feature skipped; id format.
- `group_for` covers every value of `Check` with no fall-through.
- `derive`: a capability item per mandatory and optional ICS item and none for unspecified; `applies_when` propagated; an `inopportune` item appears for a received message with a condition and not for a produced one nor for a field; every emitted item has a group.
- `emit`: key order includes `ics`; an ICS item with no coverage item is still written.
- Round-trip test in `test_models.py` covers the new fields.

---

### Task 3: Grammar stage (D24)

**Files:** create `tpg/grammar.py`, `tests/test_grammar.py`; modify `tpg/pipeline.py`, `tpg/model.py`, `tests/fixtures/sample.md`, `tests/fixtures/make_fixtures.py`, `tests/test_ingest.py`, `tests/test_pipeline.py`.

**`tpg/grammar.py`**, no LLM. `harvest(clause) -> list[TestObjectDraft]` runs four handlers over the clause text and returns their union, de-duplicated by `(name, source_quote)`.

Each handler is `detect(text) -> list[str]` returning candidate blocks, then `parse(block) -> list[TestObjectDraft]`. Detection may be permissive because the parser rejects what it cannot read; a handler that parses nothing contributes nothing.

- `cddl`: blocks starting at a line matching `^[A-Za-z][\w-]*\s*=\s*[({\[]` and running to the matching close. Members on lines `[?*+]?\s*<key>\s*:\s*<type>` or `<key>\s*=>\s*<type>`. `?` gives `presence="optional"`, otherwise `mandatory`; `*` or `+` records `size` as the occurrence marker. `.size N`, `.size (a..b)` and `a..b` go to `size`; a `/`-separated list of literals goes to `value_domain`. Object `kind="field"`, the enclosing rule name recorded in `relations` as `member of <rule>`.
- `abnf`: lines matching `^<rulename>\s*=/?\s*<elements>$` where rulename is `[A-Za-z][A-Za-z0-9-]*`. One object per rule, `kind="structure"`, `type` the element text, `value_domain` the `/`-alternatives when they are all quoted literals, `size` any `*`-repetition bounds. A rule referenced only inside `[...]` in another rule gets `presence="optional"`.
- `json_schema`: blocks that parse with `json.loads` and contain a `properties` object. One object per property: `presence` mandatory when listed in `required` else optional, `type` from `type`/`format`, `value_domain` from `enum`/`const`/`pattern`, `size` from `minimum`/`maximum`/`minLength`/`maxLength`/`minItems`/`maxItems`.
- `asn1`: blocks `^<Name>\s*::=\s*(SEQUENCE|SET|CHOICE)\s*\{` to the matching brace. Members `^\s*<field>\s+<Type>` with `OPTIONAL` or `DEFAULT x` giving `presence="optional"`, `SIZE(a..b)` and `(a..b)` giving `size`, a braced named-number list giving `value_domain`.

Every draft carries a `source_quote` that is a verbatim line of the clause text, so `check_object` passes unchanged. All drafts get `direction="internal"` unless the enclosing rule name or the clause title contains a request or response word, in which case leave it `internal` anyway: direction is prose knowledge and is not guessed here.

**Wiring**: `pipeline.run` gains `use_grammar: bool = True`. Grammar objects are built first, converted to `TestObject` with `origin="grammar"` and ids continuing the clause's numbering, and the LLM model stage is told, per clause, the names already found so it does not repeat them; its objects get `origin="prose"`. Both lists are merged with `model.merge_objects` so an attribute the prose states and the grammar does not is filled in.

**Fixture**: `tests/fixtures/sample.md` gains a clause `5.5` containing one small CDDL block, one ABNF rule, one JSON Schema object and one ASN.1 SEQUENCE, each with two or three members. `make_fixtures.py` renders them as plain indented text in all formats. Ingest tests assert clause `5.5` exists; the grammar test asserts the member inventory per notation.

**Tests**: per notation, a block with a mandatory member, an optional member, a size constraint and a value list, asserting the exact `TestObjectDraft` fields; a block of each notation that is malformed yields nothing and raises nothing; `harvest` on a clause with no formal block returns `[]`; `harvest` on the fixture clause `5.5` returns members from all four notations; a quote check that every returned `source_quote` is a substring of the clause text.

---

### Task 4: Deflation, generic test suites (D25)

**Files:** modify `tpg/derive.py`, `tpg/models.py` if needed, `tests/test_derive.py`; modify `tpg/cli.py` and `tpg/pipeline.py` for the flag.

**Rules**, applied in `derive` after the ladders, in this order:

1. **Generic groups.** Group objects by `norm(name)`. For a name occurring in more than one clause, the occurrence in the clause with the most coverage items owns them; every other occurrence loses its items and gains exactly one item with `check="reference"`, `kind="nominal"`, `group="valid_behaviour"`, `generic_group=<normalised name>`, purpose `Perform the test purposes of <name> specified for clause <owning clause>`.
2. **Requirement and object overlap.** A requirement-derived item is dropped when the requirement's `text` contains the name of an object (word-boundary, case-insensitive, names of three characters or more) that has an item of the same `check` in the same clause. Requirement items of check `nominal` are compared against object checks `presence`, `encoding_valid` and `value_valid`; `negative` against `absence`, `encoding_invalid`, `value_invalid`; `boundary` against `boundary_min` and `boundary_max`.

`derive(..., deflate: bool = True)`; `pipeline.run(..., deflate=True)`; CLI `--no-deflate`.

**Tests**: two clauses declaring an object of the same name produce one owning set plus one reference item, and the owner is the richer one; a requirement naming an object drops only the matching checks and keeps the others; a requirement naming no object keeps everything; `deflate=False` leaves counts unchanged; ids of surviving items are unchanged by deflation.

---

### Task 5: Batched generation (D26)

**Files:** modify `tpg/generate.py`, `tpg/pipeline.py`, `tpg/cli.py`, `tests/test_generate.py`, `tests/test_pipeline.py`, `tests/test_cli.py`.

`BATCH_LIMIT = 8`. New `TestCaseBatch` draft schema: a list of objects each carrying `coverage_item_id` plus the existing `TestCaseDraft` fields. `generate_source(source, clause, items, llm, attempts)` sends one prompt listing every item's id, check, kind and purpose, asks for one case per id and nothing else, accepts the cases whose id is expected and that pass `check_test_case` for their own item, and re-prompts only the missing or failing ids. Unknown ids are a failure message naming them. Items still unproduced after the retries become gaps as before. `generate(items, reqs, objs, clauses, llm, attempts, log, batch=True)` groups items by `source_id` preserving item order; `batch=False` keeps the existing per-item path unchanged. CLI `--no-batch`.

**Tests**: a batch of three items answered in one reply yields three cases with the right ids and kinds; a reply missing one id re-prompts for that id only and the second reply completes it; a reply with an unknown id reports it and does not create a case; a reply whose case fails the negative-wording rule re-prompts only that id; more than `BATCH_LIMIT` items for one source split into several calls; `batch=False` still produces one call per item; the pipeline end-to-end test passes with batching on.

---

### Task 6: Wiring, CLI, documentation, end-to-end (all decisions)

**Files:** modify `tpg/pipeline.py`, `tpg/cli.py`, `README.md`, `tests/test_cli.py`, `tests/test_pipeline.py`, `tests/test_e2e.py`.

`run(path, llm, model, clause_ids=None, attempts=3, log=..., use_model=True, use_grammar=True, deflate=True, batch=True) -> TestPlan` runs ingest, grammar, extract, model, build_ics, derive, generate, build_plan, and logs one line per stage with its counts including the ICS total and the ICS coverage percentage. CLI gains `--no-grammar`, `--no-deflate`, `--no-batch` beside `--no-model`, and the summary line reports requirements, objects, ICS items, coverage items, cases, gaps and ICS coverage.

README gains a section on the methodology: the ICS proforma and its coverage rule, the four test groups, what the grammar stage harvests, what deflation does, and the four flags with what each measures. State plainly that ICS coverage is the headline metric and needs no official suite.

`tests/test_e2e.py` adds: every ICS item of status mandatory or optional has at least one coverage item; every coverage item has a group; a reference item exists only where a name recurs; `applies_when` is a list of strings everywhere.

---

### Task 7: Evaluation harness (D27)

**Files:** modify `tools/eval/judge.py`, `tools/eval/summarise.py`, `tools/eval/parse_appendices.py`, `tools/eval/run.sh`; create `tools/eval/match_structural.py`.

1. `parse_appendices.py` keeps the `Reference` field's cited clause ids, already done, and additionally writes for each case a `check_type` inferred by rule from `purpose` plus `scenario` using the keyword ladder already used in the earlier analysis (presence, encoding, value domain, size, consistency, behaviour, reuse), and a `data_item`: the first quoted or code-styled token, else the first `data element X`, `the X field`, `the X data item` capture, else null.
2. `match_structural.py`: for every official case with a `data_item` and a `check_type`, a generated artefact matches when some coverage item's source object name equals the data item (normalised) and its check maps to the same check family. Reports matched, unmatched, and the per-family breakdown. No LLM.
3. `summarise.py` reports the three denominators (907, clause-citing, in-edition where the cited id exists among the input's clause ids), ICS coverage, the structural match rate beside the LLM judge rate, and macro averages over clauses and over families.
4. `run.sh` runs the structural matcher before the judge so a result exists even if the model is unavailable.

**Tests:** none required for `tools/eval` beyond a smoke run on the existing artefacts, since it is a research harness, but every script must run without a model and print its sections when inputs are missing.

---

## Self-review notes

- Spec coverage: D21 Task 2, D22 Task 2, D23 Task 2, D24 Task 3, D25 Task 4, D26 Task 5, D27 Task 7, D28 Task 1, D29 recorded only.
- Ordering: Task 1 is independent; Task 2 changes the data model and every later task builds on it; Task 3 adds an object source and must land after the model exists; Task 4 depends on the ladders of Task 2; Task 5 is orthogonal to 3 and 4 but touches `generate`; Task 6 wires everything; Task 7 is separate from the package.
- Genericity: no handler, rule or prompt names a standard, a family or a domain term. Notation handlers key on each notation's own syntax, which is itself a public specification.
