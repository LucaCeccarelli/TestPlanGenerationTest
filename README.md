# tpg -- test plan generator

Turns a technical standard (PDF, DOCX, Markdown, HTML, text) into a JSON or YAML test plan:
atomic requirements, ISO/IEC/IEEE 29119-3 test cases (nominal, negative, boundary), a
requirement-to-test traceability matrix, and a list of gaps the pipeline could not fill.
Design and rationale: `docs/superpowers/specs/2026-09-21-test-plan-generator-design.md`.

## Setup

    uv sync

Ollama server: local by default (`http://localhost:11434`). For a remote server set
`OLLAMA_HOST`, and `OLLAMA_API_KEY` if it needs one. A `.env` file in the working directory
is read (`KEY=VALUE` lines).

## Run

    uv run tpg generate standard.pdf --out plan.json
    uv run tpg generate standard.pdf --out plan.yaml --format yaml --model gemma4:31b --clauses 5.1,5.2 --attempts N

Exit code 0: no gaps. 2: some requirements or clauses ended in `gaps` (still written). 1: bad input or Ollama unreachable.

RFCs: feed the `.txt` or `.html` from the RFC Editor; the PDF rendering loses section numbers and falls back to page-level clauses.

## Limitations

- Unnumbered documents fall back to one clause per top-level heading (or per page for PDFs).
- PDF fonts without a Unicode map may still yield odd characters.
- Requirement ids are stable per document and model, not across re-runs with a different model.

## Tests

    uv run pytest                                         # fast, no network
    TPG_E2E=1 OLLAMA_HOST=https://ollama.com uv run pytest -m slow -v   # real model, real documents
