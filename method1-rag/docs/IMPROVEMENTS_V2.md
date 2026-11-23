# Improvement Propositions — Second Iteration (Axis A and Axis B)

## Automatic Test Plan Generation from Technical Standards

*This document is the second iteration of the state-of-the-art review. Unlike `IMPROVEMENTS.md`, it starts from a measured diagnosis of the pipeline as it exists in the repository today (commit `35d6bb0`, all nine first-iteration improvements already implemented), identifies what works and what does not, and proposes changes grounded in the 2024–2026 literature. Each proposition is marked **[NEEDS APPROVAL]** so that the choice of what to implement remains explicit.*

*All numbers below were measured on 2026-09-21 on the artefacts present in `data/output/` (1,202-chunk run), on a fresh run of the Axis A extractor and chunker over the three standards now in `data/input/` (ISO/IEC DIS 18013-5, IETF RFC 8949, OpenID for Verifiable Presentations 1.0), and, for Axis B, on a two-chunk end-to-end run through Ollama cloud with `gemma4:31b`. Nothing in this document has been implemented.*

---

## 1. Diagnosis — What Works and What Does Not

### 1.1 Important preliminary: the repository is no longer the baseline

`INITIAL_STATE.md` describes the system before the first-iteration improvements. The current code already contains A1 (two-pass chunking), A2 (BM25 + RRF), A3 (cross-refs and defined terms), B1 (Planner), B2 (schema-in-prompt and reflective retry), B3 (BERTScore gate), C1, C2 and the TraceLLM prompt headers. For the paper, the baseline must be reconstructed from commit `7cb4e9e` (the last commit before "Added the improvements"), not from the working tree. Two statements in `INITIAL_STATE.md` are also not true of either version and should be corrected before publication:

- §4.2 says `is_normative` is set from spaCy modal detection with POS filtering. In the code, the chunker uses a plain regex (`scan_modals` in `axis_a/chunker.py`); the spaCy pass in `nlp_processor.py` is executed by `run_axis_a.py` only to print a sentence count and its result is discarded.
- §4.3 says the chunk size is "512 tokens". `RecursiveCharacterTextSplitter` counts characters. 512 characters is about 105 tokens for the normative chunks measured below.

The input PDF is `ISO/IEC DIS 18013-5:2020(E)`, the Draft International Standard, not the published 2021 edition. The paper should say so.

### 1.2 Axis A — extraction and chunking

**What works.**

- PDF extraction is stable: 126 pages, 113 pages yield text, no extraction exceptions, table regions are separated from the text flow.
- Hybrid retrieval works and is fast. Four hand-written queries (BLE UUID advertisement, data element presence, session key derivation, MSO signature) each returned the correct clause within the top 3 in 0.05–0.10 s. The BM25 index and RRF fusion are wired and used.
- The JSONL/FAISS/BM25 persistence layer is sound; every downstream axis reloads it without reprocessing.

**What does not work.** The root cause of almost every other Axis A failure is a single defect in section-header detection, and it silently disables four of the five first-iteration improvements.

| Measurement (1,202-chunk run) | Value | Consequence |
|---|---|---|
| Distinct section labels | 25 | A 126-page standard with roughly 200 numbered headings is mapped onto 25 labels |
| Chunks labelled `1.2.840.10045.4.3.4` (an ASN.1 OID for ECDSA-with-SHA512) | 645 (54 %) | The header regex `^(\d+(?:\.\d+)+)\s+\S` matches OID strings in the annexes |
| Chunks labelled `8.1.2.2` | 327 (27 %) | No header after 8.1.2.2 is detected until an OID appears 40 pages later |
| Chunks with empty section | 111 | Preamble and annex text |
| Normative chunks flagged `is_full_clause` | **1 / 466** | A1 two-pass chunking is inactive: pass 1 never triggers because "clauses" are 40-page spans |
| Normative chunks that start mid-sentence (lower-case first character) | 208 / 466 | Requirements are cut in the middle |
| Normative chunks with no terminal punctuation | 286 / 466 | Same |
| Chunks with `defined_terms` populated | **0 / 1,202** | A3 defined-terms injection is inactive |
| Chunks with `context_refs` populated | 22 / 1,202, all pointing to OID "sections" | A3 cross-reference resolution is inactive |
| Planner `k` (distinct top-level prefixes) | 5, from prefixes `'', 1, 4, 5, 7, 8` | B1 clusters are named `Section_1`, `Section_810`; grouping is meaningless |
| `get_chunks_for_section("7")` | 4 chunks | The section tool used by the RAG Router and by the A2 evidence guard is unusable |

Why the header regex fails: `pdf_extractor.py` uses `extract_text(layout=True)`, which reproduces the page's horizontal geometry, so every body line and every heading is indented by 5–10 spaces. The regex is anchored at column 0 and never sees them. Annex headings (`A.1`, `C.1.5.7.1`) are not numeric and are never matched either. Re-running header detection on the same text with a whitespace-tolerant pattern and an annex pattern finds 84 numeric and 111 annex headings, versus 62 matches today of which most are OIDs.

Four further Axis A defects are independent of the header problem:

1. **Whitespace inflation.** 27.2 % of all chunk characters are runs of two or more spaces produced by layout mode. The 512-character budget therefore holds about 370 characters of text. 118 chunks are shorter than 50 characters (`"a"`, `"."`, `"Annex C"`).
2. **The Terms and Definitions clause is skipped.** The run used `--skip-pages 1..13`; §3 is on pages 10–11, and §4, §5, §6.1–6.3.1 are on pages 12–13. Even if the pages were kept, the definition parser expects `term: definition` while ISO uses the three-line form `3.1 / mobile device / portable computing device that…`. Both must change for A3 to work.
3. **Cross-reference pattern does not match ISO style.** ISO 18013-5 writes `See 7.4.3` or `as defined in 8.3.2.1`, never `clause 7.4.3` or `§7.4.3`. The regex requires the keyword and therefore matches nothing real.
4. **Normative detection is a modal-verb regex.** It flags 20 chunks that are NOTE or EXAMPLE paragraphs (informative by ISO drafting rules), it flags "may" in descriptive prose ("A document may have multiple nameSpaces"), and it misses the requirements that ISO 18013-5 encodes in tables: the data-element tables (Table 3 onwards) carry the mandatory/optional status in a `Presence` column with no modal verb. 126 chunks contain table rows; only the 65 that happen to contain a modal elsewhere are flagged.

`axis_a/evaluate.py` cannot be executed because `data/ground_truth/annotated_requirements.jsonl` does not exist. There is currently no quantitative evidence for any Axis A design choice.

### 1.3 Axis B — agentic generation

**What works.** Run end-to-end through Ollama cloud with `gemma4:31b` on two normative chunks (BLE UUID advertisement, §8.1.2.2; session-key derivation, labelled §8.1.2.2 by the pipeline but actually under §9.2 on page 45), the chain produced two schema-valid `TestCase` objects on the first attempt, in 18.8 s and 14.5 s. The content is good: correct SHALL classification, two-step inputs covering both branches of the conditional requirement, traceability field set exactly to the chunk id, preconditions that are real setup conditions. Every concrete fact the model added beyond the chunk (the BT SIG UUID `5c8256b5-…`, the HKDF salts `0x00`/`0x01`, the reference to NIST SP 800-38D) was checked and is present elsewhere in the norm. The three-agent design and the B2 schema-constrained prompt are therefore doing their job when the model is capable enough.

**What does not work.**

1. **The agent framework is the wrong tool for this job.** Each of the four agent calls is wrapped by `deepagents.create_deep_agent`, which prepends 7,692 characters (about 1,900 tokens) of generic "deep agent" instructions about todo lists, file editing and sub-agents to the system prompt, and binds eight tools the task never needs (`write_todos`, `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `task`) next to the one or two domain tools. With the configured `num_ctx=4096`, the Designer alone needs 1,132 tokens for its own prompt plus schema, so the deepagents overhead, the context package and the answer cannot fit; Ollama truncates silently. The framework also makes tool-calling mandatory, which excludes every local model that does not support tools (Ollama refuses `gemma3:4b` with "does not support tools") and forces small models into a calibration problem they are bad at.
2. **The A2 minimum-evidence guard is inverted.** `_NORMATIVE_MARKER` in `rag_router.py` is `\b(SHALL|MUST|SHOULD|MAY)\b` without `re.IGNORECASE`. Zero of the 1,202 chunks contain an upper-case modal, so the guard reports "no normative evidence" for every chunk and always falls back to `get_chunks_for_section`. Because of the section-label defect, that fallback for `8.1.2.2` returns 327 chunks, 127,332 characters, about 32,000 tokens, injected into a prompt with an 8,192-token window. The smoke run logged this fallback for both chunks.
3. **`tc_id` collisions.** Both test cases received `TC-18013-5-8.1.2.2-01`. The Designer numbers within a section it cannot see, and `pipeline.py` keys `tc_sections` by `tc_id`, so colliding cases overwrite each other's section mapping and would collide as coverage items in the plan.
4. **B3 depends on a 1.4 GB internet download.** `bert_score` loads `roberta-large` from Hugging Face on first use; the cache is empty on this machine, so the gate has never executed. It also doubles the number of Designer calls, which is the most expensive step. The smoke run stubbed it out.
5. **The Planner inherits the Axis A section labels** and therefore produces five clusters named after OID prefixes. Its shared-precondition heuristic (a modal plus a setup verb) never matched anything in the two-chunk run.
6. **Cost profile.** Five to seven LLM calls per chunk (Analyst, Router, two Designer candidates, plus retries and any tool round-trips). At the measured 15–19 s per chunk, a full 466-chunk run is 2–2.5 hours of cloud time, and every call carries the 1,900-token framework overhead.
7. **Tests measure plumbing, not quality.** All 38 tests mock the LLM. They cannot detect any of the defects above, and they passed throughout.

### 1.4 Summary table

| Component | Status | Evidence |
|---|---|---|
| PDF extraction | Works, noisy | 27 % whitespace, tables split from text |
| Section detection | **Broken** | 25 labels, 54 % OID |
| Two-pass chunking (A1) | Inactive | 1/466 full clauses |
| Hybrid retrieval (A2 index) | Works | correct top-3 in 4/4 probes |
| Evidence guard (A2 router) | **Inverted** | case-sensitive regex, 0 hits |
| Cross-refs / defined terms (A3) | Inactive | 0 and 22 junk |
| Normative detection | Weak | regex, NOTE/EXAMPLE, tables missed |
| Axis A evaluation | Not runnable | no ground truth |
| Agent chain content quality | Good with a 31B model | 2/2 valid, grounded |
| deepagents wrapper | Harmful | +1,900 tokens, 8 stray tools, tool-only models |
| B2 schema prompt + retry | Works | first-attempt validity 2/2 |
| B3 BERTScore gate | Never run | needs roberta-large download |
| B1 Planner | Inactive | garbage clusters |
| `tc_id` uniqueness | **Broken** | collision in 2 chunks |

### 1.5 Cross-standard generalisation — ISO, IETF RFC, OpenID Foundation

The Axis A extractor and chunker were run unchanged on the three standards in `data/input/`. The three documents come from three publishing pipelines and behave very differently.

| Property | ISO/IEC DIS 18013-5 | RFC 8949 (CBOR) | OpenID4VP 1.0 |
|---|---|---|---|
| Origin of the PDF | ISO typesetting (InDesign-style), 126 pages | Firefox "print to PDF" of the rfc-editor HTML page, 77 pages | Firefox "print to PDF" of the xml2rfc HTML page, 96 pages |
| PDF bookmark outline | **55 entries, matches TOC 100 %** (level 1 only) | none | none |
| Section headings in the text layer | yes, indented (`     7.3 nameSpace and DocType`) | **absent** — heading lines were not printed into the text layer; no extractor sees "1. Introduction" | yes, `5.9.2. Fallback` (trailing dot) |
| Heading recall, current regex | 0 real headings (62 hits, 59 are OIDs) | 0 | 0 |
| Heading recall, whitespace-tolerant regex vs own TOC | 0.89 (47 TOC entries; misses lower-case titles like `7.3 nameSpace…`) | 0.25 of 4 (TOC not in text layer either) | 0.98 (115 TOC entries) |
| Requirement keywords | lower-case `shall` 466, `should` 124, `may` 107, `shall not` 40 | BCP 14 boilerplate present but only 4 upper-case keyword lines survive in the text layer | **upper-case BCP 14**: MUST 205, MUST NOT 21, SHOULD 31, MAY 46, REQUIRED 30, OPTIONAL 33, RECOMMENDED 11 |
| Current `is_normative` result | 469 / 1,234 chunks | 99 / 773 chunks (mostly lower-case "may" in prose) | 236 / 993 chunks; `REQUIRED`, `OPTIONAL`, `RECOMMENDED` are not in the modal set and are ignored |
| Cross-reference style | `see 7.4.3` (64), `Annex B` (19) | `Section 3.4.1` (118), `[RFC8259]` (64) | `Section 5.1` (144), `[RFC6749]` (169) |
| Current cross-ref regex hits | 40 chunks, all wrong | 10 | 12 |
| Ligature damage with pdfplumber/pdfminer (`speci�cation`) | 0 | 72 words | **1,940 words** (`Veri�er`, `speci�cation`, `identi�er` — the domain vocabulary) |
| Whitespace share of chunk text (layout mode) | 27.9 % | 36.5 % | 39.7 % |
| Running header/footer surviving the 40-pt crop | none | `RFC 8949: … https://…` and `n of 77 9/21/26, 11:09 AM` on every page (154 lines) | `OpenID for Verifiable Presentations 1.0 https://…` and `n of 96` (96 lines) |
| Chunks with a real section label | 27 distinct (see §1.2) | 8 distinct, 586 empty, 181 labelled `65504.0` (a float from a table) | 2 distinct, 992 empty |
| Normative chunks kept whole (`is_full_clause`) | 1 / 469 | 0 / 99 | 0 / 236 |

Three conclusions follow.

1. **No single regex profile fits all three.** ISO uses lower-case modals, indented numbered headings, `see 7.4.3` references and a bookmark outline. IETF and OpenID use upper-case BCP 14 keywords (including `REQUIRED`, `RECOMMENDED`, `OPTIONAL`, `NOT RECOMMENDED`), `Section n` and `[RFCnnnn]` references, and trailing-dot heading numbers. Axis A needs a small per-family *document profile* (heading grammar, keyword set, keyword case, cross-reference grammar, informative-block markers), selected automatically from the front matter (the BCP 14 boilerplate sentence, the `ISO/IEC` header, the `openid.net` URL).
2. **Browser-printed PDFs are a lossy proxy for the real document.** The RFC print lost every heading and its table of contents; both prints lost the `fi` ligature under pdfminer-based extraction, and both carry print-time headers and footers on every page. RFC 8949 exists as canonical plain text and RFCXML v3 with `<section>` elements (checked at `rfc-editor.org/rfc/rfc8949.txt`: headings such as `3.4.1.  Standard Date/Time String` are present and keywords are upper-case). OpenID4VP 1.0 is an xml2rfc-generated HTML page with `id="section-5.1"` anchors on every heading. For these families the structured source is the right input and the PDF should be the fallback, not the default.
3. **The pipeline's parameters are ISO-specific in hidden ways.** `--skip-pages`, the 40-pt header crop, the `Presence` table convention, the modal set and the definitions parser were all tuned by hand on 18013-5 and silently misbehave on the other two.

### 1.6 Would a Markdown converter help? Measured answer

Three extraction back-ends were compared on the three PDFs (all runs single-threaded, memory-capped; no ML layout model was run, see the note at the end of this section).

| Back-end | ISO headings recovered | OpenID headings | RFC headings | Ligatures (`fi`) | Bookmarks / font sizes exposed | Time, 3 PDFs |
|---|---|---|---|---|---|---|
| `pdfplumber` (current, pdfminer-based, `layout=True`) | 0.89 recall with a tolerant regex; 28 % padding | 0.98 recall | none (not in text layer) | **broken** on both browser prints (1,940 + 72 words) | no | ~60 s |
| MarkItDown 0.1.7 (pdfminer-based) | **0 Markdown headings** — plain text only | 0 | 0 | broken (1,444 + 74 words) | no | 47 s |
| PyMuPDF 1.28 (`fitz`, plain text + `dict` spans) | bookmarks: 47/47 TOC entries (1.0); font-size/bold: 138 numbered heading lines but sub-headings split as `6.3.1\t` + `Data model` on two lines (needs a one-line join) | font+regex: 0.70 recall, 12 spurious; regex alone: 1.0 recall, 155 spurious (TOC pages and table rows) | none (not in text layer) | **intact** (0 replacement characters) | yes: `get_toc()`, per-span font size and bold flag, links | **5 s** |
| `pymupdf4llm` (Markdown output) | not measured: version 1.28 pulls in the `pymupdf-layout` model, which crashed the machine | | | | | |

**Answer.** A "Markdownify-style" converter is only as good as the structure it can see, and for PDFs that structure is not in the file as Markdown; it has to be inferred from bookmarks, font sizes and line geometry. MarkItDown does no inference for PDF (it is pdfminer text with no headings), so it would make Axis A worse. PyMuPDF is the right low-level back-end: it is ten times faster, keeps ligatures, exposes the ISO bookmark outline and per-line font sizes, and its Markdown front-end `pymupdf4llm` can be used *without* the layout model once the heading heuristic is driven by our own document profile. Model-based converters (Docling [23, 24], MinerU [25]) are the state of the art on the OmniDocBench parsing benchmark [26] and recover title hierarchy on scanned or complex layouts, but they need a GPU or a lot of CPU and RAM, and on born-digital standards their advantage over bookmark plus font-size heuristics is small; Adhikari and Agarwal's comparison of ten PDF parsers finds PyMuPDF and pypdfium the best text extractors on born-digital documents, with learning-based tools only paying off on scientific and patent layouts [27]. The MinerU-Popo work shows that title-hierarchy reconstruction is a post-processing problem on top of any extractor and improves RAG accuracy when done as a separate step [28], which is exactly where a document profile belongs.

For the two HTML-born standards the answer is different: convert the *HTML* (or RFCXML) with MarkItDown or a plain HTML-to-Markdown step. There the headings, ids, tables and cross-reference anchors are explicit, and the converter is lossless.

---

## 2. Axis A — Propositions

### A-V2-1 — Fix structure recovery before anything else  **[NEEDS APPROVAL]**

**Gap.** Every structure-dependent feature is inactive because headings are not detected (§1.2).

**SoTA evidence.** The 2026 reproduction study of chunking strategies by Zhou et al. finds that for in-corpus retrieval (the setting of this project: one query against the whole standard) simple structure-based segmentation outperforms LLM-guided and semantic chunkers, and that segmentation method matters more than chunk size [1]. MultiDocFusion (EMNLP 2025) shows that rebuilding the document's section hierarchy into a tree before chunking raises retrieval precision by 8–15 % on long industrial documents [2]. The Adaptive Chunking framework defines five intrinsic, label-free chunk-quality metrics (References Completeness, Intra-chunk Cohesion, Document Contextual Coherence, Block Integrity, Size Compliance) and shows that selecting a chunker on those metrics lifts RAG answer correctness from 62–64 % to 72 % [3].

**Proposition.**
1. Switch the PDF back-end from `pdfplumber` to PyMuPDF (`fitz`) in `axis_a/pdf_extractor.py`, keeping the same `RawPage` interface. Use `get_text("dict")` so every line carries its font size and bold flag, read `doc.get_toc()` for the bookmark outline, and keep `find_tables()` from pdfplumber only if PyMuPDF's `find_tables()` proves worse on the ISO data-element tables. This removes the ligature damage (§1.6), the 28–40 % whitespace padding, and cuts extraction time by an order of magnitude.
2. Introduce a *document profile* (`axis_a/profiles.py`, one dataclass per family: `iso`, `ietf`, `openid`, `generic`) selected automatically from the front matter. A profile holds: the heading grammar (ISO `7.3.1 Title` with indentation and annex letters; IETF/OpenID `5.9.2. Title` with a trailing dot), the OID/float exclusion rule, the keyword set and case (lower-case `shall/should/may` for ISO; upper-case BCP 14 including `REQUIRED`, `RECOMMENDED`, `OPTIONAL`, `NOT RECOMMENDED` for IETF and OpenID), the informative-block markers (`NOTE`, `EXAMPLE` for ISO; "non-normative example" for OpenID), the cross-reference grammar (`see 7.4.3`, `Section 3.4.1`, `[RFC6749]`, `Annex B`), and the running header/footer patterns to strip (`n of 77`, print timestamps, `© ISO/IEC`).
3. Recover headings by three independent signals, merged in this order: PDF bookmarks when present (ISO: 47/47), then lines whose font size or bold flag exceeds the body text and that match the profile's heading grammar, then the grammar alone on lines outside the table-of-contents pages. Join a number-only line with the following line before matching (PyMuPDF splits `6.3.1\t` / `Data model`). Accept lower-case titles (`7.3 nameSpace and DocType`, missed today).
4. Emit a `section_path` (e.g. `8 > 8.1 > 8.1.2 > 8.1.2.2 > title`) in each chunk and prepend it to the text before embedding ("contextual chunk header"). This is the cheapest form of the late-chunking idea of Günther et al. [4] and needs no new model.
5. Report, per standard, heading recall against the document's own table of contents (the protocol used in §1.5) and the five Adaptive Chunking metrics [3] for the baseline splitter and the fixed splitter. This gives the paper a quantitative, three-standard Axis A comparison that does not wait for the human ground truth.

**Expected effect.** A1, A3 and B1 become active without further changes on all three standards. `get_chunks_for_section` becomes usable, which also repairs the A2 evidence guard fallback. The profile mechanism is the generalisation argument for the paper: the pipeline is parameterised by the publishing convention, not by one standard.

### A-V2-1b — Ingest the structured source when one exists  **[NEEDS APPROVAL]**

**Gap.** For RFC 8949 no PDF extractor can recover the headings, because the browser print did not put them in the text layer (§1.5). The same print step damaged ligatures and added page furniture to both HTML-born documents.

**SoTA evidence.** The 2025 systematic review of RAG recommends provenance-aware pipelines that keep the document's native structure [12]; MultiDocFusion's gains come from an explicit hierarchical tree that an HTML or XML source provides for free [2]; Zheng et al. build their RFC oracle from the structured RFC text precisely so that every derived requirement traces to one section [22].

**Proposition.** Add an `axis_a/source_loader.py` that accepts `.pdf`, `.html`, `.xml` (RFCXML v3) and `.txt` (RFC plain text). For HTML use MarkItDown's HTML converter (already installed in the comparison environment) to obtain Markdown with `#` headings and tables; for RFCXML read `<section anchor="…"><name>` directly; for RFC text use the `n.  Title` grammar. Everything downstream (chunker, profiles, indexer) consumes the same `RawPage`-like page list, so the change is confined to loading. Keep the PDF path as the fallback for standards that only exist as PDF (ISO). Document in the paper that the three families were ingested from their canonical formats.

### A-V2-2 — Size chunks in tokens and stop skipping the front matter  **[NEEDS APPROVAL]**

**Gap.** Chunks are 105 tokens on average, far below the operating range where embedding models retain context; §3 (definitions) and §4–6.3 are skipped.

**SoTA evidence.** Bhat et al. (2025) find across multiple datasets and embedding models that 64–128-token chunks suit short factoid answers, while documents requiring broader context retrieve best at 512–1,024 tokens, and that the optimum depends on the embedding model [5]. `nomic-embed-text` has an 8,192-token context, so there is no technical reason for 105-token chunks.

**Proposition.** Measure `chunk_size` with the tokenizer (`tiktoken` `cl100k_base` is a good enough proxy; it is already a transitive dependency of langchain) at 384 tokens with 48-token overlap, applied only in pass 2 of the two-pass splitter. Keep pages 10–13 and skip only the cover, contents and foreword (pages 1–9) so that §3 definitions and §4–6 are indexed. Rewrite `extract_definitions_section` for the ISO three-line form: a `3.n` line, then the term line, then the definition until the next `3.n`.

### A-V2-3 — Treat table rows as requirement units  **[NEEDS APPROVAL]**

**Gap.** ISO 18013-5's data-element requirements live in tables with a `Presence` column (M/O/R); they carry no modal verb and are invisible to the current detector.

**SoTA evidence.** On 3GPP specifications, which interleave tables and text exactly as ISO standards do, Roychowdhury et al. show that the row-level representation with the table header repeated in every row gives the best retrieval performance among all table serialisations tested [6]. Al Hilmi et al. (2026) show that deterministic table parsing with an LLM fallback beats LLM-only extraction on accuracy and cost for tabular PDFs processed with local Ollama models [7].

**Proposition.** In `pages_to_marked_text`, serialise each extracted table row as one line `Table N | <header1>=<cell1>; <header2>=<cell2>; …` using the first row as header. In the chunker, treat each such line as its own atomic chunk when the table has a `Presence`/`Mandatory` column, set `is_normative=True` and `modals=["shall"]` when the cell is `M`, and store `requirement_kind="table_presence"` in a new `RequirementChunk` field. The Designer then receives a requirement such as "Table 3: `family_name` presence M, encoding tstr", which is exactly what a data-element conformance test needs.

### A-V2-4 — Sentence-level normative classification instead of a chunk-level regex  **[NEEDS APPROVAL]**

**Gap.** `is_normative` is a chunk-level regex hit; NOTE/EXAMPLE text and descriptive "may" count as requirements; the spaCy sentence segmentation is computed and thrown away.

**SoTA evidence.** A 2026 cost-aware comparison of fine-tuned encoders against zero/few-shot LLM prompting for fixed-label text classification finds that BERT-family encoders match or beat LLMs at one to two orders of magnitude lower cost and latency [8]. The CiRA tool shows that conditional requirements ("If A then B") can be decomposed automatically into test variables with 84.5–92.3 % accuracy, i.e. that sentence-level requirement units are the right granularity for test derivation [9]. SpecGPT segments 3GPP specifications into meaningful paragraphs before extraction and reports that segmentation plus domain-informed prompting is what makes extraction reliable [10].

**Proposition.** Use the sentence list that `annotate_text` already produces as the unit of normative detection: a chunk is normative if at least one of its sentences is normative, and each normative sentence is stored in a new `RequirementChunk.requirements: list[str]` field. Take the keyword set, its case sensitivity and the informative-block markers from the document profile (A-V2-1): for IETF and OpenID documents only upper-case BCP 14 keywords count, which removes the 83 lower-case "may" false positives measured on RFC 8949 and adds the `REQUIRED`/`OPTIONAL`/`RECOMMENDED` requirements (74 occurrences in OpenID4VP) that are invisible today; for ISO, lower-case modals count but sentences inside NOTE/EXAMPLE blocks do not. Record the matched keyword and its strength (`MUST`/`SHALL` = mandatory, `SHOULD`/`RECOMMENDED` = recommended, `MAY`/`OPTIONAL` = optional) so that `requirement_type` is derived by rule rather than by the LLM. Keep the keyword rule as the sentence classifier for now, but add a 200-sentence hand-labelled set drawn from all three standards so that a fine-tuned small encoder [8] can replace it in a later iteration and the paper can report precision/recall of normative detection per family.

### A-V2-5 — Make `evaluate.py` runnable now with a synthetic, reference-free protocol  **[NEEDS APPROVAL]**

**Gap.** No ground truth exists, so no Axis A number can be reported.

**SoTA evidence.** Ragas provides reference-free RAG metrics (context precision, context recall, faithfulness) that do not require human annotation [11]. The 2025 systematic review of RAG (128 studies) notes that retrieval diagnostics such as Recall@k and MRR@k, computed on synthetic query sets, are now the standard first-line evaluation before human studies [12].

**Proposition.** Add `scripts/make_synthetic_gt.py`: for each normative sentence (A-V2-4), ask the cloud model to write one natural-language test-engineer query for it; the sentence's chunk id is the relevance label. Evaluate Recall@5 and MRR for dense-only, BM25-only and RRF on this set, and for the baseline versus the fixed chunker. Keep the manual 200-clause annotation as the confirmatory study, but the synthetic set lets every chunking or retrieval change be measured immediately.

---

## 3. Axis B — Propositions

### B-V2-1 — Remove the deep-agent wrapper; move retrieval and control into code  **[NEEDS APPROVAL]**

**Gap.** §1.3 items 1, 2 and 6: 1,900 tokens of unrelated instructions and eight stray tools per call, mandatory tool calling, an inverted guard, unbounded fallback context.

**SoTA evidence.** Ahn and Kim (2026) show, with a fixed model and a varied enforcement layer, that guarantees owned by code (schemas, validators, source-grounding checks) hold across three hosted models on 270/270 runs, while the same guarantees expressed as prompt instructions leak, and that a bolt-on guardrail over-refuses; their conclusion is to move deterministic behaviour out of prompts and agent loops into code around a replaceable model [13]. Zhao et al. (2026) diagnose multi-turn tool calling and find that the dominant failure mode is action-class miscalibration (deciding whether to call a tool at all), which small and mid-size open models get wrong even when their tool execution is correct [14]. Cao et al. (2026) show that 0.5–3B models win on a performance-efficiency ratio for narrow tasks once the task is framed as plain generation rather than agentic tool use [15].

**Proposition.**
1. Replace `deepagents_compat.Agent` with a direct `ChatOllama.invoke` on a system prompt plus one user message in all three per-chunk agents. No tools are bound.
2. Do the retrieval deterministically in `pipeline.py` before the Analyst call: hybrid search on the chunk text (top 3), the chunk's section siblings (once A-V2-1 makes sections real), and the resolved cross-references and definitions from Axis A. Inject them as labelled context blocks. Cap the injected context at a fixed token budget (2,000 tokens) so that no prompt can exceed the window.
3. Delete the inverted `_NORMATIVE_MARKER` guard; the deterministic retrieval always includes the source chunk, so the "zero normative evidence" case cannot occur.
4. Read the model name, base URL and API key from environment variables (`OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, loaded from `.env`) in `get_llm()`, so that the same code runs against local Ollama or Ollama cloud. Update the "no internet at runtime" statement in `AGENTS.md`, `SPEC.md` and the paper to "no internet except the configured Ollama endpoint".

**Expected effect.** Roughly 2,000 fewer input tokens per call, three calls per chunk instead of five to seven, and the pipeline becomes runnable with any chat model, including local models without tool support, which the deepagents design currently excludes.

### B-V2-2 — Enforce JSON output in code, keep the reflective retry  **[NEEDS APPROVAL]**

**Gap.** Output validity currently relies on the prompt, fence stripping and retries. Ollama's server-side JSON-schema constraint (`format=<schema>`) was tested against Ollama cloud on 2026-09-21 with `gemma4:31b` and `gpt-oss:20b`: the schema was ignored and both models returned fenced Markdown. Constrained decoding is therefore not available on the cloud path and cannot be assumed.

**SoTA evidence.** SchemaBench (Lu et al., 2025) shows that even current LLMs frequently fail to produce schema-valid JSON and that fine-grained validator feedback is what improves them [16]. Matveev (2026) finds that plain JSON generation with validation gives the best final accuracy, with constrained decoding giving lower token usage but degraded accuracy on some models [17]. Le (2026) shows that the wording of schema keys acts as an instruction channel and changes accuracy by itself [18].

**Proposition.** Keep B2's schema-in-prompt and field-level reflective retry; they worked first time in the smoke run. Add a code-level pre-validator that (a) strips fences and any prose before the first `{`, (b) fills `actual_results=""`, `traceability` and `coverage_item_id` deterministically, and (c) assigns `tc_id` deterministically from the chunk id and section (`TC-<norm>-<section>-<chunk index>`), which removes the collision in §1.3 item 3. Rename schema keys with descriptive wording where Le's result suggests it matters (`inputs` becomes `test_steps_with_expected_results`) and measure first-attempt validity on 50 chunks with and without the rename.

### B-V2-3 — Replace the BERTScore gate with an embedding-distance gate plus an LLM judge  **[NEEDS APPROVAL]**

**Gap.** B3 has never run (needs a 1.4 GB download), doubles the most expensive call, and its inter-candidate agreement is only weakly related to correctness.

**SoTA evidence.** Wang et al. (TOSEM 2025) evaluate seven LLM-as-a-judge methods on software-engineering artefacts and find that output-based judging reaches Pearson correlations of 0.81 (translation) and 0.69 (generation) with human scores, far above lexical or embedding metrics, and that the score distributions resemble human ones [19]. The voice-agent judge benchmark (2026) adds the caveat that judge reliability is metric-dependent and should be calibrated per rubric dimension with a human sample [20].

**Proposition.** Generate one Designer candidate per chunk. Compute the cosine similarity between the `nomic-embed-text` embedding of the test case (objective plus expected results) and the source chunk; this is the same signal Axis C already computes as `traceability_confidence`, moved forward. Run one LLM-judge call with the SPEC's five human-evaluation dimensions (completeness, correctness, clarity, traceability, executability, 1–5 each) and the source chunk as reference. Store both in `TestCase.notes` as structured `quality: {...}`. Calibrate the judge against the 30-case human evaluation already planned in `SPEC.md §5`, reporting the per-dimension correlation as in [19, 20]. This removes `bert-score` from the requirements.

### B-V2-4 — Generate one test case per atomic requirement, not per chunk  **[NEEDS APPROVAL]**

**Gap.** A chunk is an arbitrary 105-token window; a single chunk can hold three SHALL statements or half of one. The smoke run's first chunk contained two requirements (advertise UUID, scan for UUID) and produced one test case covering both.

**SoTA evidence.** iPanda (2025), the closest analogue in protocol conformance testing, generates test cases from a keyword-indexed list of specification requirements and reports 4.7–10.8× higher pass@1 than prompting on raw specification text [21]. Zheng et al. (2025) validate protocol parsers from RFC text and stress that each derived oracle must trace to one specification sentence for the traceability problem to be solvable [22]. CiRA derives a minimal covering test set from one conditional sentence at a time [9].

**Proposition.** Once A-V2-4 provides `requirements: list[str]` per chunk, iterate the Designer over requirement sentences, passing the sentence as the target and the chunk plus retrieved context as background. Keep `traceability` as `<chunk_id>#<sentence index>`. This also gives the paper an honest ISO coverage metric: test cases per normative sentence rather than per window.

### B-V2-5 — Make the Planner deterministic and section-based  **[NEEDS APPROVAL]**

**Gap.** K-means over embeddings with `k` inferred from broken labels; cluster names are OID prefixes.

**SoTA evidence.** The same structure-first result as A-V2-1 [1, 2]: for regulatory corpora the document's own hierarchy is the strongest grouping signal. The AutoMT and ALMAS results cited in `IMPROVEMENTS.md` for B1 concern an upfront relation-extraction or planning pass, not clustering; nothing in that evidence requires k-means.

**Proposition.** Derive `feature_set` from the level-2 section path (`8.1 Device engagement`, `9.1 Session encryption`, `Annex C Certificate profiles`) recovered by A-V2-1. Drop the embedding step and the `scikit-learn`/FAISS k-means code. Keep shared-precondition extraction but run it over the section's normative sentences (A-V2-4). If a later experiment wants embedding clusters, they can be compared against this deterministic grouping as a baseline.

---

## 4. Suggested order and what each step unblocks

| Order | Proposition | Unblocks | Effort |
|---|---|---|---|
| 1 | A-V2-1 PyMuPDF back-end, document profiles, three-signal heading recovery | A1, A3, B1, `get_chunks_for_section`, A-V2-3/4, B-V2-5, all three standards | 1½ days |
| 2 | B-V2-1 remove deepagents, code-side retrieval, env-based model config | any model, cost, reproducibility | 1 day |
| 3 | B-V2-2 deterministic ids and pre-validator | plan integrity | ½ day |
| 4 | A-V2-1b structured-source loader (HTML / RFCXML / txt) | lossless RFC and OpenID ingestion | ½ day |
| 5 | A-V2-2 token sizing and front matter | retrieval quality, definitions | ½ day |
| 6 | A-V2-4 sentence-level, profile-driven normative units | B-V2-4, coverage metric, BCP 14 keywords | 1 day |
| 7 | A-V2-5 synthetic ground truth (three standards) | first Axis A numbers | ½ day |
| 8 | A-V2-3 table rows | data-element coverage | 1 day |
| 9 | B-V2-3 judge gate | quality numbers, drops bert-score | 1 day |
| 10 | B-V2-4 per-requirement generation | honest coverage | ½ day |
| 11 | B-V2-5 deterministic planner | hierarchy | ½ day |

Steps 1–3 are bug fixes in substance and should be applied before any experiment is reported; the two-chunk smoke run shows that the generation quality is already publishable once the plumbing stops corrupting the inputs. Step 4 is what makes the "works on any standard" claim honest for the two HTML-born families.

---

## 5. Bibliography (new in this iteration)

[1] Y. Zhou, S. Wang, B. Koopman, and G. Zuccon, "Beyond Chunk-Then-Embed: A Comprehensive Taxonomy and Evaluation of Document Chunking Strategies for Information Retrieval," arXiv:2602.16974, 2026.

[2] J. Shin, C. Park, J. Park, J. Seo, and H. Lim, "MultiDocFusion: Hierarchical and Multimodal Chunking Pipeline for Enhanced RAG on Long Industrial Documents," in *Proc. EMNLP 2025*, pp. 1062. DOI: 10.18653/v1/2025.emnlp-main.1062.

[3] P. R. de Moura Júnior, J. Lelong, and A. Blangero, "Adaptive Chunking: Optimizing Chunking-Method Selection for RAG," arXiv:2603.25333, 2026. *(Already [13] in IMPROVEMENTS.md; reused here for its intrinsic metrics.)*

[4] M. Günther, I. Mohr, D. J. Williams, B. Wang, and H. Xiao, "Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models," arXiv:2409.04701, 2024 (v3 2025).

[5] S. R. Bhat, M. Rudat, J. Spiekermann, and N. Flores-Herr, "Rethinking Chunk Size for Long-Document Retrieval: A Multi-Dataset Analysis," arXiv:2505.21700, 2025.

[6] S. Roychowdhury, S. Soman, H. G. Ranjani, A. Sharma, N. Gunda, and S. K. Bala, "Evaluation of Table Representations to Answer Questions from Tables in Documents: A Case Study using 3GPP Specifications," arXiv:2408.17008, 2024.

[7] M. A. Al Hilmi, N. Khare, N. F. Iglesias, K. A. Cahyanto, A. Al Afghani, and M. Yuliadi, "Tabular PDF Information Extraction with Local LLMs and Layout-Aware Parsing: A Reliability Evaluation," arXiv:2604.00003, 2026.

[8] A. A. Valdes Gonzalez, "Cost-Aware Model Selection for Text Classification: Multi-Objective Trade-offs Between Fine-Tuned Encoders and LLM Prompting in Production," arXiv:2602.06370, 2026.

[9] J. Frattini, J. Fischbach, and A. Bauer, "CiRA: An Open-Source Python Package for Automated Generation of Test Case Descriptions from Natural Language Requirements," in *Proc. IEEE REW 2023*. DOI: 10.1109/REW57809.2023.00019.

[10] M. Zhang, R. Feng, H. Tang, Y. Zhao, J. Yang, H. Qiu, and Q. Liu, "Automated Extraction of Protocol State Machines from 3GPP Specifications with Domain-Informed Prompts and LLM Ensembles," arXiv:2510.14348, 2025.

[11] S. Es, J. James, L. Espinosa-Anke, and S. Schockaert, "Ragas: Automated Evaluation of Retrieval Augmented Generation," arXiv:2309.15217, 2023 (v2 2025).

[12] A. Brown, M. Roman, and B. Devereux, "A Systematic Literature Review of Retrieval-Augmented Generation: Techniques, Metrics, and Challenges," *Big Data and Cognitive Computing*, vol. 9, no. 12, 320, 2025. DOI: 10.3390/bdcc9120320.

[13] J. Ahn and M. Kim, "From Prompts to Contracts: Harness Engineering for Auditable Enterprise LLM Agents," arXiv:2607.08028, 2026.

[14] K. Zhao et al., "Calibration is the Bottleneck: An Action-Class Diagnostic of Multi-Turn Tool-Calling," arXiv:2609.00949, 2026.

[15] J. Cao, Y. Ma, X. Li, Q. Ren, and X. Chen, "Task-Specific Efficiency Analysis: When Small Language Models Outperform Large Language Models," arXiv:2603.21389, 2026.

[16] Y. Lu et al., "Learning to Generate Structured Output with Schema Reinforcement Learning," arXiv:2502.18878, 2025.

[17] I. Matveev, "Token-Oriented Object Notation vs JSON: A Benchmark of Plain and Constrained Decoding Generation," arXiv:2603.03306, 2026.

[18] Y. Le, "Schema-Key Wording as an Instruction Channel in Structured Generation under Constrained Decoding," arXiv:2604.14862, 2026.

[19] R. Wang, J. Guo, C. Gao, G. Fan, C. Y. Chong, and X. Xia, "Can LLMs Replace Human Evaluators? An Empirical Study of LLM-as-a-Judge in Software Engineering," *ACM TOSEM*, 2025. DOI: 10.1145/3728963.

[20] A. Purwar, S. Singh, and K. Srivastava, "Benchmarking LLM Judges for Voice-Agent Evaluation: Reliability, Calibration, and Human Oversight," arXiv:2608.24314, 2026.

[21] X. Sun et al., "iPanda: An LLM-based Agent for Automated Conformance Testing of Communication Protocols," arXiv:2507.00378, 2025.

[22] M. Zheng, D. Xie, Q. Shi, C. Wang, and X. Zhang, "Validating Network Protocol Parsers with Traceable RFC Document Interpretation," *Proc. ACM Softw. Eng.* (FSE 2025). DOI: 10.1145/3728955.

[23] C. Auer et al., "Docling Technical Report," arXiv:2408.09869, 2024 (v5 Dec. 2024).

[24] N. Livathinos et al., "Docling: An Efficient Open-Source Toolkit for AI-driven Document Conversion," arXiv:2501.17887, 2025.

[25] B. Wang et al., "MinerU: An Open-Source Solution for Precise Document Content Extraction," arXiv:2409.18839, 2024.

[26] L. Ouyang et al., "OmniDocBench: Benchmarking Diverse PDF Document Parsing with Comprehensive Annotations," arXiv:2412.07626, 2024 (v2 2025).

[27] N. S. Adhikari and S. Agarwal, "A Comparative Study of PDF Parsing Tools Across Diverse Document Categories," arXiv:2410.09871, 2024 (v2 2025).

[28] B. Xu et al., "MinerU-Popo: Universal Post-Processing Model for Structured Document Parsing," arXiv:2605.24973, 2026.

---

## Appendix — Reproduction of the measurements

- Chunk statistics: `data/output/index/faiss_index/chunks.jsonl` (1,202 lines), counted with a short Python script over `section`, `is_full_clause`, `context_refs`, `defined_terms`, `text`.
- Header recount: `pages_to_marked_text(extract_pages(pdf, skip_pages=set(range(1,14))))` then `re.findall(r"(?m)^[ \t]*(\d{1,2}(?:\.\d{1,2}){1,4})\s+[A-Z][^\n]{2,80}$", text)` and the annex variant `^[ \t]*([A-H](?:\.\d{1,2}){1,4})\s+[A-Z]…`.
- deepagents overhead: a capturing `BaseChatModel` passed to `deepagents_compat.Agent` records the system message (7,692 chars) and the bound tool names.
- Guard bug: `axis_b.agents.rag_router._NORMATIVE_MARKER.flags` has no `IGNORECASE`; `grep -c` of upper-case modals over `chunks.jsonl` is 0.
- Smoke run: Analyst → Router → Designer on chunks `iso_iec_18013_5_0200` and `_0298`, model `gemma4:31b` via `https://ollama.com`, `num_ctx=8192`, BERTScore stubbed with `difflib`; per-chunk wall time 18.8 s and 14.5 s.
- Constrained-output probe: `POST https://ollama.com/api/chat` with `"format": {<JSON schema>}` for `gemma4:31b` and `gpt-oss:20b`; both returned fenced Markdown, not JSON.
- Cross-standard run (§1.5): `pages_to_marked_text(extract_pages(pdf, skip_pages))` then `chunk_document()` on each PDF with skip pages 1–9 for ISO and none for the others; keyword counts from `\b(shall not|…|may)\b` (case-sensitive lower) and `\b(MUST NOT|…|OPTIONAL)\b` (upper); ligature damage counted as U+FFFD characters plus `speci�`-type fragments.
- Heading recall (§1.5, §1.6): ground truth = numbered entries parsed from each document's own table-of-contents pages (ISO pp. 3–4, 47 entries; OpenID pp. 1–4, 115 entries; RFC: no TOC in the text layer). Recall = share of those entries found as a heading by the detector; "spurious" counts detector hits absent from the TOC, which for ISO and OpenID are mostly genuine level-4 headings the TOC does not list, so it over-states false positives.
- Converter comparison (§1.6): `pdfplumber 0.11.9`, `markitdown 0.1.7` (pdfminer.six 20260107), `pymupdf 1.28.2` without `pymupdf-layout`; each run under `nice -n 19 taskset -c 0,1` with `ulimit -v 4000000`. `pymupdf4llm` was abandoned after its layout model crashed the machine.
- Structured sources: `https://www.rfc-editor.org/rfc/rfc8949.txt` contains `1.  Introduction`, `3.4.1.  Standard Date/Time String` and upper-case BCP 14 keywords; `https://openid.net/specs/openid-4-verifiable-presentations-1_0.html` is xml2rfc HTML with `id="section-5.1"`-style heading anchors.
