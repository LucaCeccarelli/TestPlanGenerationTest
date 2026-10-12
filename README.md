# tpg -- test plan generator

Turns a technical standard (PDF, DOCX, Markdown, HTML, text) into a JSON or YAML test plan:
atomic requirements, the objects the text defines, an ICS proforma of the features the standard
declares, the coverage items they imply, ISO/IEC/IEEE 29119-3 test cases (nominal, negative,
boundary), a per-source traceability matrix, and a list of gaps the pipeline could not fill.
Design and rationale: `docs/superpowers/specs/2026-09-21-test-plan-generator-design.md` and
`docs/superpowers/specs/2026-10-12-conformance-methodology-design.md` (the conformance methodology).

## How test cases are derived

1. **Requirements**: sentences carrying a modal verb (shall, shall not, should, should not, may),
   each kept with its conditions and a verbatim quote from the clause it came from.
2. **Objects**: the elements, fields, parameters, messages, values and behaviours the clause defines
   or constrains, read from prose, from tables and from the formal declarations the clause embeds,
   with the presence, type, value domain, size and relations the text states. `--no-model` skips the
   model stage, `--no-grammar` the formal declarations.
3. **ICS items**: one line per feature the standard declares, with the status the clause gives it.
4. **Coverage items**: enumerated deterministically from the ICS, the requirements and the objects,
   without the model -- capability, presence and absence, encoding valid and invalid, value domain
   valid and invalid, boundaries (minimum, maximum, outside), consistency relations, each condition
   true and false, a valid structure supplied out of its stated precondition, and plain nominal and
   negative checks for requirements that state no conditions.
5. **Test cases**: one per coverage item, written by the model and grounded in the clause text.

The plan therefore carries `requirements`, `objects`, `ics`, `coverage_items`, `test_cases`,
`traceability` and `gaps`. Traceability is per source: one entry per requirement and per object,
listing the coverage items it produced and the test cases written for them.

## Methodology

### The ICS proforma is the yardstick

Conformance testing measures a test suite against the features a standard declares, not against
somebody else's test suite. The generator emits an **Implementation Conformance Statement
proforma**: one `ICSItem` per feature, carrying the status the text gives it -- `mandatory`,
`optional`, `conditional` or `unspecified` -- taken from an object's stated presence or from a
requirement's modality (shall and shall not are mandatory, should, should not and may are optional).

The coverage rule follows ISO/IEC 9646-2 (ITU-T X.291) clause 10.3.5, "at least one test purpose
related to each distinct conformance requirement", in the form ETSI's test purpose style guide
states it: any mandatory or optional item of the ICS is covered by at least one test purpose. The
derive stage satisfies it by construction, emitting one `capability` coverage item per mandatory or
optional ICS item, and every run audits itself against it: the pipeline log and the CLI summary both
end in `ICS coverage P% (covered/due)`, over the mandatory and optional items only.

**ICS coverage is the headline metric, and it needs no official test suite.** Matching a generated
plan against a published suite is possible only for the few standards that have one, it measures the
other suite's editorial choices as much as this one's reach, and the figures the literature reports
under that kind of matching are low. The ICS criterion is computed from the input document alone, so
it transfers unchanged to any standard, including the large majority that no official suite covers.
It is a necessary condition, not a sufficient one: it says every declared feature is addressed, not
that the cases addressing it are good.

### Four test groups

Every coverage item carries a `group` from X.291 clause 10.2.2, which is how a conformance test suite
is structured:

| group | what it tests |
|---|---|
| `capability` | the implementation supports the feature the ICS declares |
| `valid_behaviour` | a valid stimulus gets the required behaviour |
| `invalid_behaviour` | an invalid stimulus is rejected, or is never produced |
| `inopportune_behaviour` | a valid structure or message supplied when its stated precondition does not hold |

Requirements, objects, ICS items and coverage items also carry `applies_when`, the verbatim
applicability conditions the clause states, stored as text and never as a controlled vocabulary, so
no document family is baked in. Generated cases state them.

For an invalid-side item, the direction of the object selects the wording and not the existence of
the item: for a received object the purpose asks that an invalid instance be supplied and rejected,
for a produced or internal one that the implementation never produces or holds an invalid instance.
Both are test purposes; a decoder must reject what an encoder must not emit.

### The grammar stage harvests the formal declarations

Standards declare their data structures formally and then constrain them in prose. Before any model
call, a deterministic stage reads the clause text and emits objects from the declarations it finds:

- **CDDL** groups and their members, with optional, repeated, `.size`, `.default` and ranges.
- **ABNF** rules, with the element list as the type and optional groups as optional presence.
- **JSON Schema** objects, walking `properties`, `required`, `type`, `enum` and the bounds.
- **ASN.1** `SEQUENCE` and `CHOICE` members, with `OPTIONAL`, `DEFAULT`, `SIZE` and named values.

Detection is a signature match per notation and each handler's parser is the acceptance gate, so a
prose line that merely looks like a declaration is dropped rather than turned into an object. Every
object carries `origin: "grammar"` and the verbatim declaration line as its `source_quote`, so the
same grounding check applies as for prose objects, and a name a declaration already produced is not
asked of the model again.

### Deflation keeps the suite the size a suite should be

Enumerating every axis over every source produces far more cases than a human suite for the same
standard, and most of the excess is the same structure tested once per use site. Two deterministic
rules cut it, in this order:

1. **Generic test suites** (X.291 clause 11 and Annex D). Objects that recur in several clauses with
   the same obligations form a group, keyed on the normalised name together with every attribute that
   decides the group's test purposes: kind, presence, direction, type, value domain and size. The
   occurrence with the richest ladder owns them; every other site keeps a single `reference` item,
   `Perform the test purposes of <name> specified for clause <id>`, with `generic_group` naming the
   group. Occurrences that share a name but differ on a keyed attribute are distinct declarations and
   each keeps its own ladder, because a reference may only stand for the same specification.
2. **Requirement and object overlap.** A requirement-derived item is dropped when an object of the
   same clause was read off the same prose, decided by comparing the object's `source_quote` with the
   requirement's `text` rather than by looking for the object's name inside the sentence. The
   object-derived item, which carries the stated type, domain and bounds, is the one kept.

Neither rule removes an ICS item, and a reference item still covers its ICS item, so deflation cannot
lower ICS coverage.

### The four measurement flags

Each flag disables exactly one stage or rule, so its contribution can be measured on the same input
by differencing two runs.

| flag | what it measures |
|---|---|
| `--no-model` | what the LLM model stage adds over the deterministic stages: run it and compare `objects`, `ics` and `coverage_items` |
| `--no-grammar` | what the formal declarations add: the objects of `origin: "grammar"` and everything derived from them |
| `--no-deflate` | the cost of deflation: the difference in `coverage_items` is what the two rules removed, and comparing the plans shows what was lost |
| `--no-batch` | the cost of batching: one model call per coverage item instead of one per source, with the same plan, so the two can be compared for case quality at a known call count |

## Setup

    uv sync

Ollama server: local by default (`http://localhost:11434`). For a remote server set
`OLLAMA_HOST`, and `OLLAMA_API_KEY` if it needs one. A `.env` file in the working directory
is read (`KEY=VALUE` lines). `OLLAMA_TIMEOUT` (seconds, default 120) bounds each model call; a
stalled call counts as a failed attempt.

## Run

    uv run tpg generate standard.pdf --out plan.json
    uv run tpg generate standard.pdf --out plan.yaml --format yaml --model gemma4:31b --clauses 5.1,5.2 --attempts N
    uv run tpg generate standard.pdf --out plan.json --no-model     # no model stage: deterministic objects only
    uv run tpg generate standard.pdf --out plan.json --no-grammar   # no objects from formal declarations
    uv run tpg generate standard.pdf --out plan.json --no-deflate   # keep every coverage item
    uv run tpg generate standard.pdf --out plan.json --no-batch     # one model call per coverage item

Cost: generation makes one LLM call per source (a requirement or an object) carrying up to eight of
its coverage items, plus one call per clause chunk for requirements and one for objects. Use
`--clauses` to scope a run and `--no-model` for the cheaper sentence-level plan.

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
- ICS coverage is a necessary condition, not a sufficient one, and it is computed over the features
  the tool itself read out of the document: a feature the ingest or the extract stage never saw is
  absent from the denominator as well as from the suite.
- Batching groups coverage items by their source, so the call reduction depends on how many items a
  source has. Measured on the coverage item distribution of a full run over a 265-clause standard,
  1320 of 1611 sources carried only one or two items, so the batch of eight is rarely full and the
  reduction is about twofold (1612 calls against 3257), not the eightfold the limit suggests. For
  object-derived items alone, which come in ladders of five to eight, the measured ratio is 4.8.
  Batching several small sources of one clause into one call would go further and is not implemented:
  the design keeps one test purpose per case, which that would weaken.
- Deflation is deliberately conservative: a group needs identical declared obligations, so one
  structure declared with a different type or presence at two sites keeps two ladders, and a
  requirement duplicating an object it does not quote keeps its items. `--no-deflate` measures the
  whole of what the two rules remove.

## Tests

    uv run pytest                                         # fast, no network
    TPG_E2E=1 OLLAMA_HOST=https://ollama.com uv run pytest -m slow -v   # real model, real documents
