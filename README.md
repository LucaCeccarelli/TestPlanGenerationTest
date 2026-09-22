# tpg -- test plan generator

Turns a technical standard (PDF, DOCX, Markdown, HTML, text) into a JSON or YAML test plan:
atomic requirements, the objects the text defines, the coverage items they imply,
ISO/IEC/IEEE 29119-3 test cases (nominal, negative, boundary), a per-source traceability matrix,
and a list of gaps the pipeline could not fill.
Design and rationale: `docs/superpowers/specs/2026-09-21-test-plan-generator-design.md`.

## How test cases are derived

1. **Requirements**: sentences carrying a modal verb (shall, shall not, should, should not, may),
   each kept with its conditions and a verbatim quote from the clause it came from.
2. **Objects**: the elements, fields, parameters, messages, values and behaviours the clause defines
   or constrains, read from prose and from tables, with the presence, type, value domain, size and
   relations the text states. `--no-model` skips this stage, leaving sentence-level requirements only.
3. **Coverage items**: enumerated deterministically from requirements and objects, without the model --
   presence and absence, encoding valid and invalid, value domain valid and invalid, boundaries
   (minimum, maximum, outside), consistency relations, each condition true and false, and plain
   nominal and negative checks for requirements that state no conditions.
4. **Test cases**: one per coverage item, written by the model and grounded in the clause text.

The plan therefore carries `requirements`, `objects`, `coverage_items`, `test_cases`, `traceability`
and `gaps`. Traceability is per source: one entry per requirement and per object, listing the
coverage items it produced and the test cases written for them.

## Setup

    uv sync

Ollama server: local by default (`http://localhost:11434`). For a remote server set
`OLLAMA_HOST`, and `OLLAMA_API_KEY` if it needs one. A `.env` file in the working directory
is read (`KEY=VALUE` lines). `OLLAMA_TIMEOUT` (seconds, default 120) bounds each model call; a
stalled call counts as a failed attempt.

## Run

    uv run tpg generate standard.pdf --out plan.json
    uv run tpg generate standard.pdf --out plan.yaml --format yaml --model gemma4:31b --clauses 5.1,5.2 --attempts N
    uv run tpg generate standard.pdf --out plan.json --no-model   # requirements only, no object stage

Cost: one LLM call per coverage item plus one per clause chunk for requirements and one for
objects; a small clause with three objects costs about ten calls. Use `--clauses` to scope a run
and `--no-model` for the cheaper sentence-level plan.

Exit code 0: no gaps. 2: some clauses ended in `gaps` at the extract or model stage, or some
coverage items ended in `gaps` at the generate stage (the plan is still written). 1: bad input or
Ollama unreachable.

RFCs: feed the `.txt` or `.html` from the RFC Editor; the PDF rendering loses section numbers and falls back to page-level clauses.

## Limitations

- Unnumbered documents fall back to one clause per top-level heading (or per page for PDFs).
- PDF fonts without a Unicode map may still yield odd characters.
- Requirement ids are stable per document and model, not across re-runs with a different model.
- Structural markers are English-only: `Annex`, `Appendix`, `Table`, and the modal verbs shall,
  must, should, may. Documents using other-language equivalents will under-segment or under-extract.
- A zero-gap run is an optimistic signal, not a proof: a retry that answers with an unrelated but
  valid draft can close an open failure without actually fixing it.

## Tests

    uv run pytest                                         # fast, no network
    TPG_E2E=1 OLLAMA_HOST=https://ollama.com uv run pytest -m slow -v   # real model, real documents
