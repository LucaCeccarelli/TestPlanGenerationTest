# Conformance Methodology Iteration — Design Spec

Date: 2026-10-12
Status: approved in discussion, implementation pending
Builds on: `2026-09-21-test-plan-generator-design.md` (base) and `2026-09-21-test-model-design.md`
(the test model stage). Supersedes their §4.4 derivation table and §3 data model where they conflict.
Research behind it: `reports/Conformance test coverage mechanisms.md` and the five note files in
`research_notes/Conformance test coverage mechanisms/`.

## 1. Why

Measured on ISO/IEC DIS 18013-5 against the official suite ISO/IEC TS 18013-6:2025, the tool covers
13.8 % of the 687 clause-citing official test cases. The research settled three things:

1. **The target metric was wrong.** 85 to 90 % is unattainable on strict per-case matching; the
   highest figure anyone has published against a human suite is 0.84 under a permissive similarity
   matcher on 90 reference cases [R45]. The metric this genre actually uses is coverage of the
   conformance requirements, which ISO/IEC 9646-2 (= ITU-T X.291) clause 10.3.5 states as "at least
   one test purpose related to each distinct conformance requirement" [R46], and which ETSI's test
   purpose style guide states as "any mandatory or optional item of the ICS is covered by at least a
   TP" [R47]. That is a criterion the generator can satisfy by construction and audit itself.
2. **The tool over-generates.** 3231 cases for 842 requirements is 3.84 per requirement. ETSI's own
   IPv6 project produced 356 conformance tests from 1112 catalogued requirements, 0.32 per
   requirement [R48], and ETS 300 406 wrote in 1995 that "the formal and automatic derivation of
   tests generally leads to a huge number of tests without interest" [R49]. More enumeration on the
   axes already present is not the lever; Pretschner et al. measured a sixfold increase in
   model-based tests buying 11 % more detected errors [R50].
3. **44 % of the official suite is out of reach of the current ladder.** 257 type or encoding checks
   belong to syntax testing and 44 behaviour checks to state transition and scenario testing, two of
   the twelve specification-based techniques ISO/IEC/IEEE 29119-4 defines and this tool does not
   implement [R51]. The ceiling at perfect execution of the present design is about 56 %.

## 2. Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D21 | A new deterministic stage emits an **ICS proforma**: one `ICSItem` per feature the standard declares, with a status of mandatory, optional or conditional, derived from an object's `presence` or a requirement's `modality`. One `capability` coverage item is then emitted per mandatory or optional item | ETR 266 Guidance 5 and X.291 clause 10.4's first rule make this the genre's coverage criterion [R46,R47]. It is also the only coverage metric that needs no official suite, which is what makes the tool measurable on standards that have none |
| D22 | Requirements and objects carry `applies_when: list[str]`, a list of verbatim applicability conditions extracted from the clause; coverage items inherit it and generated cases state it | 595 of the 907 official cases are gated by a Profile precondition and all carry a Technology tag; X.291 clause 10.3 and TDL's `PICSReference` make applicability part of a test purpose [R46,R52]. Stored as text, never as a controlled vocabulary, so no document family leaks in |
| D23 | Coverage items gain a **test group** from X.291 clause 10.2.2: `capability`, `valid_behaviour`, `invalid_behaviour`, `inopportune_behaviour`. Two new checks: `capability` (per ICS item) and `inopportune` (a valid message or structure supplied when its stated precondition does not hold) | The 9646-2 test suite structure. `inopportune` is the one group the tool had no analogue for, and it is derivable without further LLM work |
| D24 | A new deterministic **grammar stage** harvests formal declarations from clause text and emits objects from them: CDDL, ABNF, JSON Schema and the common ASN.1 `SEQUENCE`/`CHOICE` shape. Detection is a signature match per notation; each handler's parser is the acceptance gate, so detection may be permissive. Objects gain `origin: prose | grammar` | 257 of the official tests are encoding checks over structures the standard declares formally. ParCleanse reaches 99/95 on field names and 94/91 on field types with a typed field graph as its target [R53]; AUTOSPEC, which targets a grammar instead, reaches 16.7 % on independent constraints [R54], so the field graph is the right normal form and the tool already has it. Emitting objects means nothing downstream changes |
| D25 | **Deflation**, two rules. (a) Objects that recur in several clauses **with the same obligations** form a **generic group**, keyed on the normalised name together with every attribute that determines the group's test purposes: kind, presence, direction, type, value domain and size. The occurrence with the most coverage items owns them, ties broken by document order; every other site gets a single `reference` item naming the group. Occurrences sharing a name but differing on any keyed attribute are distinct declarations and each keeps its own ladder. (b) A requirement-derived item is dropped when an object of the same clause was derived from **the same prose**, which is decided by comparing the object's `source_quote` with the requirement's `text`, not by looking for the object's name inside it | X.291 clause 11 and Annex D define generic test suites, and the official suite uses them in the 27 cases that say "perform all Common_X test cases" [R46]. Without this the tool regenerates a shared structure once per use site, which is most of the 12-fold inflation. The keying and the provenance test are amendments forced by review, see D31 |
| D26 | Generation is **batched per source**: one LLM call per requirement or object carrying up to 8 of its coverage items, the reply keyed by coverage item id, valid cases accepted and only the failures re-prompted | 3257 calls at 10.7 s is 12.7 hours. Batching by source also makes the preconditions of one object's cases consistent, which is how the official suite achieves 112 distinct precondition blocks across 907 cases. Per-item generation currently scores 56 of 60 grounded, so the batch keeps per-item purposes rather than templating prose, which would risk that |
| D27 | The evaluation reports **three denominators** (all 907, the 687 citing a clause, and the subset whose cited clause id exists in the input edition), a **judge-free structural matcher** on (data item, check type) beside the LLM judge, **ICS coverage** as the suite-independent headline, and macro averages over clauses and families | The judge is the same model family as the generator, which inflates [R55]; a structural matcher removes that from the headline. Reporting the in-edition subset separates a real miss from a requirement absent from the input |
| D28 | Robustness, carried over from the last evaluation: the chunk limit drops to 3000 characters, a truncated reply yields its complete elements instead of nothing, and the ingest counts table rows per clause so the model stage can be re-prompted for the rows it did not return | 12 of 16 model-stage gaps were truncated replies on the largest prompts, and 361 table rows produced 4 objects. ParCleanse's ablation attributes 24 to 37 points of recall to dividing the document before prompting [R53] |
| D30 | **Direction selects the wording of a negative coverage item, never its existence.** The invalid-side items (`absence` of a mandatory element, `encoding_invalid`, `value_invalid`, `boundary_outside`) are emitted for every object. For a received object the purpose asks that an invalid instance be supplied and rejected; for a produced or internal object it asks that the implementation never produce or hold an invalid instance | Amendment forced by measurement. Gating those items on `direction == "received"` suppressed the entire invalid half of the ladder for all 83 grammar-derived objects of the ISO fixture: 250 coverage items with zero `encoding_invalid`, zero `value_invalid`, zero `boundary_outside` and zero negative `absence`. Grammar objects have no prose author to state a direction and the model prompt deliberately does not ask for one again, so the gate could never be satisfied. ISO/IEC/IEEE 29119-4 clause 5.2.4 syntax testing applies to an encoder and a decoder alike: one must not emit an invalid encoding, the other must reject it. Both are test purposes, so the obligation is to word them differently, not to drop one |
| D31 | **A generic group is a shared specification, not a shared name, and an overlap is shared provenance, not a shared word.** Amendment to D25, forced by review | Keying D25 rule (a) on the bare name collapsed occurrences carrying different obligations: on the real fixture 6 of 18 reference sites were mandatory ICS entries whose only coverage item pointed at an optional ladder, and 16 of 18 declared a different type than the owner, while the evaluation counted all 18 as covered. X.291 clause 11 grants a generic test suite because the *same* specification is referenced from many places, so two declarations that differ in presence or type are not one structure. Rule (b) keyed on the object's name occurring in the requirement's text, which deletes a real test purpose whenever a name happens to appear: an object `nonce` constrained by size suppressed a requirement stating a 500 ms timing limit, and a three-character name such as `set` matches ordinary English. Both rules were mine; the implementation followed the brief exactly |
| D32 | **Recorded limitation, not reopened: D30's two wordings are not epistemically symmetric.** The received wording, supply an invalid instance and observe rejection, is a finitely executable test purpose. The produced or internal wording, the implementation never produces or holds an invalid instance, is a universal claim that no finite test can verify, only falsify. It is kept because an obligation on an encoder is real and X.291 clause 10.2.2 places it in invalid behaviour, and because dropping it would suppress the whole invalid half for the 83 per cent of objects that are produced or internal, which is the defect D30 itself was raised to fix | Noted so the article states it as a known limit of the method rather than an oversight. The practical consequence is that a produced-side invalid item is tested in practice by observing the implementation's own output and checking it conforms, which partly overlaps the `encoding_valid` item of the same object. Resolving it properly needs a notion of a sampled conformance check that the coverage-item model does not carry |
| D29 | Recorded deviations, deliberately not implemented: the ICS factoring rule of ETS 300 406 Annex A.2 (one question for a structure whose members all share its status), the two-stage combination deflation of X.291 clause 10.3.3, and human calibration of the judge | Each needs either a parent/child relation the object model does not carry, or human labelling effort. Named here so the article can state them as known gaps rather than oversights |

## 3. Data model changes

```
Origin   = prose | grammar
Status   = mandatory | optional | conditional | unspecified
Group    = capability | valid_behaviour | invalid_behaviour | inopportune_behaviour

RequirementDraft + applies_when: list[str] = []
TestObjectDraft  + applies_when: list[str] = []
TestObject       + origin: Origin = "prose"

ICSItem
  id: str            # "ICS-<source id>"
  source_id: str     # the requirement or object it came from
  clause_id: str
  feature: str       # what the implementation may or must support
  status: Status
  condition: str | null
  applies_when: list[str]

CoverageItem
  + group: Group
  + applies_when: list[str]
  + generic_group: str | null   # set on a `reference` item, naming the owning group
  check gains: capability | inopportune | reference

TestPlan + ics: list[ICSItem]
```

`Check` gains three values; `Kind` is unchanged, with `capability` and `reference` items being
`nominal` and `inopportune` being `negative`.

## 4. Stage changes

### 4.1 Ingest
`Clause` gains `row_count: int`, the number of row-record lines, so the model stage can check it got
one object per row. `CHUNK_LIMIT` becomes 3000.

### 4.2 Grammar (new, `tpg/grammar.py`, no LLM)
`harvest(clause) -> list[TestObjectDraft]`. Per notation a detector and a parser:

- **CDDL**: a block matching `^\s*[A-Za-z][\w-]*\s*=\s*[({]`. Members `key: type`, `? key` optional,
  `* key` repeated, `.size`, `.default`, ranges. One object per member with `presence`, `type`, `size`.
- **ABNF**: `rulename = elements` with `/`, `[...]`, `*`. One object per rule, `type` the element
  list; optional groups give `presence: optional`.
- **JSON Schema**: a block parsing as JSON with a `properties` key. Walk `properties`, `required`,
  `type`, `enum`, `minimum`, `maximum`, `minLength`, `maxLength`.
- **ASN.1**: `Name ::= SEQUENCE {` or `CHOICE {`, members `field Type` with `OPTIONAL`, `DEFAULT`,
  `SIZE(a..b)`, named value lists.

Every object carries `origin="grammar"` and a `source_quote` that is the verbatim declaration line,
so the existing grounding check still applies. The stage runs before the LLM model stage; objects
whose name a grammar already produced are not asked of the LLM again.

### 4.3 Model (LLM)
Prompt gains `applies_when`. After the stage, when `clause.row_count` exceeds the number of objects
whose quote is a row record, the clause is re-prompted for the missing rows only, up to the retry
budget, and the residue is recorded as a gap naming the count.

### 4.4 ICS (new, `tpg/ics.py`, no LLM)
`build_ics(requirements, objects) -> list[ICSItem]`. Status mapping: object presence maps straight
through; requirement modality maps shall and shall_not to mandatory, should and should_not and may to
optional. Features with an empty name are skipped.

### 4.5 Derive
Adds, in order: one `capability` item per mandatory or optional ICS item; the existing ladder for
objects and requirements, each item now carrying `group` and `applies_when`; one `inopportune` item
per received object of kind message or structure that has a condition or any precondition text; then
the two deflation rules of D25 as amended by D31. Per D30 the invalid-side items are emitted for
every object and `direction` selects their wording.

Deflation never leaves a mandatory or optional ICS item without a coverage item that asserts its own
obligations, which is the D21 guarantee and is checked by a fast test, not only by the slow
end-to-end suite. A `reference` item satisfies that guarantee only for a site whose obligations are
identical to the owner's, which is what the D31 keying ensures.

### 4.6 Generate
One call per source with up to 8 items. The reply is a list keyed by `coverage_item_id`; unknown or
duplicate ids are failures; each case is checked by the existing rules; only failing ids are
re-prompted. `--no-batch` keeps the per-item path for comparison.

### 4.7 Emit
`ics` is written between `objects` and `coverage_items`. Traceability is unchanged.

## 5. CLI

`--no-model`, `--no-grammar`, `--no-batch`, `--no-deflate` each disable one stage or rule, so the
contribution of each can be measured separately. Exit codes unchanged.

## 6. Testing

Unit tests per new module with the existing `FakeLLM`; `tpg/grammar.py` and `tpg/ics.py` and the new
derive rules are deterministic and get table-driven tests. The sample fixture gains one small block
of each of the four notations so the grammar stage is exercised in the fast suite. The slow suite
asserts that every ICS item of status mandatory or optional has at least one coverage item.

## 7. Evaluation

`tools/eval/` gains the three denominators, a structural matcher on (data item, check type) parsed by
rule from each official test's Purpose text, ICS coverage, and macro averages. The LLM judge stays
but is reported beside the structural matcher, never alone.

## 8. References added

- [R45] Masuda et al., recall against a human high-level test suite, arXiv:2510.03641, 2025.
- [R46] ITU-T X.291 (04/1995) = ISO/IEC 9646-2, clauses 10.2 to 10.4 and 11, Annex D.
- [R47] ETSI ETR 266 (1996), Test Purpose style guide, Guidance 5.
- [R48] ETSI IPv6 testing project figures, ITU-T workshop, December 2006.
- [R49] ETSI ETS 300 406 (1995), clause 7.4.1 and Annex A and D.
- [R50] Pretschner et al., ICSE 2005, model-based testing effectiveness.
- [R51] ISO/IEC/IEEE 29119-4:2021, clauses 5.2.1 to 5.2.12 and 6.2.x.
- [R52] ETSI ES 203 119-4 (2022), TDL Structured Test Objectives; ES 202 553, TPLan.
- [R53] ParCleanse, ISSTA 2025, arXiv:2504.18050, 10.1145/3728955.
- [R54] AUTOSPEC, arXiv:2511.17977, 2025.
- [R55] Wataoka et al., self-preference in LLM judges, NeurIPS 2024; ISSTA 2025 meta-evaluation,
  arXiv:2502.06193.
