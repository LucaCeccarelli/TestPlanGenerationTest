# Raising recall and completeness of LLM extraction over long technical documents

Framing per the coordinator's refinement: the target output is an ISO/IEC 9646-tradition **abstract test-purpose suite** (fixed-field records, templated prose, ~2.4 steps and ~2.9 expected results per case, 112 distinct precondition blocks shared across 907 cases). Prose generation is treated as solved-enough. The research question is **recall of the inventory those records enumerate** — the per-field checks (455 presence/absence, 257 type/encoding, 97 value-domain) whose source material is the standard's data-element tables, CDDL definitions and certificate profile tables.

Sections are ordered by the coordinator's priority. Sources are labelled where they are vendor or practitioner material rather than peer-reviewed.

---

## 1. Exhaustive record-per-row extraction from tables in long documents

### Takeaway
No published study was found that reports per-row semantic extraction accuracy on a real standard's data-element table. What the literature does establish, consistently: **table row/shape recognition is the dominant failure mode** (row accuracy 0.596, exact shape accuracy 0.334 on PubTabNet), **whole-document accuracy collapses relative to field accuracy** (0.956 field vs 0.76 document), **LLMs cannot be trusted to count rows**, and **truncation of array-valued output is the named top production failure for exactly this shape of task** — it leaves unclosed JSON and raises no error. The specification-extraction systems that reach high recall (ParCleanse, SpecGPT) all avoid long-array decoding entirely by generating per structural node and merging.

### Cited Findings — row and structure accuracy
- Table **structure** recognition is the weak link: on PubTabNet a structure-recognition pipeline reported **row accuracy 0.596, column accuracy 0.584, exact shape accuracy 0.334**, with column merging as the main failure mode — [RaV-IDP, arXiv:2604.23644](https://arxiv.org/pdf/2604.23644)
- **Field accuracy ≫ document accuracy**: in a structured-output benchmark one model reached **~0.956 field accuracy on table analysis but only 0.76 document accuracy** — a few errors per document compound into a failed document — [arXiv:2603.18014](https://arxiv.org/pdf/2603.18014)
- Output format affects even the ability to measure: a multimodal table-extraction benchmark found Markdown output "lacked a standard structure across models, which made consistent comparison hard", and switched to structured JSON/CSV, scoring with F1, precision/recall and a shape-accuracy measure — [Benchmarking Table Extraction, ACL XLLM 2025](https://aclanthology.org/2025.xllm-1.2.pdf)
- Established partial-credit table metrics are **TEDS** (tree edit distance) and **GriTS** (grid table similarity), which give credit for near-correct structure — [ACL XLLM 2025](https://aclanthology.org/2025.xllm-1.2.pdf)
- **LLMs are unreliable at counting rows**: a benchmark found "the smaller Llama-2 models such as Llama-2-7B or Llama-2-13B make mistakes in counting rows" — so the row count must come from deterministic code — [Evaluating the Table Reasoning Ability of LLMs and MLLMs, ACL Findings 2024](https://aclanthology.org/2024.findings-acl.23.pdf)
- Structural table tasks are a distinct, measurable weakness: "Table Meets LLM" (WSDM 2024) builds a benchmark of **seven structural tasks including cell lookup, row retrieval and size detection**, and finds performance varies with "table input format, content order, role prompting, and partition marks". Self-augmentation gains were small: **TabFact +2.31%, HybridQA +2.13%, SQA +2.72%, Feverous +0.84%, ToTTo +5.68%** — [arXiv:2305.13062](https://arxiv.org/abs/2305.13062)
- Small models specifically fail on spec tables: a 3GPP table benchmark found "smaller models (under 10B parameters) struggle both to recall 3GPP knowledge and to interpret tables", attributed to limited telecom exposure during pretraining — [TeleTables, arXiv:2601.04202](https://arxiv.org/pdf/2601.04202)
- Mechanism caution (vendor-reported): correct cell text with wrong span structure silently reassigns values to the wrong columns, which downstream code typically cannot detect — [Reducto, vendor](https://llms.reducto.ai/table-extraction-accuracy-scanned-pdfs)
- Vendor-reported figure, no independent head-to-head: Reducto claims **99.6% precision and recall on LongExtractBench**, said to be audited by micro1 across 225 long documents — [Reducto, vendor](https://llms.reducto.ai/best-llm-ready-document-parsers-2025)

### Cited Findings — how truncation of long structured output is avoided
- Truncation is the **named top production failure for array-valued schemas**: "the most common production failure for schemas with array fields, since list length varies and a schema that usually yields a few items can occasionally yield many more", caused by a `max_tokens` too low for the schema's realistic output size — [GMI Cloud, practitioner](https://www.gmicloud.ai/en/blog/structured-output-for-llm-inference-json-schema-enforcement-constrained-decoding-and-parse-failure-rates)
- Constrained decoding guarantees **syntax, not completeness**: when generation stops at the limit the JSON is left syntactically incomplete with an unclosed brace or missing bracket. An implementation report on Transformers.js structured output confirms that stopping at the new-token cap "returns partial JSON with no error raised, so the caller has to detect it" — [GMI Cloud](https://www.gmicloud.ai/en/blog/structured-output-for-llm-inference-json-schema-enforcement-constrained-decoding-and-parse-failure-rates); [openaccountant/wilson issue #168](https://github.com/openaccountant/wilson/issues/168)
- **TruncProof (arXiv:2605.13076)** states the problem formally: existing approaches "can't strictly enforce a maximum token count, which leads to either endless generation or truncated output". It proposes grammar-constrained decoding that **estimates the minimum tokens needed to finish a valid object at each step**, so the output always closes within budget — [TruncProof](https://arxiv.org/pdf/2605.13076)
- Degenerate repetition is a second, separate truncation cause: LLM entity extraction can enter a loop that "infinitely repeats the same sequence as their output up to the maximum output token cap", not fixable by temperature or basic prompt engineering — [GDELT, practitioner](https://blog.gdeltproject.org/llm-infinite-loops-in-llm-entity-extraction-when-temperature-basic-prompt-engineering-cant-fix-things/)
- Constrained decoding also carries a quality cost, not only latency — [Draft-Conditioned Constrained Decoding, arXiv:2603.03305](https://arxiv.org/pdf/2603.03305); efficiency work on Earley-driven dynamic pruning — [arXiv:2506.01151](https://arxiv.org/pdf/2506.01151)
- Standard practitioner mitigations, repeated across sources: treat the `length` finish reason as a **failure** not a success; size `max_tokens` for worst-case list length; cap array length in the schema (`maxItems`) so the grammar itself bounds the output; **paginate or chunk long lists across several calls instead of asking for everything at once** — [GMI Cloud](https://www.gmicloud.ai/en/blog/structured-output-for-llm-inference-json-schema-enforcement-constrained-decoding-and-parse-failure-rates)

### Cited Findings — windowed / per-node generation as practised by the best spec systems
- **ParCleanse (arXiv:2504.18050)** never asks for a long array. It builds a DocTree from the RFC table of contents, generates a format **per node (section)** independently, syntax-checks each with **EverParse** and **regenerates on error until it passes**, then merges node formats bottom-up with the LLM until the root holds the full format. 9 RFCs, 42–104 pages (mean 62), GPT-4o at temperature 0 — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- A non-LLM parser, not the LLM, is the acceptance gate for each bounded output — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- **SpecGPT (arXiv:2510.14348)** output volumes give the scale reference for a chunked design: per protocol **50k–98k output tokens spread over many per-section calls**, never one call — [SpecGPT](https://arxiv.org/html/2510.14348v1)
- Chunk **size** barely matters once structure is respected, so there is little to tune there: on VRDU, F1 by chunk tier was small (≤1024 tok) **0.591**, medium (≤2048) **0.650**, max (≤4096) **0.651**; on FUNSD 0.415 / 0.414 / 0.411. "Max chunks won by 0.001 over medium and 0.060 over small" — only over-small chunks hurt — [LayIE-LLM, arXiv:2502.18179v4](https://arxiv.org/html/2502.18179v4)
- What *does* move F1 on layout-rich documents is **output post-processing and match criteria**, not chunking: output refinement "cleaned" raised VRDU F1 from 0.650 to **0.734**; fuzzy matching 0.650 → **0.733**; full design-space tuning one-factor-at-a-time **0.783**, brute-force best **0.801** against a 0.650 baseline (~20% and ~23% relative) — [LayIE-LLM](https://arxiv.org/html/2502.18179v4)
- Warning against padding the per-row prompt with examples: on VRDU, **0 examples gave F1 0.650 (few-shot) / 0.649 (CoT), 5 examples gave 0.580 / 0.578** — more in-context examples *hurt* — [LayIE-LLM](https://arxiv.org/html/2502.18179v4)
- Input serialization is dataset-dependent, so it must be measured rather than assumed: VRDU OCR 0.650 vs Markdown 0.648; FUNSD OCR 0.414 vs Markdown **0.490** — [LayIE-LLM](https://arxiv.org/html/2502.18179v4)
- Practitioner reports of splitting by field: in a KYC extraction system the author moved from one call per document to **one call per field**, reporting the single-call version "was juggling too much: layout, language, format, and field semantics, with errors in one field bleeding into others. Per-field calls were slower and more expensive, but each call was simple enough that the model stopped tripping over itself" — [nilenso blog, practitioner](https://blog.nilenso.com/blog/2026/05/18/evals-before-prompts-building-an-llm-ocr-for-kyc/)
- The same author **later reverted** to a single call per document once the model improved — the decomposition "had quietly outlived its usefulness" — [nilenso blog, practitioner](https://blog.nilenso.com/blog/2026/05/18/evals-before-prompts-building-an-llm-ocr-for-kyc/)
- Known hazard of per-slot extraction: a per-field "hunter" call "fills a fixed schema slot for every field under completion pressure; it will produce an answer regardless of whether the field is clearly present in the document, making it prone to confabulating plausible values for absent or ambiguous fields" — [arXiv:2606.24420](https://arxiv.org/pdf/2606.24420)
- Legal-reasoning extraction split a single prompt because it "produced outputs that were too short and missed issues on long documents" — the same truncation-as-silent-recall-loss pattern — [arXiv:2607.03325](https://arxiv.org/pdf/2607.03325)

### Inferences
- The tool's ingest **already preserves table rows as records**, which means the hardest published failure (row/shape accuracy 0.596/0.334) is solved upstream and does not need an LLM at all. The remaining LLM job is a bounded per-row conversion — the regime where ~0.956 field accuracy applies rather than 0.76 document accuracy.
- One call per row, or per small fixed-size row window, makes the observed 33-rows → 3-objects failure **structurally impossible**: each call's output is bounded, so truncation cannot silently drop 30 records. This is the same move ParCleanse makes at section granularity and the KYC system makes at field granularity.
- Discarding a truncated reply converts a *partial* result into a *zero* result — the 361-rows → 4-objects case. Even with no other change, salvaging the complete array prefix from a truncated reply and re-prompting for the residual rows recovers most of that loss. Ollama exposes `done_reason: "length"`, so the check is cheap; the published advice is that it must gate acceptance explicitly, because neither JSON-schema enforcement nor a grammar will surface it.
- The per-row design has one documented cost to guard: slot-filling pressure invites confabulated values for absent fields (arXiv:2606.24420). The tool's existing verbatim-source-quote requirement is the right counter-measure, and should be mandatory on per-row object extraction too.
- LayIE-LLM's 5-shot regression argues against enriching the per-row prompt with examples; its "cleaned output" gain (+0.084 F1) argues for normalising model output against the known row vocabulary instead.

### Gaps
- **No published per-row extraction accuracy on an ISO/ETSI/3GPP data-element table.** Row-level numbers exist only for PubTabNet-style structure recognition, not for semantic field extraction from spec tables.
- No study found that compares "one call per table" against "one call per row" with recall reported for both.
- No published measurement of truncation rate versus array length for any specific open model, and nothing specific to Ollama or to a ~31B model.
- TruncProof is a 2026 preprint with no independent replication or production implementation found.
- "Table Meets LLM" quantifies format and partition-mark effects in its body tables, but the abstract page gives no per-format figures; the full-text numbers for serialization-format comparison and for adding explicit row/column identifiers were not retrievable (PDF text layer compressed).

---

## 2. Closing the recall gap by construction: count first, then one record per row

### Takeaway
This is the thinnest area in the published literature and the strongest novelty claim available. The **count-the-rows-then-require-one-record-per-row** pattern appears only in practitioner tooling (sec2md's report-only table-completeness checks) and in deterministic-denominator advice, never as a measured technique. The closest published results for the related **extract-a-key-list-then-fill-each-key-separately** pattern are strong: ParCleanse's decomposition ablation shows field-name recall **54% → 94%** and independent-constraint recall **26% → 82%**, and a materials pipeline reports a miss rate of **12.4% → 3.3%** from iterative extraction with source tracking.

### Cited Findings — decomposition by construction, with numbers
- **ParCleanse decomposition ablation** (precision/recall %) — the cleanest published before/after for "decompose then merge" versus "whole document in one prompt":

  | Variant | Msg type | Field name | Field type | Indep. constr. | Dep. constr. |
  |---|---|---|---|---|---|
  | Full ParCleanse | 100/100 | 99/95 | 94/91 | 98/82 | 73/44 |
  | − traceability refinement | 100/100 | 99/94 | 93/89 | 88/68 | 85/44 |
  | − refinement **and** − divide-and-conquer | 97/**71** | 91/**54** | 65/**37** | 79/**26** | **0/0** |

  "Removing divide-and-conquer causes a consistent drop across all element types"; dependent constraints go to zero — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- Baseline on the same task without decomposition: **ChatAFL** scored message types 89/55, field names 78/35, independent constraints 81/**10**, with field types and dependent constraints unsupported — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- ParCleanse also **corrects its own structural index** before extracting: the LLM summarizes each section, then "identifies hidden parent-child dependencies among same-level sections", used to correct the ToC-derived tree — a step beyond naive heading nesting — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- **Iterative extraction + source tracking measured against single-pass**: a multi-stage materials-IE pipeline capturing 47 features reports **F1 ≈ 0.96 at both feature and tuple level**, and versus single-pass extraction without source tracking, **+10.0% F1 (feature level) and +13.7% (tuple level)** on microstructure. Missed materials fell **from 49 to 13 out of 396** across 100 articles — **miss rate 12.4% → 3.3%** — with zero false positives claimed — [arXiv:2510.05142](https://arxiv.org/abs/2510.05142)
- **Key-list-then-fill, as practised**: a knowledge-graph pipeline uses iterative triplet extraction where "the set of extracted entities is used as a constraint to extract relations between them from the text chunk" — entities enumerated first, relations filled against that fixed key list — [arXiv:2307.01128](https://arxiv.org/pdf/2307.01128)
- **Annotation-then-conversion (arXiv:2504.01294)** is the same two-stage shape applied to specifications: 603 specifications from 37 documents across 3 open-source systems, evaluated on GPT-4o, Claude and Llama. End-to-end extraction fails through "specification oversimplification and specification fabrication". The two-stage method yields **+29.2% in the number of correctly extracted specifications and +14.0% in average accuracy**; best LLM reaches **71.6% accuracy** — [arXiv:2504.01294](https://arxiv.org/abs/2504.01294)
- End-to-end single-stage accuracy on that benchmark: **Claude 51.7%, GPT-4o 47.1%, Llama 45.4%** — roughly half of specifications correct before the two-stage fix — [arXiv:2504.01294](https://arxiv.org/pdf/2504.01294)
- **SpecGPT's segmentation is structural, not length-based**: regex cleaning strips tables of contents, headers, footers and footnote markers; paragraphs are mapped to section numbers; a section tree is built; **leaf-node content is merged bottom-up into parent sections**. Cross-references are handled with a section-number-prefixed mapping — [SpecGPT](https://arxiv.org/html/2510.14348v1)

### Cited Findings — verifying that no row was skipped
- The closest published implementation of a row-completeness check is **sec2md**, an SEC-filing converter, which runs **report-only checks comparing each source table with the Markdown its parser produced**: "Check 1 looks for source numbers missing from the table's output. Check 2 looks for rows or values that changed order" — [sec2md PR #4, practitioner](https://github.com/kelab5am/sec2md/pull/4)
- Counts must be deterministic, not model-produced, because small Llama-2 models "make mistakes in counting rows" — [ACL Findings 2024](https://aclanthology.org/2024.findings-acl.23.pdf)
- Null-aware counting separates "row missing" from "row extracted but incomplete": `COUNT(*)` counts all rows including NULLs, `COUNT(column)` only non-NULL, "which helps measure data completeness" — [Dawiso, practitioner reference](https://www.dawiso.com/glossary/sql-count-complete-guide-to-counting-records-in-database-queries)
- **Per-record support tracing** as a published completeness check: an approach for finding support for tabular LLM outputs measures "the number of data lake tables that support tuples (or partial tuples) in a generated table" — i.e. confirming every output record traces back to a source row — [Finding Support for Tabular LLM Outputs, VLDB TaDA 2024](https://vldb.org/workshops/2024/proceedings/TaDA/TaDA.9.pdf)
- ParCleanse's **fine-grained, per-property** checking vastly outperforms one whole-object check: feeding the whole extracted format into a single Z3 formula produced 233 issues (211 crashes) and only **4 unique bugs**, whereas per-property testing found **69 unique bugs** — [ParCleanse](https://arxiv.org/html/2504.18050v1)

### Cited Findings — completeness feedback loops, and their limits
- ParCleanse's **traceability-assisted refinement** (trace a suspected inconsistency back to its source RFC section, re-reason step by step about whether the format or the parser is wrong) lifts independent-constraint recall **68% → 82%** and precision **88% → 98%**. Removing traceability from the identification stage drops format-error classification accuracy to **0%** and overall accuracy from **97% to 84%**; removing both traceability and fine-grained testing drops accuracy on logical inconsistencies to **4%** — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- **ReLoop (arXiv:2602.15983)** makes execution verification the only blocking check: "A Fatal result triggers regeneration with error feedback (up to N attempts)", and additionally embeds a self-check inside the generation call asking whether every constraint is implemented and whether all numeric values were extracted, before the output is returned — [ReLoop](https://arxiv.org/html/2602.15983v2)
- **Error-targeted retry beats blind retry**: send back the source document, the failed extraction *and the specific validation error*, because "without the specific error, the model has no guidance for what to fix and typically produces the same mistake" — [Validation/Retry/Feedback guide, practitioner](https://claudecertificationguide.com/learn/4-prompt-engineering/4-4-validation-retry-loops)
- **Re-prompting for missed items saturates**: "the LLM is asked to process the document again and search for other entities which were not extracted yet", on the premise that "the first LLM extraction is typically not exhaustive". On a ~12k-character document, "each iteration enriches the extracted information, but the benefit decreases"; **from the third iteration (after four LLM calls) the majority of scores are either getting worse or stagnating**, and "the risk that the LLM will suffer from hallucinations increases as we observe a growth of bias" — [arXiv:2404.04068](https://arxiv.org/pdf/2404.04068)
- That paper's stopping rule is explicitly qualitative: stop "when an additional LLM call will return no or only a few new entities"; the right round count "depends heavily on the text being extracted and on the chosen schema" — [arXiv:2404.04068](https://arxiv.org/pdf/2404.04068)
- **Regenerate beats iterative correction when the verifier is noisy**: "when verification signals are noisy, increasing the number of verification-and-rectification iterations does not guarantee consistent performance gains"; verification-and-regeneration is "more robust to verification noise and more efficient than repeated correction loops" — [arXiv:2603.20441](https://arxiv.org/html/2603.20441)
- **Benchmark feedback against plain resampling**: a preregistered study on frozen small code models found "code-plus-facts and blind resampling produced zero observed pooled difference in the tested sample" — [arXiv:2606.31511](https://arxiv.org/pdf/2606.31511)
- The completeness check can itself cause the miss: one audit found "a revision prompt asking for full re-derivation regularly exhausted the token budget before reaching the marker" — [arXiv:2608.04355](https://arxiv.org/pdf/2608.04355)
- Naive chunk-by-chunk iteration accumulates error: "chunk-by-chunk extraction has high recall but suffers from error accumulation… The best chunk-by-chunk method scores 38.8, substantially below both end-to-end extraction and GAVEL-AGENT. The gap is mainly due to iterative update errors" — [Gavel, arXiv:2601.04424](https://arxiv.org/pdf/2601.04424)

### Inferences
- The tool is unusually well placed to build the thing the literature lacks: a **hard, non-LLM completeness oracle per clause**. Because the ingest already preserves rows as records, `objects_extracted_for_clause / rows_in_clause_tables` is computable with no annotation at all. On the two reported failures it reads 3/33 and 4/361 — the gap is detectable before any LLM is consulted.
- The row-ID binding step that sec2md and the VLDB support-tracing work both imply is the cheap enforcement mechanism: assign each ingested row a stable ordinal, pass it in the prompt, require it back in each output record, then set-difference the returned IDs against the source IDs. That turns a silent recall loss into an enumerable residual.
- Because the residual is enumerable, the re-prompt is well-specified — the opposite of the noisy-verifier case the regeneration paper warns against. It should target **only the missing row IDs**, not a re-derivation of the clause, which is both the token-budget-exhaustion failure (arXiv:2608.04355) and the error-accumulation failure (Gavel).
- The 3-iteration saturation point and the Gavel error-accumulation result together argue for **union-with-dedup passes** (each pass only adds) rather than passes that rewrite a running state.
- ParCleanse's per-property-over-whole-object result (69 vs 4 bugs) is the same lesson one level down: verify each extracted object against its own source row, not the clause's object set as a whole.

### Gaps
- **No published system reports "recall before gap-feedback / recall after gap-feedback" for structured extraction from standards.** The row-count-as-denominator technique appears nowhere as a measured method. This is genuinely unaddressed and is the most defensible novelty claim available.
- sec2md's checks are report-only and carry no published accuracy figures; they establish the pattern, not its effectiveness.
- No measured threshold for when to stop a gap-targeted re-prompt loop; the only published guidance is qualitative and from a single 12k-character case study.

---

## 3. Filling a fixed field template, and reusing shared blocks rather than regenerating them

### Takeaway
**This is the weakest-covered area in the literature and, judging by the evidence, the least worth researching further** — which supports the coordinator's instruction to treat prose as solved-enough. No work was found on LLM generation of ISO/IEC 9646 TSS&TP records or ETSI abstract test purposes. The nearest published findings are that exact-match slot-filling accuracy is low and gains from more few-shot examples are uneven, and that retrieved-demonstration selection helps cross-domain slot filling. For the specific case of a precondition block shared verbatim by 154 cases, the literature offers no technique because the problem is not a generation problem: it is a lookup.

### Cited Findings
- **No LLM work on this genre exists.** A targeted search for LLM generation of ETSI/TTCN test purposes or abstract test suites returned only the ETSI framework documents themselves. ETSI conformance deliverables are split with Part 2 covering **test suite structure and test purposes (TSS&TP)** and Part 3 the **Abstract Test Suite (ATS)** — [ETSI TS 103 663-2](https://www.etsi.org/deliver/etsi_ts/103600_103699/10366302/01.03.01_60/ts_10366302v010301p.pdf); [GTPv2-C ATS overview](https://ttcn-3.etsi.org/index.php/downloads/publicts/publicts-etsi/122-gtpv2-c-conformance-testing-for-s11-interface)
- An ITU-T conformance tutorial defines the test-purpose step as saying "what each possible test case should check, written in whatever form is most suitable" — i.e. the genre deliberately leaves the prose form loose, which is why templating works — [ITU-T SG 17 tutorial](https://www.itu.int/dms_pub/itu-t/oth/15/04/T15040000080001PDFE.pdf)
- Nearest adjacent LLM work: **LLMCFG-TGen** derives abstract test cases from use cases via LLM-generated control flow graphs, and notes that LLM test generation directly from natural-language requirements "can suffer from incompleteness, redundancy, and unclear output, largely because of hallucinations" — [arXiv:2512.06401](https://arxiv.org/pdf/2512.06401)
- **Retrieved exemplars for slot filling**: a cross-domain zero-shot slot-filling method retrieves similar demonstrations per test input with a nearest-neighbour method, then selects among them by average confidence, and additionally feeds a small model's slot predictions to the LLM as extra reference — [ACL Findings 2025](https://aclanthology.org/2025.findings-acl.1097.pdf)
- **Template-then-slot pipelines** are the established shape: Skill2Query runs query template generation → parameter slot filling → expansion, noting that "few-shot examples provide additional clues about parameter expressions and possible values" — [arXiv:2608.16071](https://arxiv.org/pdf/2608.16071)
- **Exact-match slot filling is hard and few-shot gains are uneven**: a template-and-slot-filling annotation study reports GPT-4 and GPT-3.5 results for template selection and slot-filling accuracy across different numbers of few-shot examples, with low exact-match slot-filling accuracy and uneven gains from more examples — [Flee the Flaw, arXiv:2406.12402](https://arxiv.org/pdf/2406.12402)
- Consistency diagnosis: "many model inconsistencies are actually retrieval inconsistencies", so retrieval details should be logged separately from generation — [Deepchecks glossary, practitioner](https://deepchecks.com/glossary/llm-output-consistency/)
- Relevant counter-evidence against adding examples to the per-record prompt: on VRDU, 0 in-context examples gave F1 0.650 and 5 gave 0.580 — [LayIE-LLM](https://arxiv.org/html/2502.18179v4)

### Inferences
- With 112 distinct precondition blocks across 907 cases and the most common shared by 154, the human suite's consistency comes from **reuse, not from re-authoring**. The engineering equivalent is a block library keyed on (system under test, technology, profile), selected deterministically and emitted verbatim — a lookup, not a generation. No LLM call is needed for the shared part, which also removes it as a source of variance and of token budget pressure.
- The identifier taxonomy (`mDL_DM_FamilyName_01`, `Common_COSESign1_04` — 118 families averaging 7.7 cases) is itself derivable from the extracted inventory plus the check category. That makes the record ID a **function of the coverage item**, so it can be assigned deterministically and used as the join key for the completeness check in section 2.
- The only genuinely LLM-shaped part of the record is the Purpose line and the 2–3 step/expected-result pairs. At ~2.4 steps and ~2.9 expected results per case, each generation is small and bounded — the LayIE-LLM evidence says to keep that prompt lean rather than loading it with exemplars, and the slot-filling literature says exact-match prose reproduction is where models are weakest, which is another argument for emitting shared blocks literally.

### Gaps
- No published accuracy figures for generating 9646-style test-purpose records, with or without template reuse. The genre appears entirely unstudied in the LLM literature.
- No study found that measures consistency gains from emitting a retrieved block verbatim versus regenerating it, in any domain.
- The "Flee the Flaw" slot-filling accuracy numbers were visible only as a described table, not as retrievable values.

---

## 4. General recall techniques: multi-pass, ensembling, self-consistency, and model size

### Takeaway
Ranked by reported recall gain on long-document extraction: **decomposition first** (ParCleanse: field-name recall 54% → 95%; L3X: 38.7–47.7% → 83.6%), then **union of varied retrieval/prompt reformulations** (L3X: 76.2% → 83.6% from 1 to 5 reformulations), then **majority-vote ensembling**, which buys precision rather than recall (SpecGPT: +11.5 precision points, −2.1 recall versus the best single model). Model size matters but less than architecture: L3X's own 70B model scored only 38.7–47.7% recall before decomposition.

### Cited Findings — union and ensembling
- **L3X "Recall Them All" (arXiv:2405.02732, TACL)**: long object-list extraction from long texts in two stages — recall-oriented retrieval-augmented generation, then precision-oriented scrutinization to validate/prune. Books corpus: 11 books/series, ~16,000 pages, 8 predicates, 764 subject-predicate pairs, ~5,300 entities, ~12,000 aliases — [L3X](https://arxiv.org/abs/2405.02732); numbers from [TACL PDF](https://people.mpi-inf.mpg.de/~ssinghan/tacl_paper.pdf)
- **L3X stage-1 recall (books, macro-avg %)**: LLM-only zero-shot single prompt **38.7**; LLM-only few-shot **ensemble 47.7**; L3X variants **83.4–85.2**; oracle upper bound (all top-500 passages) **88** — [L3X TACL PDF](https://people.mpi-inf.mpg.de/~ssinghan/tacl_paper.pdf)
- **L3X query-ensembling ablation** (amp config, books) — the cleanest published recall-vs-ensemble-size curve:

  | # retriever query reformulations | Stage-1 recall | R@P50 | R@P80 |
  |---|---|---|---|
  | 1 | 76.2 | 44.0 | 31.5 |
  | 3 | 81.1 | 48.2 | 35.4 |
  | 5 | **83.6** | **48.6** | **35.9** |

  — [L3X TACL PDF](https://people.mpi-inf.mpg.de/~ssinghan/tacl_paper.pdf)
- L3X's precision stage trades recall hard: best config **R@P50 49.7, R@P80 36.5** on books — holding precision at 80% costs ~47 points of the 83.6% candidate recall. On web data (~10M C4 documents): stage-1 recall **60.5** (vs 41.9 LLM-only few-shot ensemble), stage-2 R@P50 31.9, R@P80 18.3, oracle ceiling 65 — [L3X TACL PDF](https://people.mpi-inf.mpg.de/~ssinghan/tacl_paper.pdf)
- L3X notes ~**16% of all ground-truth object values fall into a low-rank-missing category** that the system misses even after recall maximisation — [L3X TACL PDF](https://people.mpi-inf.mpg.de/~ssinghan/tacl_paper.pdf)
- **SpecGPT ensembling**: five LLMs (GPT-4o, DeepSeek V3, Qwen Turbo, Claude Sonnet 4, Gemini 2.5 Pro) run identical prompts at **temperature 0.2**; transitions aligned when states match exactly and action/condition spans overlap ≥0.75 (word-based), then combined by **majority voting** — [SpecGPT](https://arxiv.org/html/2510.14348v1)
- SpecGPT NAS transition extraction (179 ground-truth transitions), P/R/F1 %:

  | Model | P | R | F1 |
  |---|---|---|---|
  | GPT-4o | 79.09 | **92.55** | 85.29 |
  | Claude Sonnet 4 | 80.39 | 87.23 | 83.67 |
  | Gemini 2.5 Pro | 70.00 | 89.36 | 78.50 |
  | DeepSeek V3 | 68.70 | 84.04 | 75.60 |
  | Qwen Turbo | 61.71 | 77.66 | 68.77 |
  | **Ensemble (5-model vote)** | **91.86** | 90.43 | **91.14** |

  Ensemble F1 is **+5.85 over the best single model and +22.37 over the weakest**; note recall *fell* 2.1 points versus GPT-4o alone — [SpecGPT](https://arxiv.org/html/2510.14348v1)
- **Prompt design dominated ensembling** in SpecGPT: direct prompting without the designed domain-informed prompts scored **F1 14.87%** versus 91.14% — [SpecGPT](https://arxiv.org/html/2510.14348v1)
- SpecGPT cost: per model per protocol, NAS ~222k–237k input and 50k–98k output tokens, 20–202 minutes wall clock; **~$2.7 (NAS), $1.6 (NGAP), $1.5 (PFCP) per full 5-model run** — [SpecGPT](https://arxiv.org/html/2510.14348v1)
- SpecGPT's harder protocols (no single-vs-ensemble split reported): PFCP-all 85.71/90.00/87.80, NGAP-all 70.71/67.96/69.31, NGAP-UCM 57.43/64.89/60.93 — [SpecGPT](https://arxiv.org/html/2510.14348v1)
- **Atomic Self-Consistency (EMNLP 2024, arXiv:2405.13131)** targets recall rather than picking one best answer: sample several generations, split each into atomic facts (one sentence = one atomic fact, chosen over neural decomposition for cost), cluster, filter to the most consistent clusters, summarize the survivors — [arXiv:2405.13131](https://arxiv.org/pdf/2405.13131)
- Sample-count saturation: with self-ensembling for chart data extraction, "On ChartQA (T=2.0), RMS F1 rises sharply from K=3 to K=7 and largely saturates thereafter" — [arXiv:2605.27298](https://arxiv.org/pdf/2605.27298)
- Self-consistency gains are **scale-dependent**: "+3%–6% absolute accuracy improvement over UL2-20B but +9%–23% for LaMDA-137B and GPT-3" (reasoning tasks, not extraction) — [Wang et al., arXiv:2203.11171](https://arxiv.org/pdf/2203.11171)
- Agreement level is diagnostic: full-agreement samples F1 **0.938** vs two-disagreement samples **0.756** — [arXiv:2510.13143](https://arxiv.org/pdf/2510.13143)
- **Google LangExtract** ships multi-pass as a parameter (`extraction_passes=3`, documented as improving recall), motivated by "recall can decrease in multi-fact retrieval scenarios in needle-in-a-haystack tests across million-token contexts", handled "using a chunking strategy, parallel processing and multiple extraction passes over smaller, focused contexts" — [Google Developers Blog](https://developers.googleblog.com/introducing-langextract-a-gemini-powered-information-extraction-library/); [google/langextract](https://github.com/google/langextract)
- The recall/precision tension is structural: "enhancing recall introduces more irrelevant information during the model's reasoning process, while increasing retrieval precision reduces recall" — [CAFE, arXiv:2505.10063](https://arxiv.org/pdf/2505.10063)

### Cited Findings — model size, fine-tuning, distillation
- **L3X model-size ablation** — the only size sweep found on long-document recall: main experiments used Llama 3.1 Instruct 70B; with Llama-8B (~10× smaller) "recall fell below 50%, versus about 80% with the 70B model". GPT-3.5 preliminary results were similar to Llama-70B — [L3X TACL PDF](https://people.mpi-inf.mpg.de/~ssinghan/tacl_paper.pdf)
- Frontier text models cluster tightly on layout-rich IE: GPT-4o 0.798, LLaMA3-70B 0.784, GPT-3.5 0.777 (STL F1). Multimodal: GPT-4o-vision 0.902 ($4.76), **Qwen2.5-vision 0.890 (local, $0)**. Conclusion: "text-only approaches constitute a good trade-off between performance and cost" — [LayIE-LLM](https://arxiv.org/html/2502.18179v4)
- **Fine-tuning beats zero-shot frontier models on a fixed schema**: with 2,998 training documents, "the best fine-tuned open-source models exceed every zero-shot commercial system on this schema"; fine-tuned **Qwen2.5-VL-7B reaches 0.985 F1**, and even SmolVLM2-256M moves **0.000 → 0.726 F1** — [arXiv:2609.15706](https://arxiv.org/pdf/2609.15706)
- LoRA fine-tunes at small scale: rank-8 **LLaMA 3.1-8B at 96.75% F1**; best sub-8B **Qwen 3.5 4B at 96.60% F1** with JSON-only prompting (merchant extraction; no GPT-4 comparison) — [arXiv:2606.08051](https://arxiv.org/pdf/2606.08051)
- Vendor claim: fine-tuned specialists cut document-AI cost ~90% versus frontier models — [Nanonets, vendor](https://nanonets.com/blog/fine-tuned-models-vs-frontier-cost/)
- Unverified secondary: a Medium write-up of "Extract-0" claims a fine-tuned 7B beat GPT-4.1 across 1,000 extraction tasks with an average reward of 0.573 and 89% valid-JSON rate; code unreleased and the original paper was not locatable — [Medium, secondary/unverified](https://ai-engineering-trend.medium.com/a-smaller-model-outperforms-gpt-4-1-on-document-information-extraction-for-196-9e25b39d9538)
- Pre-training resource if distillation is pursued for telecom-style specs: **TSpec-LLM** covers all 3GPP documents from Release 8 to Release 19 (1999–2023) — [arXiv:2406.01768](https://arxiv.org/pdf/2406.01768)

### Inferences
- For a recall-limited pipeline, **union, do not vote**. SpecGPT's vote cost 2.1 points of recall to buy 11.5 points of precision — the wrong trade here, since the tool's rule-based verifier and verbatim-quote requirement can play L3X's stage-2 scrutinization role on a unioned candidate pool.
- Self-consistency's scale dependence (+3–6% at 20B vs +9–23% at 137B) warns that sampling-based voting on a 31B local model will sit at the low end. L3X's union-of-reformulations gain is not scale-dependent in the same way because the diversity comes from the input, not the sampling — which makes it the better fit for a self-hosted mid-size model.
- A 31B model sits between L3X's 8B (<50% recall) and 70B (~80%) points, so size is plausibly a contributing limit. But L3X's own 70B scored only 38.7–47.7% before decomposition: **exhaust decomposition before upgrading the model.** No finding above requires a frontier model; ParCleanse used GPT-4o, but its decisive result is architectural, and SpecGPT's individual-model recalls (77.66–92.55) bracket what a well-prompted 31B could plausibly reach on bounded per-row inputs.
- Fine-tuning evidence (0.985 F1 on a fixed schema) applies cleanly to the object extractor, whose schema is fixed (presence, type, value domain, size, relations). Training pairs are cheap to harvest here: the official conformance suites already cite clauses, giving labelled (clause → expected field checks) pairs.
- Agreement level as a quality signal maps onto the tool's gap-recording behaviour: items found by only one of N variants are candidate gaps to flag rather than silently keep or drop.

### Gaps
- No controlled single-vs-ensemble ablation for SpecGPT beyond NAS, so +5.85 F1 rests on one protocol.
- No paper found reporting self-consistency recall gains for **field-level** extraction at 7B–70B scale with a clean single-run baseline; several candidate papers explicitly declined to isolate the ensemble contribution.
- No published recall number for any 20B–35B open model on document extraction; the 8B/70B L3X pair has no intermediate point.
- No distillation study targeting spec/requirement extraction specifically.
- No recall-per-dollar curve for the union approach; SpecGPT's $1.5–2.7 per run covers 5 frontier APIs, not a local model.
- No quantified recall gain published for LangExtract's `extraction_passes`; treat it as mechanism, not evidence.

---

## 5. Recall levels reached on real standards, and measuring recall without complete ground truth

### Takeaway
The best published recall on real standards is ParCleanse's **100% message types / 95% field names / 91% field types / 82% independent constraints / 44% dependent constraints** on 9 RFCs with GPT-4o. All of it was measured against **hand-written ground truth** costing 0.5–6 hours per protocol. The field has no answer to the no-ground-truth problem beyond hand annotation, oracle upper bounds, cross-release consistency, downstream bug yield, and inter-model agreement.

### Cited Findings
- Best published recall by element type (ParCleanse, 9 RFCs, GPT-4o): **message types 100%, field names 95%, field types 91%, independent constraints 82% (155 of 189), dependent constraints 44%**. TCP was worst, due to implicit alignment and bit-level offset details — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- ParCleanse's ground truth was hand-written: "about 0.5 to 6 hours to write ground-truth formats per protocol, and about 15 minutes per protocol to compare ParCleanse's output against them" — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- SpecGPT measured against manually annotated ground truth (179 NAS transitions); best ensemble recall **90.43%**, precision 91.86% — [SpecGPT](https://arxiv.org/html/2510.14348v1)
- **Cross-release consistency as a ground-truth-free signal**: SpecGPT extracted 142 NAS transitions on Release 15, "about 20% fewer than Release 17", with state count largely unchanged and no P/R/F1 given for Release 15 — [SpecGPT](https://arxiv.org/html/2510.14348v1)
- **Oracle upper bound as a ground-truth-free ceiling**: L3X reports recall if all top-500 retrieved passages were perfectly exploited as **88% (books) / 65% (web)** against achieved 83.6% / 60.5% — separating retrieval ceiling from extraction loss — [L3X TACL PDF](https://people.mpi-inf.mpg.de/~ssinghan/tacl_paper.pdf)
- **Miss rate against a manually counted denominator**: 396 materials across 100 articles, missed 49 → 13, i.e. **12.4% → 3.3%** — [arXiv:2510.05142](https://arxiv.org/abs/2510.05142)
- **Downstream yield as a recall proxy**: ParCleanse found **69 unique bugs (68 new, 36 developer-confirmed, 17 fixed and merged, 18 PRs approved pending, 1 unresolved)**, and classified 90 detected inconsistencies (86 logical, 4 crash) at **97% accuracy**, each bug with a proof-of-concept input. Against ParDiff on BABEL/BFD/BGP-4: 33 unique bugs (all new and confirmed) versus ParDiff's 4 (1 new, 1 confirmed) — [ParCleanse](https://arxiv.org/html/2504.18050v1)
- **Inter-model agreement as a proxy**: full-agreement samples F1 0.938 vs two-disagreement samples 0.756 — [arXiv:2510.13143](https://arxiv.org/pdf/2510.13143)
- Terminology caution: in RAG setups "recall" means *retrieval* recall, not extraction recall — "due to low recall, where not all relevant nodes are retrieved, the LLM may lack the context it needs". The two must be measured separately — [3GPP RAG literature, arXiv:2505.11856](https://arxiv.org/pdf/2505.11856)

### Inferences
- The tool's measurement position is **better than any paper's**. The official ISO/IEC TS 18013-6:2025 suite (907 cases; 687 citing a clause) is an *externally authored* denominator, so 13.8% is a real recall-against-an-independent-oracle figure. Published recall numbers are all against self-authored ground truth and are therefore likely optimistic; the two are not directly comparable, and the notes should say so rather than present 13.8% as directly below ParCleanse's 95%.
- A second, free denominator exists internally: preserved table rows. `objects_extracted / rows_in_clause_tables` is a structural recall proxy requiring no annotation — directly analogous to L3X's oracle upper bound, and reading 3/33 and 4/361 on the two known failures.
- The official suite's 455/257/97 split maps almost exactly onto ParCleanse's element taxonomy: field names → presence/absence, field types → type/encoding, independent constraints → value domain. ParCleanse's profile (**95% / 91% / 82%**) is therefore a reasonable published ceiling estimate for a well-decomposed pipeline on those three categories, against the 13.8% now achieved.
- **Dependent constraints are the expected permanent gap category.** At 44% recall even for GPT-4o with full decomposition and refinement, cross-field conditional requirements should be recorded as gaps by design rather than chased.
- The 118 identifier families averaging 7.7 cases give a third, independent completeness check: a family with far fewer generated cases than its peers signals an under-extracted object, detectable without any ground truth at all.

### Gaps
- **No published system reports extraction recall against an independent, externally authored conformance suite.** Every recall figure in the literature is against ground truth the authors wrote themselves.
- No paper found reports recall **by requirement category** (presence / type / value domain) on an ISO standard.
- "Recall Them All" reports no NDCG or recall@k table despite the list-shaped task; metrics are stage-1 recall/precision/AUC and stage-2 R@P50/R@P80 only.
- No published figure for how much of an abstract test-purpose suite is derivable from a document's tables alone versus from its prose — which would bound the achievable coverage for a table-first strategy.
