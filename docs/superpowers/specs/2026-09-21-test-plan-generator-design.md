# Test Plan Generator — Design Spec

Date: 2026-09-21
Status: draft, awaiting review

## 1. Goal

A local Python CLI that takes a technical standard (PDF, DOCX, Markdown or HTML, in English) and produces, without human intervention, a machine-readable test plan: one set of test case specifications per requirement plus a requirement-to-test traceability matrix, following the ISO/IEC/IEEE 29119-3 test case specification structure.

Non-goals (YAGNI, revisit only on demand):

- Plan-level sections (scope, schedule, risks, environment, entry/exit criteria). They are not derivable from the standard and would be invented.
- Web UI, multi-user review workflow, test management tool import.
- Executable test code. Output is test *descriptions*.
- Languages other than English.
- Hosted LLM providers. Only Ollama.

## 2. Decisions and rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Staged pipeline (ingest → extract → generate → verify), not a single prompt | End-to-end extraction oversimplifies and fabricates requirements [R1]; staged pipelines with a verification stage raise the verified-output rate from 74% to 96% [R2]. With no human review, the verify stage is the reviewer. |
| D2 | Extraction is annotation-then-conversion: a regex pass marks candidate sentences (shall / shall not / must / should / may / required), then the LLM converts each candidate into an atomic requirement | Two-stage extraction gave +29% correctly extracted specifications over end-to-end [R1]. The regex pass is cheap, deterministic, and bounds what the LLM can invent. |
| D3 | Every requirement carries a verbatim `source_quote` that must appear in its clause text | Cheapest available grounding check against fabrication [R1]. A quote that is not in the source fails verification. |
| D4 | Per requirement: 1 nominal + N negative/boundary cases; conditional requirements ("if A or B then C") have their condition combinations enumerated explicitly | Conditional requirements imply a minimal full-coverage test set that can be derived mechanically [R3]. Making conditions explicit lets the verifier check coverage instead of trusting the model. |
| D5 | LLM output is constrained by JSON Schema via Ollama structured outputs, validated with pydantic | Unverified free-text output yielded 0% requirement coverage in the RAITG baseline purely because it was unparseable [R2]. Schema-forcing removes that failure class at zero cost. |
| D6 | Verification is rule-based, not LLM-based; failures retry up to 3 times, then are recorded as `gaps` in the output | Rule verification is what produced the 22-point gain in [R2]. A retry budget of 3 gave 89% success in [R4]. Recording gaps keeps the run fully automated while never silently dropping a requirement. |
| D7 | One LLM call per requirement, prompt contains only that requirement and its parent clause | Level of detail in the requirement text is the main driver of generation success [R4]; long context dilutes it. Small prompts also suit a 14B-class local model. |
| D8 | Output is one JSON or YAML file: `requirements`, `test_cases`, `traceability`, `gaps` | Requested by the user. Traceability matrix is emitted as data, not prose, so it can be checked and diffed [R5]. |
| D9 | Ollama with a 14B–30B model on a 16GB+ GPU; model name is a CLI flag with a default | User constraint. Model is a knob because extraction quality is model-dependent [R7]. |
| D10 | Python, five modules, minimal deps: `pymupdf`, `python-docx`, `ollama`, `pydantic`, `pyyaml` | Stdlib-first. Each dep replaces code that would otherwise be reinvented (PDF text, DOCX text, LLM client, schema validation, YAML). Markdown and HTML are read with stdlib (`html.parser`). |
| D11 | ISO/IEC/IEEE 29119-3:2021 test case specification fields, not IEEE 829 | IEEE 829-2008 was superseded by 29119-3. The field sets are compatible; 29119-3 is current. |

Known limitation, stated up front: fully automated generation is contrary to the literature's recommendation that LLM-drafted requirement artifacts receive human revision [R7]. The verify stage and the `gaps` list are the mitigation. Anything in `gaps` is by definition untested.

## 3. Data model

All types are pydantic models. IDs are stable and derived from the source, so re-running on the same document yields the same IDs.

```
Clause
  id: str            # clause number as printed, e.g. "5.2.3"; fallback "p<page>-<n>" for PDFs without numbering
  title: str
  text: str

Requirement
  id: str            # "REQ-<clause id>-<n>", n = order within clause
  clause_id: str
  text: str          # atomic, rewritten as one testable statement
  modality: shall | shall_not | should | may
  conditions: list[str]   # empty if unconditional; e.g. ["A", "B"] for "if A or B then C"
  source_quote: str  # verbatim substring of Clause.text

TestCase                       # ISO/IEC/IEEE 29119-3 test case specification fields
  id: str            # "TC-<requirement id>-<n>"
  requirement_id: str
  kind: nominal | negative | boundary
  objective: str
  preconditions: list[str]
  inputs: list[str]
  steps: list[str]
  expected_result: str
  pass_criteria: str
  condition_assignment: dict[str, bool] | null   # which conditions are true/false in this case

Gap
  requirement_id: str | null   # null when the failure is at clause level
  clause_id: str
  stage: extract | generate
  reason: str                   # last verification failure message
  attempts: int

TestPlan
  source: {path, sha256, generated_at, model}
  requirements: list[Requirement]
  test_cases: list[TestCase]
  traceability: list[{requirement_id, test_case_ids: list[str]}]
  gaps: list[Gap]
```

## 4. Pipeline

### 4.1 Ingest (`ingest.py`) — no LLM

Input: file path. Output: `list[Clause]`.

- PDF: `pymupdf` text per page, joined. DOCX: `python-docx` paragraphs. Markdown: raw text. HTML: `html.parser` text.
- Clause segmentation: regex on line starts matching `^\d+(\.\d+)*\s+\S` (numbered heading). Text between two headings belongs to the first. Documents with no numbered headings fall back to one clause per page (PDF) or per top-level heading (others).
- Tables are flattened to text rows. Figures are ignored.

### 4.2 Extract (`extract.py`) — regex + LLM

Input: `list[Clause]`. Output: `list[Requirement]`, `list[Gap]`.

1. Annotation: split clause text into sentences; keep sentences matching `\b(shall|shall not|must|must not|should|should not|may|is required to)\b`. Clauses with no candidates are skipped (they produce no requirements and no gap).
2. Conversion: one LLM call per clause with candidates. Prompt contains clause id, clause text, and the candidate sentences. Schema-constrained output: a list of `Requirement` (without id). The model may split one sentence into several atomic requirements or merge none; it may not add requirements that have no candidate sentence.
3. Verification (per requirement): `source_quote` is a substring of clause text (whitespace-normalised); `text` is non-empty; `modality` matches a modal verb present in `source_quote`. Any failure rejects the whole clause's batch and retries with the failure message appended to the prompt, up to 3 attempts. After 3 failures the clause is recorded as a `Gap` with `stage=extract`.

### 4.3 Generate (`generate.py`) — LLM

Input: `Requirement` (+ parent `Clause` text). Output: `list[TestCase]`.

- One LLM call per requirement. Prompt: requirement text, modality, conditions, clause text for context, the 29119-3 field definitions, and the rule "produce exactly one nominal case, at least one negative case for shall/shall_not, and one boundary case when the requirement mentions a numeric limit, range, size, or time". For conditional requirements the prompt lists the required `condition_assignment` combinations: for `n` conditions, the CiRA-style minimal set is the all-true assignment plus one assignment per condition flipped to false (n+1 cases), assigned to nominal/negative kinds.
- Schema-constrained output: list of `TestCase` (without id).

### 4.4 Verify and emit (`verify.py`, `emit.py`)

Per requirement, after generation:

- Exactly one `nominal` case.
- Every case: `steps` non-empty, `expected_result` non-empty and not equal to any step, `pass_criteria` non-empty.
- `shall` / `shall_not` requirements have at least one `negative` case.
- Conditional requirements: the set of `condition_assignment`s equals the required set from 4.3.
- No case references a requirement id other than its own.

Failure → retry up to 3 times with the failure list appended to the prompt; then `Gap` with `stage=generate`. Requirements that ended in a gap still appear in `requirements` and in `traceability` with an empty `test_case_ids`.

Emit: assign ids, build traceability, write JSON (default) or YAML (`--format yaml`).

### 4.5 LLM client (`llm.py`)

Thin wrapper over `ollama.chat` with `format=<json schema>` and `options={"temperature": 0}`. One function: `complete(prompt: str, schema: type[BaseModel]) -> BaseModel`. Retries on malformed JSON are handled here (parse failure counts as one attempt). This is the only module that touches the network, so tests replace it with a fake.

## 5. CLI

```
tpg generate <standard file> [--out plan.json] [--format json|yaml] [--model qwen2.5:14b] [--clauses 5.2,5.3]
```

`--clauses` restricts the run to listed clause ids, for fast iteration on a long standard. Exit code 0 when `gaps` is empty, 2 when it is not (so a CI job can notice), 1 on hard errors (unreadable file, Ollama unreachable).

Progress goes to stderr, one line per clause and per requirement. No logging framework.

## 6. Error handling

- Unreadable or empty input: exit 1 with the reason.
- Ollama unreachable or model missing: exit 1 before any work starts (checked once at startup).
- LLM timeouts and malformed output: count as a failed attempt; handled by the retry budget.
- Everything that fails after the retry budget becomes a `Gap`; the run never aborts because of model output quality.

## 7. Testing

- Unit tests per stage with small fixtures under `tests/fixtures/`: a 3-clause Markdown standard, the same as DOCX and PDF (generated once, committed), one clause with a conditional requirement, one with a numeric limit.
- `llm.py` is replaced by a fake that returns canned pydantic objects, so extract/generate/verify tests are deterministic and fast. Verify tests feed hand-written bad outputs and assert the exact failure message.
- One end-to-end test against the user's sample standard, marked slow, asserting: zero `gaps`, every requirement has one nominal case, every `source_quote` is found in the source text. This is the acceptance test for the fixture.
- No mocks of Ollama's HTTP layer; the boundary is the `complete()` function.

## 8. Project layout

```
tpg/
  __init__.py
  cli.py        # argparse entry point
  models.py     # pydantic types from §3
  ingest.py
  extract.py
  generate.py
  verify.py
  emit.py
  llm.py
tests/
  fixtures/
  test_ingest.py test_extract.py test_generate.py test_verify.py test_e2e.py
pyproject.toml
```

## 9. State of the art

Searches ran on 2026-09-21 through the paper-search MCP server (arXiv, Semantic Scholar, OpenAlex, Crossref, DBLP) for: LLM test case generation from requirements, requirements extraction from standards, conformance test generation, and requirement-to-test traceability. Findings that shaped this design:

**Extraction from documents is the weak link, and staging fixes part of it.** Li et al. [R1] built a 603-specification dataset from 37 software documents and evaluated GPT-4o, Claude and Llama on end-to-end extraction. The two dominant failure modes were *oversimplification* (dropping conditions and qualifiers) and *fabrication* (inventing requirements not in the text). Their annotation-then-conversion method, which first marks the relevant sentences and only then converts them, improved correctly extracted specifications by 29.2% and average accuracy by 14 points, with the best model at 71.6%. Decisions D2 and D3 are direct applications. ReXCL [R6] independently arrives at the same shape for semi-structured requirement documents: heuristic extraction into a predefined schema, then model-based classification.

**Rule verification after generation is where most of the quality comes from.** RAITG [R2] is the closest published pipeline to this design: decompose a requirement into atomic units, expand each into structured test cases, generate, then rule-verify for structural, logical, coverage and redundancy defects. On 362 requirements across four domains, adding the verification stage raised the verification pass rate from 73.9% to 95.9%. Its unverified baseline scored 0% requirement coverage simply because the model emitted free text instead of JSON, which is the argument for schema-forced output (D5). RAITG's mutation-score indicator is regex-based, so its claims about test *strength* are weaker than its claims about structure; this design makes no test-strength claims.

**Conditional requirements can be covered mechanically.** CiRA [R3] extracts the causal structure of conditional requirements ("if A or B then C") and generates the minimal set of test case descriptions achieving full coverage. On 61 Corona-Warn-App requirements it inferred the correct test variables in 84.5% of cases and correct variable configurations in 92.3%. Standards are dense with conditional clauses, so D4 adopts the idea: the LLM is asked to name the conditions, and the verifier, not the LLM, checks that the required assignments are all present.

**Retry budgets and prompt detail.** APITestGenie [R4] generates API tests from business requirements plus OpenAPI specs using RAG and a retry loop. It produced valid tests for 89% of requirements within at most three attempts on ten real APIs, and its statistical analysis found the level of detail in the requirement text to be the primary driver of success. That motivates the 3-attempt budget (D6) and the one-requirement-per-prompt rule (D7).

**Traceability.** REST-at [R5] automates requirement-to-test-case trace links with an LLM. This design does not need to *recover* links because every test case is generated from exactly one requirement, so links are known by construction and emitted as data (D8). REST-at is the reference if traceability against pre-existing test suites is ever needed.

**Model comparison and the human-review caveat.** Korraprolu et al. [R8] compare LLMs on test case generation from natural-language requirements; together with Pasquale et al. [R7], who deployed LLM-drafted specifications in a consulting company, the consistent finding is that output quality depends heavily on model and input quality and that human revision is normally required. This project chooses full automation anyway; the `gaps` list is the honest accounting of what the automation could not do.

## 10. References

- [R1] H. Li, Z. Dong, S. Wang, H. Zhang, L. Shen, X. Peng, D. She. *Extracting Formal Specifications from Documents Using LLMs for Automated Testing.* arXiv:2504.01294, 2025. — Source for the annotation-then-conversion extraction stage and the fabrication/oversimplification failure modes (D1, D2, D3).
- [R2] V. P. Javvadi. *LLM-Based Test Case Generation from Natural-Language Requirements: A Verified Multi-Domain Empirical Study with Symbolic Mutation Indicators* (RAITG). Research Square preprint, doi:10.21203/rs.3.rs-10060668/v1, 2026. — Source for the four-stage decompose/expand/generate/verify pipeline and the measured value of rule verification (D1, D5, D6).
- [R3] J. Frattini, J. Fischbach, A. Bauer. *CiRA: An Open-Source Python Package for Automated Generation of Test Case Descriptions from Natural Language Requirements.* IEEE REW 2023, doi:10.1109/REW57809.2023.00019, arXiv:2310.08234. — Source for deriving a minimal full-coverage test set from conditional requirements (D4).
- [R4] A. Pereira, B. Lima, J. P. Faria. *APITestGenie: Generating Web API Tests from Requirements and API Specifications with LLMs.* AST 2026, doi:10.1145/3793654.3793743, arXiv:2604.02039. — Source for the 3-attempt retry budget and for keeping prompts focused on one detailed requirement (D6, D7).
- [R5] N. Leon-Quinstedt, B. Lindgren, M. Yurdakul, F. Gomes de Oliveira Neto. *REST-at: An LLM-Based Tool for Automating Traceability between Requirements and Test Cases.* AST 2026, doi:10.1145/3793654.3793746. — Reference for traceability as an explicit artifact (D8); not needed for link recovery here.
- [R6] P. Bhattacharya, M. Chakraborty, S. K. Arumugam, R. Gupta. *Read, Extract, Classify: A Tool for Smarter Requirements Engineering* (ReXCL). arXiv:2605.11045, 2026. — Corroborates heuristic-then-model extraction into a fixed schema (D2).
- [R7] L. Pasquale, A. Ragone, E. Piemontese, A. Amiri Darban. *Exploring the Use of LLMs for Requirements Specification in an IT Consulting Company.* arXiv:2507.19113, 2025. — Industrial evidence that LLM-drafted requirement artifacts need human revision; the stated limitation of the fully automated mode (D9, §2 caveat).
- [R8] B. R. Korraprolu, P. Pinninti, Y. R. Reddy. *Test Case Generation for Requirements in Natural Language — An LLM Comparison Study.* ISEC 2025, doi:10.1145/3717383.3717389. — Evidence that model choice materially changes output quality; why the model is a CLI flag (D9).
- [S1] ISO/IEC/IEEE 29119-3:2021, *Software and systems engineering — Software testing — Part 3: Test documentation.* — Source of the test case specification fields in §3 (D11).
- [S2] IEEE Std 829-2008, *Standard for Software and System Test Documentation.* — Superseded by [S1]; listed because the user named it.
