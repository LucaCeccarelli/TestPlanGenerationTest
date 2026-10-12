# Article outline: from an agentic RAG pipeline to a deterministic test-model generator

Working notes, not prose. Four sections, each with what changed, why, the sources behind the
decision, and the numbers. Sources are tagged `[Sn]` and listed at the end.

---

## 1. Initial state

**What it was.** Three decoupled axes over ISO/IEC DIS 18013-5, producing an ISO/IEC/IEEE 29119-3
JSON test plan. Axis A extraction and indexing, Axis B a three-agent generation chain, Axis C an
LLM auditor.

- Stack: `pdfplumber`, spaCy, `RecursiveCharacterTextSplitter`, `OllamaEmbeddings` + FAISS,
  `ChatOllama` (llama3.2, `num_ctx=4096`), `deepagents`, pydantic, `guardrails-ai`, BERTScore.
- Axis B chain: Analyst, then RAG Router, then Designer. One pass per normative chunk, no shared
  state. Axis C: structural guardrails plus an Auditor agent whose verdict is overridden by a
  deterministic Python rule.
- Research gap claimed, and still valid: the literature derives test cases from user stories, SRS
  documents or existing source code; nothing generates a 29119-3 plan from a normative standard
  upstream of any implementation.

**Baseline metrics.**

| | |
|---|---|
| Source files / lines | 28 / 2,678 |
| Tests | 23, all external calls mocked |
| Chunks produced | 843, then 1,175, then 1,202 across runs; 466 normative in the indexed run |
| FAISS index | 3.5 MB plus 583 KB docstore |
| Test plans produced | **0** (no Ollama runtime during the documented runs) |

**Nine known limitations** recorded at the time: flat single-pass chunking that splits clauses,
dense-only retrieval, no cross-reference or defined-term awareness, independent per-chunk
generation, non-reflective retry, no generation-time quality gate, LLM-only hallucination
detection, a manual adversarial protocol, and no ground truth for Axis A.

**Framing for the article.** The baseline is a conventional 2024-style agentic RAG design: embed
everything, retrieve, let agents reason. Every later decision is a reaction to measuring it.

---

## 2. First iteration: nine improvements from the state of the art

Nine propositions, each written as gap, evidence, concrete change. Eight search queries across
arXiv, Semantic Scholar and CrossRef; 25 references.

| # | Change | Why, from the literature |
|---|---|---|
| A1 | Structure-aware two-pass chunking | clause-atomicity; semantic and adaptive chunking `[S13-S16]` |
| A2 | Hybrid dense plus sparse retrieval, BM25 and RRF | Blended RAG `[S7]`, FAIR-RAG `[S8]` |
| A3 | Cross-reference resolution, defined-terms injection | AgenticIE on regulatory documents `[S12]` |
| B1 | Planner agent for deduplication and feature-set skeleton | multi-agent LLM testing `[S18-S20]` |
| B2 | Schema-constrained generation with error-reflective retry | LLM test generation from SRS `[S2,S3]`, APITestGenie `[S25]` |
| B3 | BERTScore self-evaluation gate | hallucination detection `[S9-S11]` |
| C1 | Embedding-distance pre-audit | probabilistic-distance hallucination detection `[S10]` |
| C2 | Adversarial protocol as a reproducible pytest suite | reproducibility of the detection-rate metric |
| X | TraceLLM-style traceability enrichment | TraceLLM `[S6]`, NLP for traceability `[S22]` |

All nine were implemented. **This is the part of the story that matters: implementing the state of
the art on an unmeasured foundation produced no measurable gain.**

---

## 3. The measured diagnosis that forced a rebuild

A second review started from measurement instead of literature. One defect disabled four of the
nine improvements, silently.

| Measurement, 1,202-chunk run | Value | Consequence |
|---|---|---|
| Distinct section labels | 25 | a 126-page standard with about 200 headings |
| Chunks labelled `1.2.840.10045.4.3.4` | 645 (54 %) | the heading regex matches ASN.1 OIDs in annexes |
| Chunks labelled `8.1.2.2` | 327 (27 %) | no heading detected for 40 pages |
| Normative chunks that are a full clause | **1 / 466** | A1 inactive |
| Chunks with defined terms | **0 / 1,202** | A3 inactive |
| Cross-references resolved | 22, all pointing at OIDs | A3 inactive |
| Planner clusters | 5, named `Section_810` | B1 meaningless |
| `tc_id` uniqueness | collisions | traceability broken |
| `deepagents` wrapper | +1,900 tokens, 8 stray tools | harmful |
| BERTScore gate | never ran | needs a model download |

**Extraction back-ends compared on three standards** (ISO DIS 18013-5, RFC 8949, OpenID4VP 1.0):

| Back-end | ISO headings | Ligatures | Outline and font data | Time |
|---|---|---|---|---|
| pdfplumber (current) | 0.89 with a tolerant regex, 28 % padding | broken | no | 60 s |
| MarkItDown | **0 headings**, plain text | broken | no | 47 s |
| PyMuPDF | 47/47 bookmark entries | **intact** | yes | **5 s** |

Conclusion drawn, and the article's hinge: a Markdown converter is only as good as the structure it
can infer, and for born-digital PDFs that structure must come from bookmarks, font size and line
geometry `[S27,S28]`; model-based converters `[S23-S26]` win only on scanned or complex layouts.

**Why rebuild rather than patch.** Two independent reasons:

1. The sophistication was inert. Retrieval, agents and gates sat on top of a document model that
   did not know where clauses began.
2. The target's shape was wrong. The official conformance suite for this standard is an enumeration
   of objects times a fixed check ladder, not one test per prose chunk. Per-chunk generation cannot
   reach that granularity however good the agents are.

---

## 4. The radical change: a deterministic pipeline with an explicit test model

**New design, four stages, no framework, no vector store, no agents.**

```
ingest (rule-based, layout only)
  -> extract requirements (regex candidates, then one LLM call per clause chunk)
  -> extract objects: the test model (one LLM call per clause chunk)
  -> derive coverage items (deterministic, no LLM)
  -> generate one test case per coverage item
  -> rule-based verification, bounded retry, explicit gaps
```

**Where each decision came from.**

| Decision | Source |
|---|---|
| An explicit intermediate model, then derive tests from it without further LLM reasoning | AUTOSPEC `[S30]`: protocol elements to an I/O grammar, 92.8 % client message types recovered on five RFCs |
| A domain meta-model plus testability constraints injected into generation | RAFT `[S31]` |
| Systematic enumeration by the tool, LLM writes only the prose | iPanda `[S21]`, 4.7 to 10.8 times better pass@1 than a pure-LLM baseline |
| Hierarchical document understanding before generation | NeTestLLM `[S32]`, 4,632 tests, 41 historical bugs versus 11 for the national suite |
| Test model, coverage items, equivalence partitioning, boundary analysis as the naming and the ladder | ISO/IEC/IEEE 29119-4 `[S29]` |
| A fixed pipeline instead of autonomous agents | Agentless `[S33]`: a three-phase pipeline beat every open-source agent on SWE-bench Lite at a fraction of the cost |
| Small models are weak tool users, so no tool-calling control flow | `[S34]` |
| Rule-based verification stage rather than an LLM critic | RAITG `[S35]`: verification raised the pass rate from 73.9 % to 95.9 %; reviewer-capability study `[S36]`: same-model self-review gave no gain and 35 % false rejections |
| Annotation then conversion for extraction, with a verbatim quote per requirement | Li et al. `[S37]`: +29.2 % correctly extracted specifications, and the two failure modes are oversimplification and fabrication |
| Minimal condition-combination set for conditional requirements | CiRA `[S9]` |
| Three-attempt retry budget, one requirement per prompt | APITestGenie `[S25]` |
| Table rows as requirement units | the V2 proposition, plus table-representation studies on 3GPP specifications `[S38]` and layout-aware tabular extraction `[S39]` |
| PyMuPDF as the extraction back-end | the measurement above, plus the parser comparison `[S27]` |

**What the tool deliberately does not do:** no embeddings, no retrieval, no agent framework, no
executable test code, no plan-level prose. Every rule is about layout, numbering, typography or
generic English, never about a document family.

**Intermediate result, sentence-level only, before the test model existed:**

| | |
|---|---|
| Requirements / test cases | 215 / 428 |
| Coverage of the official suite | 29 of 687 = **4.2 %** |
| Generated cases grounded / actionable / correct, of 60 | 52 / 50 / 51 |

Diagnosis of that 4.2 %: whole-batch rejection at extraction discarded about 200 drafts including
the most-tested clauses, the ingest lost half the clause structure on this document, and the
granularity mismatch remained.

---

## 5. Latest upgrades and results

**The ground truth.** The three appendices of ISO/IEC TS 18013-6:2025 parsed by rule into
structured test cases: **907** official test cases, **687** citing an 18013-5 clause, across 54
distinct clauses and 118 test families, 7.7 tests per family. Their check distribution is the
evidence for the coverage ladder:

| Check the official test performs | Count |
|---|---|
| presence or absence | 455 |
| type or encoding well-formedness | 257 |
| value domain | 97 |
| behaviour or protocol flow | 44 |
| size or boundary | 8 |

**Upgrades in this iteration.**

- Ingest: table rows kept as `Header: cell | Header: cell` records; repeated page furniture removed
  by recurrence; heading plausibility by numbering sequence; annex and appendix markers.
  Clauses recovered 117 to **265**; largest clause 122 KB to **16 KB**.
- Extraction: per-draft acceptance instead of whole-batch rejection; `should_not` added; long
  clauses chunked.
- New stages: the test model, and deterministic coverage-item derivation.
- Generation: one call per coverage item; the tool sets the kind, never the model.
- Vocabulary leniency: strict enums in a batch schema meant one bad value rejected an entire reply.
  Relevant literature on constrained decoding and schema wording `[S40-S42]`. The emitted JSON
  schema still advertises the vocabulary, so a server that enforces it still constrains generation.
- Operational: a request timeout, after one run hung for over 90 minutes on a single call.

**Measured, same model (`gemma4:31b`), local Ollama, 12.7 h, about 10.7 s per call:**

| | before | after | change |
|---|---|---|---|
| Requirements | 215 | 842 | 3.9x |
| Objects in the test model | 0 | 921 | new |
| Coverage items | 0 | 3,257 | new |
| Test cases | 428 | 3,231 | 7.5x |
| Items that produced a case | n/a | 3,231 of 3,257 (99.2 %) | |
| Gaps | 14 | 66 | |
| **Coverage of the official suite** | **4.2 %** | **13.8 %** | **3.3x** |
| Grounded / actionable / correct, of 60 | 52 / 50 / 51 | 56 / 50 / 54 | |

Per-clause, best is 25.4 % on the device-engagement clause; the clauses that scored zero before now
score 12 to 14 %.

**What still limits it, measured not guessed.**

- Twelve of sixteen model-stage gaps are a truncated reply, three attempts each, on the largest
  prompts. Clean clauses have a median largest chunk of 826 characters; nine of the twelve failures
  exceed 6,000. Those twelve clauses hold **361 table rows and produced 4 objects**, and they are
  the data-element table and the certificate-profile tables, exactly where the official suite
  concentrates. Fix: a smaller chunk limit for the model stage, and confirm the server context.
- Actionability did not improve, 50 of 60, and is now the quality ceiling: vague steps, not wrong
  tests.
- The fixture is the 2020 draft; the official tests cite the 2021 edition. A confound to state.

**Engineering analytics worth a line.** Tests 23 mocked to **134** with a fake only at the model
boundary; dependencies from LangChain, FAISS, deepagents, guardrails, BERTScore down to five
(`pydantic`, `ollama`, `pymupdf`, `python-docx`, `pyyaml`).

---

## Sources

Reuse the numbering from the two review documents where possible.

- `[S2]` Krishna et al., LLMs in SRS, arXiv:2404.17842. `[S3]` Korraprolu et al., ISEC 2025,
  10.1145/3717383.3717389. `[S6]` Alturayeif et al., TraceLLM, arXiv:2602.01253.
  `[S7]` Sawarkar et al., Blended RAG, MIPR 2024. `[S8]` FAIR-RAG, arXiv:2510.22344.
  `[S9]` Frattini et al., CiRA, REW 2023, 10.1109/REW57809.2023.00019.
  `[S10]` Oblovatny et al., arXiv:2506.09886. `[S11]` Sun et al., AAAI 2026, arXiv:2603.22812.
  `[S12]` Colakoglu et al., AgenticIE, arXiv:2509.11773. `[S13-S16]` adaptive, max-min and
  LumberChunker chunking. `[S18-S20]` AutoMT, multi-agent committees, ALMAS.
  `[S21]` Sun et al., iPanda, arXiv:2507.00378. `[S22]` Guo et al., arXiv:2405.10845.
  `[S23-S26]` Docling, MinerU, OmniDocBench. `[S25]` APITestGenie, arXiv:2409.03838.
  `[S27]` Adhikari and Agarwal, arXiv:2410.09871. `[S28]` MinerU-Popo, arXiv:2605.24973.
- New in this project: `[S29]` ISO/IEC/IEEE 29119-4:2021. `[S30]` AUTOSPEC, arXiv:2511.17977.
  `[S31]` RAFT, arXiv:2601.09762. `[S32]` NeTestLLM, arXiv:2510.13248.
  `[S33]` Agentless, ACM TOSEM 2025, 10.1145/3715754. `[S34]` Shen et al., arXiv:2401.07324.
  `[S35]` RAITG, 10.21203/rs.3.rs-10060668/v1. `[S36]` Tanveer, arXiv:2609.04270.
  `[S37]` Li et al., arXiv:2504.01294. `[S38]` Roychowdhury et al., 3GPP table representations.
  `[S39]` Al Hilmi et al., layout-aware tabular extraction. `[S40]` Lu et al., arXiv:2502.18878.
  `[S41]` Matveev, arXiv:2603.03306. `[S42]` Le, arXiv:2604.14862.
  `[S43]` ISO/IEC/IEEE 29119-3:2021. `[S44]` ISO/IEC TS 18013-6:2025, the ground truth.

**Caveat for the methods section.** The paper-search MCP server stopped returning results partway
through; `[S29-S37]` were located by web search and read from arXiv. Coverage and precision are
judged by the same model family that generates, which is a known bias `[S19,S20]` and should be
stated as a limitation.

---

## 6. Sixth iteration: adopting the conformance-testing methodology

The 13.8 per cent prompted a literature search aimed specifically at the genre of the official
suite. It changed the target, not just the implementation. Sources added here are `[S45-S55]`.

### 6.1 What we discovered

**The suite is not an ad-hoc document; it is a standard artefact with a standard derivation.** The
three appendices of ISO/IEC TS 18013-6 are a Test Suite Structure and Test Purposes document in the
ISO/IEC 9646-2 tradition, whose free twin is ITU-T X.291 (1995). Measured evidence for the match:
nine labelled fields per case, which map field for field onto ETSI ETR 266's test purpose template
and onto TPLan's `with { } ensure that { when { } then { } }`; applicability by Technology tag and
Profile precondition, present in 595 of 907 cases; identifiers encoding system under test, area,
object and index; 118 families averaging 7.7 cases; 112 distinct precondition blocks, the commonest
shared by 154 cases; and 27 cases that say "perform all Common_X test cases", which X.291 clause 11
and Annex D define as generic test suites.

**The metric we were optimising was the wrong one.** `[S45]` is the only published system reporting
recall against a human-written test suite: 0.84, but with a cosine-similarity matcher at threshold
0.7, on 90 reference cases, with precision 0.60, and 0.37 on its sister dataset. Strict per-case
recall of 85 to 90 per cent has never been reported by anyone. What the genre itself measures is
requirement coverage, and two normative sources state the rule:
- X.291 clause 10.3.5: "at least one test purpose related to each distinct conformance requirement".
- ETR 266 Guidance 5: "any mandatory or optional item of the ICS is covered by at least a TP".

**We were over-generating, not under-generating.** 3231 cases for 842 requirements is 3.84 per
requirement. ETSI's own IPv6 project produced 356 conformance tests from 1112 catalogued
requirements, 0.32 per requirement `[S48]`, with the norm that "a test suite should never exceed a
few hundreds of tests". ETS 300 406 wrote in 1995 that "the formal and automatic derivation of tests
generally leads to a huge number of tests without interest" `[S49]`, and that "the coverage by the
TPs is never absolute nor complete, and no method exists to objectively evaluate it". Pretschner et
al. measured a sixfold increase in model-based tests buying 11 per cent more detected errors
`[S50]`.

**Forty-four per cent of the suite was out of reach by construction.** ISO/IEC/IEEE 29119-4 defines
twelve specification-based techniques; the tool implemented two. The 257 encoding checks belong to
syntax testing, clause 5.2.4, and the 44 behaviour checks to state transition and scenario testing,
5.2.8 and 5.2.9. Ceiling at perfect execution of the old ladder: about 56 per cent.

**Recall, not prose, is the bottleneck, and there is a published ceiling.** ParCleanse `[S53]`
reaches 99/95 on field names and 94/91 on field types over nine RFC protocols, and its ablation
attributes 24 to 37 points of recall to dividing the document before prompting. Its dependent
constraints still sit at 44 per cent even with a frontier model, which says cross-field conditions
should be recorded as gaps rather than chased. AUTOSPEC `[S54]`, which targets a grammar instead of
a typed field graph, reaches 16.7 per cent on independent constraints, which is the argument for
keeping our object model as the normal form.

**Several things nobody has published**, which is where the contribution lies: no generation of a
TSS&TP or an ICS proforma from prose; no definition of test-purpose equivalence and no suite-to-suite
matching method; no completeness audit of any real conformance suite against its own standard, which
X.291 and ETS 300 406 both say is impossible for want of a metric; no per-row extraction accuracy on
any standard's data-element table; nothing on specification-edition mismatch between an input and a
reference suite; no covering arrays over conformance applicability predicates.

### 6.2 The specification of this iteration

Nine decisions, D21 to D29, in
`docs/superpowers/specs/2026-10-12-conformance-methodology-design.md`. New pipeline:

```
ingest  ->  grammar (deterministic objects from declarations)
        ->  extract requirements (LLM)  ->  model (LLM objects)
        ->  ics (deterministic proforma)
        ->  derive (coverage items, test groups, deflation)
        ->  generate (batched per source)  ->  verify  ->  emit
```

| # | Decision | What it adds |
|---|---|---|
| D21 | An **ICS proforma**: one item per declared feature with a status of mandatory, optional or conditional, derived from an object's presence or a requirement's modality; one `capability` coverage item per mandatory or optional item | the genre's coverage criterion, satisfied by construction and auditable without an official suite |
| D22 | **Applicability predicates** `applies_when`, verbatim text on requirements and objects, inherited by coverage items and stated in the case | the Technology and Profile axis, 595 of 907 official cases |
| D23 | The four **test groups** of X.291 clause 10.2.2: capability, valid behaviour, invalid behaviour, inopportune behaviour, with two new checks `capability` and `inopportune` | the group the tool had no analogue for |
| D24 | A **grammar stage**, deterministic, harvesting CDDL, ABNF, JSON Schema and ASN.1 declarations into objects with `origin: grammar` | the 257 encoding checks; nothing downstream changes because it emits the existing object type |
| D25 | **Deflation**: drop a requirement item when an object already yields the same check, and make a recurring structure a **generic group** owned once with a `reference` item at every other site | X.291 clause 11; intended to remove most of the twelvefold inflation, and measured at 1.4 per cent once the rule was made sound, see 6.4 |
| D26 | **Generation batched per source**, up to 8 items per call, keyed by coverage item id, retrying only the failures | 12.7 hours towards about 3, and consistent preconditions per object |
| D27 | Evaluation with **three denominators**, a **judge-free structural matcher** on data item plus check type, **ICS coverage** as a soundness invariant, and macro averages | removes the same-family judge from the headline number. ICS coverage turned out to be satisfied by construction, so it is an invariant rather than a score, see 6.4 |
| D28 | Chunk limit 3000, salvage of a truncated reply's complete elements, and **row accounting**: the ingest counts table rows so the model stage can be re-prompted for the rows it did not return | the 361 rows that produced 4 objects |
| D29 | Recorded as deliberately **not** done: the ICS factoring rule of ETS 300 406 Annex A.2, the two-stage combination deflation of X.291 clause 10.3.3, human calibration of the judge | honest gaps, each needing data the model does not carry or human labelling |
| D30 | **Direction selects the wording of a negative coverage item, never its existence.** The invalid-side items are emitted for every object; for a received object the purpose asks that an invalid instance be supplied and rejected, for a produced or internal one that the implementation never produce or hold it | an amendment forced by measurement, see 6.4 |
| D31 | A **generic group is a shared specification, not a shared name**, keyed on every attribute that determines its test purposes; an **overlap is shared provenance**, not a shared word | amendment forced by review; the name-keyed version asserted purposes the owning ladder did not contain, and the word-keyed version deleted genuine test purposes |

### 6.3 The choices, and what was rejected

- **Keep the 29119-3 plan as the output, use 9646-2 as the backbone.** The proforma and the group
  structure drive generation; the deliverable format does not change. Nothing is lost and the
  methodology is gained.
- **The field graph stays the normal form, not a grammar.** ParCleanse against AUTOSPEC is a fivefold
  difference in constraint recall and the difference is the target representation `[S53,S54]`.
- **The grammar stage emits objects, not tests.** One handler per notation, dispatched on that
  notation's own syntax, with the handler's parser as the acceptance gate so detection can be
  permissive. Keeps the tool generic: RFCs bring ABNF, OpenID brings JSON Schema, 3GPP brings ASN.1,
  and an ISO table brings nothing, which is exactly where the row accounting of D28 carries the load.
- **Batch per source, do not template the prose.** The research supports collapsing 3231 artefacts to
  roughly 100 to 250 patterns, but per-item generation currently scores 56 of 60 grounded, so the
  batch keeps per-item purposes and takes the cost win without risking the quality that is measured.
- **Rejected: more enumeration.** We are twelve times denser than ETSI's own pipeline and a 1995
  standard predicted the outcome.
- **Rejected: an LLM critic for quality.** Same-family self-review is inert or harmful `[S36,S55]`;
  the rule-based verifier does the job.
- **Rejected: a vagueness word list** for the flat actionability score, for the same reason the
  negative-wording gate was already costing cases. Context, not policing.
- **Target restated honestly:** 85 to 90 per cent is attainable on ICS and requirement coverage, and
  is not attainable on strict per-case matching, where the realistic band is 35 to 60 per cent.

### 6.4 What building it changed: five findings forced by measurement

Each stage was probed on the real 126-page fixture as it was built, which is how the following were
found. They are the honest part of the story: a design that looked complete on paper lost reach to
defects only a count could reveal, and one of the defects we went looking for turned out not to
exist.

**The invalid half of the ladder was unreachable (amended as D30).** The specification gated the
negative coverage items on an object's `direction` being `received`. Measured on the fixture, that
gate produced 250 coverage items containing zero `encoding_invalid`, zero `value_invalid`, zero
`boundary_outside` and zero negative `absence`, for all 83 grammar-derived objects. Objects
harvested from a formal grammar have no prose author to state a direction, and the model prompt
deliberately does not ask for one twice, so the gate could never be satisfied. 29119-4 clause 5.2.4
applies to an encoder and a decoder alike: one must not emit an invalid encoding, the other must
reject it. Both are test purposes, so the obligation is to word them differently, not to drop one.
Removing the gate took the fixture from 281 items with no invalid side to 383 items with 62
`encoding_invalid` and 40 negative `absence`. This was a specification error, not an implementation
error, and it is recorded as one.

**The grammar stage was losing a third of what it harvested.** Probing the four handlers on the
fixture rather than on synthetic blocks found: a member sharing a line with its closing bracket was
dropped, losing 2 of the 4 real ASN.1 members; the ABNF detector fired on CDDL rule heads, typing 11
of 94 objects as a bracket; the merge collapsed same-named members of different structures, absorbing
11 of 94 and reducing one name declared with three distinct types to one; and CDDL comments leaked
into the type field of 35 of 94. Four defects, none of which a unit test on a well-formed block would
have shown.

**A suspected ingest ceiling turned out to be an edition difference, and finding that out mattered
more than a fix would have.** The harness measured that only 265 clause ids are ever segmented from
the whole standard, and that cited clauses carrying 184 official test cases were never among them:
`8.3.2.1.2.2` with 88 cases, `9.1.1.4` with 64, `8.3.2.1.2.3` with 32. The obvious reading was that
deeply nested headings were not being recognised, which would have capped coverage before any LLM
ran. It was wrong. An independent oracle, the document's own bold-text styling, cross-checked against
all 1516 bold lines, finds exactly 265 numbered headings, and ingest already produced exactly those
265, six numbering levels included. None of the three cited ids exists anywhere in the input, not
even as a cross-reference; their draft equivalents `8.2.1.1.2.2`, `9.2.1.4` and `8.2.1.1.2.3` were
all being read correctly all along. The input is the 2020 draft and the official suite cites the 2021
published edition, so this is the **edition mismatch asserting itself inside what looked like a
parser defect**. The methodological point is the one worth publishing: a coverage denominator built
from clause citations silently mixes a reading failure with an edition difference, and only an oracle
independent of the parser can separate them.

The same investigation did find a real defect, on a different document: a heading written as a number
and a lowercase title on one line was rejected, costing the OpenID4VP specification 24 clause ids,
including its entire IANA registry annex. 180 to 194. That it showed up on the second document and
not the first is the argument for keeping more than one specification in the test set.

**One of the three input formats is unreadable, which bounds the generality claim.** RFC 8949 yields
zero headings, and not because of segmentation: the PDF embeds its text in an `Identity-H` font
subset with no `ToUnicode` mapping, so the extractor decodes none of it. `get_text()` returns zero
occurrences of `Abstract`, `Introduction` or `MUST` across the whole document. A tool that claims to
accept any technical specification has to be honest that it currently accepts any specification whose
PDF carries a recoverable character map, and that this is a property of the file rather than of the
standard.

**Deflation was mostly a measurement of its own defect.** The generic-group rule first measured a
16.2 per cent reduction in coverage items, which looked like the answer to the twelvefold
over-generation. Review found the rule keyed on the object's bare name, so it collapsed occurrences
carrying different obligations: on the real fixture 6 of 18 pointer sites were mandatory entries
whose only coverage item pointed at an optional ladder, 16 of 18 declared a different type than the
owner, and the evaluation counted all 18 as covered. The second rule had the mirror defect, keying on
the object's name appearing anywhere in a requirement's text, which deletes a real test purpose
whenever a name happens to occur: an object `nonce` constrained by size suppressed a requirement
stating a 500 ms timing limit, and a three-character name such as `set` matches ordinary English.

Both were errors in the specification, not the implementation, and both are corrected as D31: a group
is keyed on every attribute that determines its purposes, and an overlap is decided by shared
provenance, the object's own source quote against the requirement's text. The honest number after the
correction is **1.4 per cent**, down from 12.9. Every one of the twelve sites that stopped grouping
differs on type, kind, presence or structure membership, and none on spelling, so the fall is the
defect being removed rather than a key made too blunt.

The conclusion is worth more than the mechanism. **X.291's generic test suite factors across systems
under test, not across clauses of one specification.** The official suite's 27 generic references run
between its mDL and mDL-reader appendices, where the same structure is tested from two sides; within
a single standard, the same field name recurring in different structures genuinely carries different
obligations, and there is almost nothing to factor. So deflation is not the remedy for over-generation
that we took it for. It is a correctness mechanism that keeps a shared specification from being tested
twice, worth 1.4 per cent here and more on a specification that genuinely repeats itself, and the
twelvefold density gap has to be addressed where it is actually produced, in how many items one
declaration yields.

### 6.5 Results

**Measurement first, on the previous run's artefacts.** Rebuilding the metric before rebuilding the
generator was the right order, because it moved the headline up rather than down and told us how much
of the old 13.8 per cent was a measurement artefact.

| Scope | LLM judge | Judge-free structural matcher |
|---|---|---|
| All official cases citing a clause of the standard | 13.8 per cent (95 of 687) | **22.5 per cent** (168 of 747 scorable) |
| Scored in-edition subset | 16.8 per cent (of 250) | **18.8 per cent** |
| Macro average over official test families | 11.5 per cent | 17.5 per cent |

The two methods agree on 73.4 per cent of the cases both can score, which is the result that matters:
the structural matcher is not merely a looser judge. A 20-case hand audit of the rule-based inference
gets the check type right 15 times and the data item right 10 times plus 3 correct nulls, and every
error mode observed produces a false negative, so 22.5 per cent is a lower bound. Two honest limits:
the matcher needs a source object, and requirement-derived items carry no name, so 1575 of 3257
coverage items cannot be scored by it at all; and the in-edition denominator of 250 is a floor,
because an id present in the 2021 edition and renumbered in the 2020 draft counts as absent for want
of a semantic crosswalk between the editions.

**Three denominators, stated rather than chosen silently.** 907 official cases in all; 687 citing a
clause of the standard under test; 250 whose cited clause id actually exists in the input edition.
The third is the only honest one without a semantic crosswalk between the 2020 draft and the 2021
published edition, and it is the one scored.

**ICS coverage is an invariant, not a score, and saying so is part of the result.** D27 nominated it
as the headline because ETR 266 Guidance 5 states the rule the genre actually measures, that any
mandatory or optional item of the ICS is covered by at least one test purpose, and because it needs
no official suite and so transfers to standards that have none. Wiring it up and running all sixteen
flag combinations showed it reads 100 per cent of 65 items in every one. That is because the
generator emits a capability item per due ICS item by construction, so the figure cannot fall below
100 without a defect. It is therefore a soundness check on the derive stage, which is worth having and
is worth publishing as a guarantee, but it is not a measure of how much of a standard was understood.
What carries that information is the **denominator**: 65 ICS items is a claim about how many testable
features the tool found in the document, and it is that count, not the ratio, which should be compared
across runs and across standards.

**To be filled from the next full run** on a local 31B model: the ICS item count with its coverage
invariant restated; objects by origin,
prose against grammar; coverage items by test group; the structural match rate beside the judge rate
on the new plan; and wall time against the previous 12.7 hours, with the LLM call count under batched
and per-item generation.

### 6.6 Sources added

`[S45]` Masuda et al., arXiv:2510.03641. `[S46]` ITU-T X.291 (04/1995) = ISO/IEC 9646-2, clauses
10.2 to 10.4, 11, Annex D. `[S47]` ETSI ETR 266 (1996), Test Purpose style guide. `[S48]` ETSI IPv6
testing project figures, ITU-T workshop, December 2006. `[S49]` ETSI ETS 300 406 (1995), clause 7.4.1
and Annexes A and D. `[S50]` Pretschner et al., ICSE 2005. `[S51]` ISO/IEC/IEEE 29119-4:2021, clauses
5.2.1 to 5.2.12 and 6.2.x. `[S52]` ETSI ES 203 119-4 (2022) TDL Structured Test Objectives and
ES 202 553 TPLan; Schulz, Wiles and Randall, TestCom/FATES 2007, LNCS 4581. `[S53]` ParCleanse,
ISSTA 2025, arXiv:2504.18050. `[S54]` AUTOSPEC, arXiv:2511.17977. `[S55]` Wataoka et al., NeurIPS
2024 on judge self-preference, and the ISSTA 2025 meta-evaluation, arXiv:2502.06193.

**Caveat.** 29119-4's per-technique coverage-item definitions and its Annex F on technique
effectiveness are paywalled; clause names and the standard's architecture are verified from the free
preview, their contents are not. ISO/IEC 9646-7 on ICS proformas is not in ITU's free set and is
known only indirectly through ETS 300 406 Annex A.
