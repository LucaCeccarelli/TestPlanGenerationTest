# Measuring coverage of a generated test suite against a human-written reference suite

Scope note: this file covers (0) the genre of the reference suite — an ISO/IEC 9646-style abstract
test-purpose suite — and what that genre licenses for *structural* rather than textual matching,
(1) suite-to-suite matching methods, (2) LLM-as-judge reliability for equivalence judgments,
(3) adequacy criteria that do not need a reference suite, (4) numbers reported by comparable automated
systems, (5) whether 85–90 % is plausible, (6) reference-suite evaluation methodology (version
mismatch, partial credit, reporting conventions). All findings are generic to "a standard with a
published conformance suite"; nothing below depends on the mDL domain.

---

## The genre of the reference suite: structural matching of abstract test purposes

### Takeaway
The reference suite's genre has a name, a standard and a formal notation, and that is the single most
useful finding for the measurement question. A labelled-field record with ID / SUT / Purpose /
Reference / Technology / Profile / Preconditions / Test scenario / Expected results is a **Test Purpose
in the ISO/IEC 9646-2 TSS&TP tradition**, and ETSI standardised a notation for exactly this record —
**TPLan (ETSI ES 202 553)** — whose block structure is `header (TP id, Summary, RQ ref, Config, TD ref)`
+ `with { preconditions } ensure that { when { stimulus } then { expected response } }`. That is
field-for-field the tuple the generated artefacts already carry. So matching on prose is not required
and is not the genre's own idiom: the defensible protocol is **block-wise structural matching** —
agree on RQ ref / clause, on the object or data item, on the `when` (applicability condition and
stimulus), and on the `then` (expected outcome) — with text similarity used only inside a block, and
the LLM used only where a block's content is free prose. Partial credit then falls out of the notation
rather than being invented: a match can be scored per block.

### Cited Findings
- **ISO/IEC 9646-2:1994** sets requirements for the production of *system-independent conformance test
  suites*, applying to **abstract test cases** that check conformance of an implementation to the
  relevant **static and/or dynamic conformance requirements** by controlling and observing protocol
  behaviour; its structure runs ICS proformas → conformance requirements → **TSS&TP** → abstract test
  method → ATS specification, so **traceability between these layers is part of the framework**, and
  the TSS&TP part contains its own sub-clauses on test suite structure, test purposes, **coverage
  (clause 10.4)** and TSS&TP compliance —
  [ISO/IEC 9646-2:1994 preview/TOC (ANSI
  webstore)](https://webstore.ansi.org/preview-pages/ISO/preview_ISO+IEC+9646-2-1994.pdf) ·
  [CSA ISO/IEC 9646-2 listing](https://infostore.saiglobal.com/en-us/Standards/CSA-ISO-IEC-9646-2-0-360786_SAIG_CSA_CSA_822784/)
  — N.B. the clause-number detail came from search-result metadata; the preview PDF itself returned
  HTTP 403 and the normative text was not read (see Gaps).
- **ETSI TPLan (ES 202 553)** is a structured notation from ETSI TC MTS for writing Test Purposes; a TP
  "describes **what to test, not how**"; it uses a small set of communications-oriented keywords,
  extensible per technology area, and suits **both conformance and interoperability testing** —
  [ETSI CTI TPLan page](https://portal.etsi.org/CTI/ApproachToTesting/TestLanguages/TPLAN.htm) ·
  [ES 202 553 v1.1.1 (PDF)](https://www.etsi.org/deliver/etsi_ES/202500_202599/202553/01.01.01_50/es_202553v010101m.pdf)
- **The TPLan TP structure**, which is the citable structural decomposition:
  - header fields: **TP id, Summary, RQ ref** (the requirement tested), **Config** (test
    configuration), **TD ref** (related test description);
  - **`with { … }`** — preconditions;
  - **`ensure that { … }`** — the expected behaviour, composed of **`when { … }`** (the stimulus) and
    **`then { … }`** (the expected response);
  - keywords `with`, `ensure that`, `when`, `then` plus domain phrases
  — [ETSI CTI TPLan page](https://portal.etsi.org/CTI/ApproachToTesting/TestLanguages/TPLAN.htm)
- A worked TPLan TP shows the full record shape: `TP_COR_1100_01`, summary "EUT reassembles a
  fragmented packet of an original length less than 1500 octets", precondition fixing the path MTU at
  1280 octets, `when` QE1 is requested to send data needing 1288–1492 octets, `then` the EUT indicates
  it received the same data unchanged, with header references `RQ_001_1100`, `CF_COR_23`,
  `TD_COR_1100_01` — [ETSI CTI TPLan page](https://portal.etsi.org/CTI/ApproachToTesting/TestLanguages/TPLAN.htm)
- **Claimed benefits of the structured form**, all of which are measurement benefits in your setting:
  consistent TP / assertion / requirement descriptions with less room for misinterpretation; **clear
  identification of preconditions, stimuli and responses**; simpler migration from requirements to TPs;
  automatic syntax checking; and a basis for a **transfer format and software-tool representation** —
  [ETSI CTI TPLan page](https://portal.etsi.org/CTI/ApproachToTesting/TestLanguages/TPLAN.htm)
- TPLan's scope is described as a notation with a **fixed structure and a common set of English
  keywords**, oriented to reactive black-box communication systems; its use is optional, but if a
  specification adopts it the standard's requirements apply —
  [ES 202 553](https://www.etsi.org/deliver/etsi_ES/202500_202599/202553/01.01.01_50/es_202553v010101m.pdf)
  (via [ETSI page](https://portal.etsi.org/Services/CentreforTestingInteroperability/ETSIApproach/TestingLanguages/TPLan))
- One listing marks ES 202 553 as **inactive**, and ETSI's later direction is **TDL (Test Description
  Language, ES 203 119)**, which keeps the same layout — a `Test Purpose` block containing
  `ensure that { when {…} then {…} }` —
  [GlobalSpec ES 202 553 listing](https://standards.globalspec.com/std/1169735/es-202-553) ·
  [ETSI STF 476 TDL report](https://docbox.etsi.org/STF/Archive/STF476_MTS_TDL2/Public/STF%20476%20-%20Task%204%20Report.pdf) ·
  [TDL overview (BME)](https://www.tmit.bme.hu/sites/default/files/AG_TDL_2018_Eng.pdf) ·
  [STV-TDL slides](https://tdl.etsi.org/images/STV-TDL_v08.pdf)
- Early tool work on the notation (TestCom 2007) treats TPLan TPs as machine-processable artefacts
  rather than prose — [Schulz, Wiles, Randall, TestCom 2007
  (PDF)](https://dl.ifip.org/index.html/db/conf/pts/testcom2007/SchulzWR07.pdf)
- An ITU-T workshop deck presents the same conformance-TP skeleton — header, preconditions, stimulus,
  expected response — as the basic structure —
  [ITU-T workshop PDF](https://itu.int/dms_pub/itu-t/oth/06/02/T06020000020001PDFE.pdf)
- **Per-side splitting is established practice** in this genre: ETSI's ETS 300 064 series publishes the
  TSS&TP in separate documents per system under test — Part 3 "TSS&TP specification for the user",
  Part 5 "TSS&TP specification for the network" — which makes per-SUT coverage comparison the natural
  reporting unit — [ETS 300 064-3](https://etsi.org/deliver/etsi_i_ets/300001_300099/30006103/01_60/ets_30006103e01p.pdf) ·
  [ETS 300 064-5](https://www.etsi.org/deliver/etsi_i_ets/300001_300099/30006405/01_60/ets_30006405e01p.pdf)
- **Structural signals beat text similarity when matching test artefacts** — the one retrieved result
  with >90 % precision/recall on requirements↔test-case linking used *realised functional features in
  code* rather than prose, versus recall <40 %/precision <30 % for text-only IR (LSI, LDA, BM25, word
  vectors) on bug-report↔manual-test-case linking — [ASE 2011 (Ziftci &
  Krueger)](https://www.se.cs.uni-saarland.de/conferences/ASE/ase2011/www.continuinged.ku.edu/programs/ase/papers/26.html)
  · [SBES](https://sol.sbc.org.br/index.php/sbes/article/view/17022)
- **Term mismatch is the named primary cause of low precision** in artefact trace retrieval — the
  failure mode that structural matching on IDs, clause references and a closed check-type vocabulary
  avoids entirely — [IJACSA 13(12)](https://thesai.org/Downloads/Volume13No12/Paper_92-Clustering_based_Automated_Requirement_Trace_Retrieval.pdf)
- **The field admits it has no standard metric for NL test cases**: NeTestLLM states that test cases
  expressed in natural language "lack standardized quality metrics, making it difficult to assess
  their reliability and coverage", and therefore adopts a semi-quantitative key-section + semantic
  coverage scheme — [arXiv 2510.13248](https://arxiv.org/html/2510.13248v1)
- **Name leakage is a measured hazard in exactly this genre**: in 5G O-RAN test-procedure generation,
  closed-source models' generated procedures "significantly rely on the test case name and the
  components listed in the prompt" — i.e. matching that uses the official test's title or ID as a
  signal measures recall of the *label*, not of the check — [arXiv 2506.10111](https://arxiv.org/pdf/2506.10111)
- The best published structural-ish matcher for NL test cases still works per-*step*, then aggregates:
  cluster similar test steps, then combine step clusters with the test case name to identify similar
  test cases — F-score 87.39 % at step level vs. 83.47 % at whole-test level, i.e. **decomposing before
  matching scored higher than matching whole cases** — [arXiv 2110.07733](https://arxiv.org/pdf/2110.07733)

### Inferences
- **The literature does support structural matching, by analogy and by notation, but no paper performs
  TP-to-TP structural matching between two abstract test suites.** The support is: (a) the genre's own
  standards define the tuple (9646-2 TSS&TP; TPLan `with/ensure that/when/then` + RQ ref), so matching
  on that tuple is matching on the artefact's own semantics rather than on an invented schema;
  (b) 9646-2 already treats coverage and requirement→TP→ATS traceability as normative concerns, so
  "which TPs are covered" is the genre's native question; (c) every empirical datapoint retrieved shows
  structural or decomposed signals beating whole-text similarity. This is a defensible
  position-with-a-gap: your contribution is the first instantiation, not an application of a known
  method.
- **Concretely, the mapping from the 907-case record set onto the TPLan blocks is direct**: Test case ID
  → TP id (and, since the IDs encode SUT/area/object/index, a *parsed* structural key); System under
  test → the per-SUT split that ETS 300 064 does by document; Reference → RQ ref; Technology/Profile →
  Config and applicability; Preconditions → `with`; Test scenario → `when`; Expected results → `then`;
  Purpose → Summary. Matching should therefore be a conjunction of block-level predicates, not one
  similarity score.
- **A principled match key, in order of discriminating power**: (1) SUT, from the ID taxonomy and the
  SUT field — a mismatch here is an automatic non-match and costs nothing to enforce; (2) object/data
  item, from the ID's object segment and the Purpose; (3) check type from the closed vocabulary
  (presence, absence, encoding well-formedness, value domain, size/boundary, consistency, behaviour);
  (4) applicability condition (Technology/Profile/Preconditions); (5) expected outcome. Only (2) and
  (5) genuinely need semantic judgment; (1), (3) and (4) are categorical and should be decided by
  string/enum comparison, not by an LLM. This shrinks the LLM's role from "is this the same test" to
  "is this the same object" plus "is this the same expected outcome", which is the narrowest and most
  calibratable judgment available.
- **The 118-family / 7.7-cases-per-family structure is a free stratification and a free partial-credit
  level.** Family-level coverage ("did the generator produce anything in this family?") is a second,
  strictly easier metric that is honest, is computable from the ID taxonomy with no judge at all, and
  is the one most likely to reach a high percentage. Reporting family coverage and per-case coverage
  side by side is the single clearest way to avoid an argument about whether 13.8 % is "the" number:
  they measure breadth and depth respectively.
- **The 54-clause / 687-case distribution with a 90-case maximum means a raw percentage is dominated by
  a few clauses.** A generator that handles the heaviest clause well can move the aggregate several
  points without broadening. Report **macro-averaged recall over clauses** (and over the 118 families)
  alongside the micro-averaged figure; the gap between macro and micro is itself a finding about
  whether the generator is broad or lucky.
- **The closed check-type vocabulary enables a confusion matrix over check types**, which is far more
  informative than a single percentage: it will show, e.g., that presence and encoding checks match
  well while boundary and consistency checks do not. Reviewers reward this kind of decomposition and it
  directly answers "what would it take to improve".
- **Do not let the official test's ID or title into the judge's prompt.** The AI5GTest name-reliance
  finding makes this a known inflation path; show the judge only Purpose/scenario/expected-results
  content, and keep IDs for the structural key computed outside the judge.

### Gaps
- **No publication found that matches one abstract test-purpose suite against another**, nor any
  published metric for TP-to-TP equivalence. ISO/IEC 9646-2's clause 10.4 "Coverage" concerns coverage
  of *conformance requirements by test purposes*, not coverage of one TP suite by another — i.e. the
  standard supports clause/requirement coverage as the native metric, not suite-to-suite recall.
- The **normative text of ISO/IEC 9646-2 was not read** (the ANSI preview returned HTTP 403; the
  clause-number and scope detail above came from search-result metadata and a CSA catalogue listing).
  Before citing clause 10.4 in the paper, obtain the standard. Note also that one listing marks an
  edition of 9646-2 as withdrawn, with 1994 the commonly referenced edition.
- The **ES 202 553 PDF could not be text-extracted** (compressed/encrypted streams); the TPLan block
  structure above comes from the ETSI CTI portal page describing the standard, which is a primary ETSI
  source but not the normative text.
- **No formal definition of "test purpose equivalence"** was found in any standard or paper, so the
  conjunctive predicate above is a construction, not a citation. Framing it as an operationalisation of
  the TPLan block structure is the strongest available justification.

---

## Suite-to-suite comparison: published methods for mapping a generated suite onto a reference suite

### Takeaway
There is no standard benchmark method for suite-to-suite coverage, but there are three reusable
building blocks with published numbers: unsupervised similar-test-case detection for NL test cases
(F-score ≈ 83–87 %), embedding-cosine matching with a fixed threshold as used in the one industry
study that reports recall against an existing high-level test suite, and traceability-link recovery
(IR/precision-recall) between heterogeneous test artefacts, where text-only IR performs poorly
(recall < 40 %, precision < 30 %) unless hybridised. Thresholds in the literature are borrowed rather
than calibrated, and matching validation is usually weak — which is itself a citable gap your paper
can exploit.

### Cited Findings
- **Near-duplicate / similar NL test case detection (Viggiato et al., arXiv 2110.07733, later TSE).**
  Unsupervised pipeline over test *steps*: evaluates several text-embedding techniques, similarity
  metrics and clustering algorithms, clusters similar steps, then combines step clusters with the test
  case name to identify similar test cases. Reported F-score **87.39 %** for similar steps with an
  ensemble of NLP techniques, **86.99 %** with Word2Vec alone, and **83.47 %** for whole test cases;
  requires no labelled data or human supervision — [arXiv 2110.07733](https://arxiv.org/pdf/2110.07733)
  ([ar5iv full text](https://ar5iv.labs.arxiv.org/html/2110.07733))
- Same work states explicitly that naive approaches (searching for exactly matching test cases) are
  insufficient to capture all similarity — i.e. lexical exact match under-counts matches, which is the
  direction in which a weighted-token-overlap retriever will err —
  [arXiv 2110.07733](https://arxiv.org/pdf/2110.07733)
- **Step-level similarity at industrial scale.** A Mälardalen University technical report evaluates a
  similarity function for detecting similar test steps in manual NL test cases, built on standard
  Postgres text functions, on an industrial data set of **65 000 test steps** —
  [MDU 4713 Tech Report](https://www.es.mdu.se/publications/4713-Tech__Report__Similarity_Function_Evaluation)
- **Levenshtein-distance clustering of test cases** (Ericsson-related study): each test case is
  serialised to a string, pairwise Levenshtein distance drives clustering, clusters then feed parallel
  test scheduling — cited in the same search cluster as above; primary source not retrieved (see Gaps).
- **Industrial similarity analysis (QualityLogic).** Jaccard and cosine similarity plus a proprietary
  genetic clustering algorithm; first pass targeted almost-identical test cases for elimination and
  produced a **4 % reduction** in overall test cases; second pass grouped tests with similar sequences
  — [QualityLogic case study (PDF)](https://qualitylogic.com/wp-content/uploads/2019/06/QL-Case-Study-Similarity-Analysis-Using-AI.pdf)
- **Embedding-cosine matching with a fixed threshold — the closest published analogue to your setup**
  (Masuda et al., "Generating High-Level Test Cases from Requirements using LLM: An Industry Study",
  arXiv 2510.03641, Tokyo City University + VeriServe). Protocol: embed each *truth* (reference) test
  case and each generated test case with OpenAI `text-embedding-3-small`; similarity = cosine; a pair
  counts as a match at **threshold 0.7**, justified by citing prior work that "a similarity score of
  0.7 or higher is considered identical"; matching is **many-to-one in both directions** (one truth
  case may match several generated cases and vice versa) —
  [arXiv 2510.03641 (HTML)](https://arxiv.org/html/2510.03641v1)
- Their metric definitions, which are directly reusable: **recall = (# unique truth cases matched by
  at least one generated case) / (# truth cases)**; **precision = (# unique generated cases that match
  some truth case) / (# generated cases)**; F1 = harmonic mean; plus a **"generation rate" = #generated
  / #truth**. The authors state they deliberately weight recall over precision, arguing automated
  execution can absorb extra cases — [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- Their validation of the matching is thin and they say so only obliquely: the paper states experts
  confirmed the similarity threshold had "no issues" but **gives no protocol, sample size or results**;
  the threshold is borrowed from another domain and not calibrated on their data; a later passage
  inconsistently says "0.65 or higher is considered a match" —
  [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- **Traceability-link recovery between test artefacts.** Standard scoring is precision, recall,
  F-measure (F1 and F2 both used), with Average Precision for ranked candidate links and
  precision-at-recall-level curves — [Automating Requirements Traceability: Two Decades of Learning
  from KDD, arXiv 1807.11454](https://arxiv.org/pdf/1807.11454)
- The same review argues **recall matters more than precision** in tracing, because detecting a false
  positive is much cheaper than discovering an error of omission — a defensible justification for
  reporting recall-against-reference-suite as the headline number —
  [arXiv 1807.11454](https://arxiv.org/pdf/1807.11454)
- Text-only IR between *test* artefacts performs badly: for bug reports linked to manual test cases,
  LSI, LDA, BM25 and a word-vector deep-learning technique achieved **average recall below 40 % and
  average precision below 30 %**, attributed partly to vocabulary differences between test-case
  descriptions and target documents — [Improving Traceability Recovery Between Bug Reports and Manual
  Test Cases (SBES)](https://sol.sbc.org.br/index.php/sbes/article/view/17022)
- A **merged matrix** (union of links recovered by at least one of four techniques) reached **93 %
  recall** after cleaning, spell-checking and term weighting — same source
  ([SBES](https://sol.sbc.org.br/index.php/sbes/article/view/17022))
- Structural signals beat text similarity: Ziftci and Krueger linked requirements to test cases via
  realised functional features in code and obtained **precision/recall above 90 %**, an improvement on
  then-existing IR approaches on the same case studies (chat system, Apache Pool, Apache Log4j) —
  [ASE 2011 paper page](https://www.se.cs.uni-saarland.de/conferences/ASE/ase2011/www.continuinged.ku.edu/programs/ase/papers/26.html)
- **Term mismatch is the named root cause** of low precision in trace retrieval; clustering-based
  approaches are proposed to address it — [Clustering based Automated Requirement Trace Retrieval,
  IJACSA 13(12)](https://thesai.org/Downloads/Volume13No12/Paper_92-Clustering_based_Automated_Requirement_Trace_Retrieval.pdf)
- A TF-IDF study on requirements↔test cases concluded the method was good at detecting *negative*
  relationships but not positive ones, and of limited use for recovering traceability —
  [Telkom University open library (PDF)](https://openlibrary.telkomuniversity.ac.id/pustaka/files/172857/abstraksi/pengembalian-ketelusuran-antara-test-cases-dan-requirements-menggunakan-teknik-tf-idf.pdf)
- Evaluation convention for recovered links: report **both** a ranked measure (Mean Average Precision)
  and a set-based measure (interpolated precision-recall graph) — [Improving Traceability Recovery
  Techniques Through the Study of Tracing Methods and Analyst Behavior (dissertation,
  U. Kentucky)](https://uknowledge.uky.edu/cs_etds/5)

### Inferences
- Your pipeline (top-5 lexical retrieval by weighted token overlap, then an LLM equivalence judgment)
  is a two-stage *recall-oriented* matcher. The retrieval stage is the published weak link: lexical
  overlap is exactly the method shown to miss paraphrases, and the term-mismatch literature predicts
  systematic misses when the generated vocabulary follows the 2020 draft while the reference tests use
  the published edition's terms. Reporting **retrieval recall@k separately** (how often the correct
  match is in the candidate set, measured on a hand-labelled subset) would decompose "the generator
  missed it" from "the retriever never showed it to the judge".
- Two cheap upgrades with direct citations: add an embedding similarity channel alongside token
  overlap (Viggiato: embeddings outperform exact matching; Masuda: `text-embedding-3-small` cosine),
  and enlarge *k* or take the union of candidates from both channels (the SBES "merged matrix" result
  shows union-of-techniques materially raises recall).
- Because the two published matchers differ (embedding cosine at a fixed threshold vs. LLM
  equivalence), running both and reporting the pair is a credible robustness check: an embedding-cosine
  number is directly comparable to Masuda et al., and an LLM-judged number is the stricter criterion.

### Gaps
- No published method matches a *generated test plan* (descriptions, 29119-3 style) onto an *official
  conformance suite* clause-by-clause. The analogues are requirements→test traceability and NL
  test-case deduplication; your contribution can be framed as adapting them.
- The Ericsson/Levenshtein clustering study and the "almost identical" industrial numbers were only
  available through secondary summaries; primary sources not retrieved.
- No published calibration of a similarity threshold for *conformance* test cases; the 0.7 cosine
  cutoff is borrowed from unrelated domains.

---

## LLM-as-judge reliability for equivalence judgments: agreement, biases, mitigations

### Takeaway
Judge–human correlation in SE is strong on some tasks and useless on others, and in no retrieved study
does it reach human–human agreement; the best SE meta-evaluation reports Pearson 81.3 (code
translation), 68.5 (code generation) and only 26.2 (code summarisation) against human inter-rater
Pearson of 85.9 / 79.7 / 73.7. Pairwise comparison was *worse* than individual scoring and
position-inconsistent. Self-preference bias is documented and quantified elsewhere, with perplexity
(familiarity) as the leading mechanistic explanation — which means a same-family judge is a real,
citable threat, not a hypothetical one, and the standard fix is a cross-family judge plus calibration
against a human-labelled subset with chance-corrected agreement reported on identical items.

### Cited Findings
- **The SE meta-evaluation (Wang et al., "Can LLMs Replace Human Evaluators? An Empirical Study of
  LLM-as-a-Judge in Software Engineering", ISSTA 2025; arXiv 2502.06193).** Builds a meta-evaluation
  dataset over code translation, code generation, code summarisation; evaluates 7 LLM-as-judge methods
  on general-purpose LLMs plus 2 LLMs fine-tuned for evaluation —
  [arXiv 2502.06193](https://arxiv.org/abs/2502.06193) ·
  [ISSTA 2025 page](https://conf.researchr.org/details/issta-2025/issta-2025-papers/85/Can-LLMs-replace-Human-Evaluators-An-Empirical-Study-of-LLM-as-a-Judge-in-Software-E)
- Best judge vs. human, individual scoring (values ×100; Pearson R / Spearman ρ / Kendall τ):
  **code translation** BatchEval+GPT-4o **81.32 / 73.67 / 59.80** vs. best conventional metric ChrF++
  34.23 / 31.30 / 22.65; **code generation** DeepSeek-V2.5 **68.51 / 66.39 / 54.74** vs. METEOR
  65.55 / 67.11 / 49.66; **code summarisation** G-Eval **26.19 / 23.34 / 17.18**, *worse* than ROUGE-L
  47.01 / 48.45 / 35.47 — [arXiv 2502.06193v3 (HTML), Table 3](https://arxiv.org/html/2502.06193v3)
- **Human inter-rater agreement in the same study** (translation / generation / summarisation):
  Spearman ρ 83.07 / 75.42 / 74.20; Pearson R 85.86 / 79.70 / 73.74; Kendall τ 72.26 / 63.40 / 62.57.
  This is the correct ceiling to quote when arguing a judge-based score is bounded —
  [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- The study **does not report Cohen's κ**; its agreement is correlational, not chance-corrected —
  [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- **Pairwise comparison underperformed**: G-Eval and BatchEval reached highest pairwise accuracy on
  translation at only **64.67 and 65.33**; accuracy fell **below 50** on code generation; all methods
  unusable on summarisation — [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- **Position bias quantified**: pairwise judgments were frequently inconsistent when response order
  was swapped; the most accurate methods had order-consistency/agreement scores of roughly **11–24**
  on translation and generation — [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- **Verbosity bias documented** (GPT-4o scored a verbose step-by-step summary 5/5 where a concise
  docstring-style answer was wanted) — [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- **Self-preference was NOT evaluated** in that study — explicitly a gap in the SE literature
  — [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- Their recommendations, verbatim in substance: prefer **individual scoring over pairwise**; use
  **output-based judges with large state-of-the-art LLMs** (embedding-based and probability-based
  methods not recommended for SE); **validate the judge against human scores for each task before
  relying on it**; for weakly-correlated tasks use the judge alongside conventional metrics with
  prompts that counter verbosity; inference strategies (G-Eval, BatchEval) gave only marginal gains
  over greedy decoding — [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- Fine-tuned judges (Auto-J, Prometheus 2) were **weaker** than large general-purpose models —
  [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- **Self-preference bias, quantified** (Wataoka et al., NeurIPS 2024). Proposes the first quantitative
  metric, defined as a difference in conditional probabilities: how often the evaluator prefers a
  response when it generated it versus when another source did, conditioned on a human rater having
  preferred that response. **GPT-4 exhibits a significant degree of self-preference bias**; some
  models (e.g. oasst-pythia-12b) show the reverse, underestimating their own outputs —
  [arXiv 2410.21819](https://arxiv.org/html/2410.21819v1) ·
  [NeurIPS 2024 page](https://neurips.cc/virtual/2024/106181)
- **Mechanism**: LLMs assign significantly higher evaluations than humans to outputs with **lower
  perplexity**, regardless of whether those outputs were self-generated; the authors conclude
  self-preference arises because a model's own outputs have lower perplexity for it —
  [arXiv 2410.21819](https://arxiv.org/html/2410.21819v1)
- **Self-preference extends to rubric-style binary verdicts** — exactly your judging format. Pombal
  et al. find SPB occurs under both holistic scoring and per-criterion binary rubrics, with judges
  systematically favouring outputs from **themselves, from models in their own family, or from models
  trained on similar data**, and warn this is most damaging in recursive self-improvement settings —
  [alphaXiv 2604.06996](https://www.alphaxiv.org/abs/2604.06996)
- **Measurement confound caveat**: Roytburg et al. argue earlier self-preference measurements conflate
  narcissism with experimental confounds — in particular, judges deliver self-preferring verdicts on
  queries they themselves answered incorrectly; they claim controlling for this could reduce
  measurement error by 89.6 % (authors' claim, abstract only, unverified) —
  [arXiv 2601.22548v3](https://arxiv.org/pdf/2601.22548v3)
- **Prompt-sensitivity audit for SE judges** (Zhao, Esmaeili, Fard, "Bias in the Loop: Auditing
  LLM-as-a-Judge for Software Engineering", arXiv 2604.16790, April 2026). Controlled interventions
  isolate one presentation cue at a time across **code generation, code repair and test generation**
  under two pointwise judging regimes. Findings: small prompt edits swing outcomes; semantically
  equivalent rewording produces different verdicts; several biases pull the judge toward whichever
  option the prompt favours, raising accuracy when that matches the gold answer and lowering it when
  it does not; effects large enough to **change task-level conclusions and alter relative model
  rankings**. Conclusion: reported judge performance may reflect prompt artefacts rather than stable
  assessment ability. Recommendation: **report bias sensitivity alongside accuracy** and use explicit
  controls — [arXiv 2604.16790](https://arxiv.org/abs/2604.16790)
- **Forward-looking SE position paper** (metadata lists TOSEM; venue unconfirmed): "From Code to
  Courtroom: LLMs as the New Software Judges" states LLM-as-judge research in the SE community is
  still in its early stages and that these methods often lead to misalignment with human judgment —
  [arXiv 2503.02246](https://arxiv.org/html/2503.02246v1)
- **Calibration protocol conventions** (practitioner/tooling sources, not peer-reviewed): report raw
  human–human agreement next to a chance-corrected metric, computed on **identical items with the same
  metric** as the LLM–human figure; choose the statistic by annotation design (Cohen's κ for two
  annotators with categorical labels, weighted κ for ordered labels, Krippendorff's α when annotator
  counts vary); never report κ alone — pair it with the confusion matrix, class prevalence, precision/
  recall/F1 per class and uncertainty intervals; build gold labels by adjudication or majority vote
  and keep ties and low-consensus items rather than forcing a label; keep the calibration set
  **separate from the examples used to write or tune the judge prompt**; report **error direction**,
  not only overall agreement — [Arize: measuring human–LLM judge
  alignment](https://arize.com/blog/measuring-human-llm-judge-alignment/) ·
  [Calibrating an LLM judge with Cohen's κ](https://oneuptime.com/blog/post/2026-08-31-calibrate-llm-judge-cohens-kappa/markdown)
- Reported κ values from a published study that did this properly (financial-LLM compression paper):
  humans labelled every case where two judges disagreed plus a random sample of agreement cases, then
  **reweighted the strata by frequency**; Cohen's **κ = 0.83** judge-vs-human for one judge, **0.76**
  between the two judges; the two judges erred in **opposite directions** —
  [arXiv 2609.26241](https://arxiv.org/pdf/2609.26241)
- Decomposing κ across pair types (human–LLM, LLM–LLM, human–human) plus ECE and reliability curves is
  implemented in open tooling — [Potato judge-calibration
  docs](https://potatoannotator.readthedocs.io/en/latest/ai-intelligence/judge_calibration/)
- An alternative practitioner protocol: split human-labelled data into train/dev/test, iterate the
  judge prompt on dev until **TPR and TNR both exceed 90 %**, run once on held-out test, then apply a
  bias-correction formula to production scores, using domain-expert labellers rather than crowd workers
  — [validate-evaluator skill (Hamel Husain)](https://skills.sh/hamelsmu/evals-skills/validate-evaluator)

#### How large a human-labelled calibration subset must be
- **There is no universal minimum n for Cohen's κ.** Required sample size depends on the expected κ,
  the category prevalences, α and desired power; too small yields imprecise estimates, too large wastes
  resources — [tutorial on agreement studies, PMC12935580](https://pmc.ncbi.nlm.nih.gov/articles/PMC12935580/)
- **The standard power calculation is Flack et al. (1988)**, implemented as `N2.cohen.kappa` in the R
  `irr` package; inputs are the raters' marginal probabilities, the true κ (k1), the null κ (k0), α and
  power. A binary-outcome variant is **Cantor (1996), *Psychological Methods***, implemented as
  `N.cohen.kappa`; the package's own worked example tests whether κ exceeds **0.7** when the true κ is
  **0.85** and both raters classify 50 % of subjects as positive —
  [`irr` package reference manual](https://cloud.r-project.org/web/packages/irr/refman/irr.html)
- For more than two raters or more than two categories, `kappaSize` and related tools are needed; a
  user report shows `N2.cohen.kappa` struggling with a three-category design with unequal marginals
  (0.2 / 0.6 / 0.2) — [R-help thread](https://mailman.stat.ethz.ch/pipermail/r-help/2014-November/423182.html)
- **Pilot estimates of prevalence matter more than any rule of thumb**, and no authoritative minimum-n
  rule should be quoted without a specific source —
  [`irr` manual](https://cloud.r-project.org/web/packages/irr/refman/irr.html) ·
  [PMC12935580](https://pmc.ncbi.nlm.nih.gov/articles/PMC12935580/)
- **A Monte Carlo study argues the conventional advice is over-conservative**: He, Baker, Hutt & Zhang
  note that some researchers argue Cohen's κ cannot validly be used without much larger samples, and
  conclude κ **can** reasonably be used at the sample sizes often used in practice, provided the
  threshold κ is raised or power-analysis stringency applied —
  [ICQE22 paper](https://learninganalytics.upenn.edu/ryanbaker/ICQE22_pdf_7730.pdf) ·
  [extended version](https://learninganalytics.upenn.edu/ryanbaker/ICQE22-Kappa-MC-extended.pdf)
- **Severe class imbalance is the binding constraint**, not n as such: raw agreement looks impressive
  when one label dominates, so κ must be read with the confusion matrix and class prevalence, and the
  calibration set needs **enough examples of each important class** —
  [Oneuptime](https://oneuptime.com/blog/post/2026-08-31-calibrate-llm-judge-cohens-kappa/markdown) ·
  [Arize](https://arize.com/blog/measuring-human-llm-judge-alignment/)
- **The disagreement-stratified design is the efficient answer** when labelling is expensive: label all
  judge-disagreement cases plus a random sample of agreement cases, then reweight strata by frequency
  — that design yielded κ = 0.83 (judge vs. human) and 0.76 (judge vs. judge) —
  [arXiv 2609.26241](https://arxiv.org/pdf/2609.26241)

### Inferences
- The same-model-family threat is **citable and specific**, not vague: Pombal et al. show SPB applies
  to family members and to models trained on similar data, and applies under binary rubric judging.
  The defensible response is a second judge from a different family on the same items, reporting both
  scores and their κ; if the cross-family judge scores lower, report the lower number as the headline.
- Your score direction matters for how worried to be. Self-preference inflates scores; your 13.8 % is
  so low that self-preference is unlikely to be *producing* the result — the more plausible argument is
  that the true score is at or below 13.8 %, making a same-family judge a **conservative** bias here
  and a strong one for the 56/50/54-of-60 quality ratings (which are the scores a self-preferring
  judge would inflate). Say this explicitly; reviewers will accept an argued direction of bias much
  more readily than an unargued disclaimer.
- Because the SE meta-evaluation found pairwise comparison worse and position-inconsistent while
  individual scoring was usable, your per-official-test "does any candidate verify the same check?"
  design is the better of the two published options; cite that. Mitigate position bias within the
  candidate set by shuffling the order of the five retrieved candidates across repeated runs and
  reporting agreement between runs.
- Rubric decomposition (same data item/behaviour, same condition, same expected outcome as three
  separate binary sub-judgments, conjoined afterwards) is consistent with the "counter the bias with an
  explicit prompt contract" advice and additionally yields free diagnostics: which of the three
  conditions most often breaks the match.
- The honest ceiling statement for any judge-based score is the human inter-rater figure from a
  comparable task (ρ 0.74–0.83 in the SE meta-evaluation). A paper claiming 85–90 % *measured by an
  LLM judge* is claiming precision the measurement instrument has not been shown to have.
- **Specific weaknesses invited by the current protocol** (top-5 lexical retrieval → same-family judge
  → "does any of these verify the same check?"), each with the citation that makes it a named threat
  rather than a worry: (i) *ceiling imposed by the retriever* — a lexical-overlap top-5 cannot be
  rescued by any judge, and term mismatch is the documented primary cause of low recall in artefact
  matching ([IJACSA](https://thesai.org/Downloads/Volume13No12/Paper_92-Clustering_based_Automated_Requirement_Trace_Retrieval.pdf));
  (ii) *same-family self-preference*, which Pombal et al. show applies to the judge's own family and to
  models trained on similar data, and applies under binary rubric judging
  ([alphaXiv 2604.06996](https://www.alphaxiv.org/abs/2604.06996)); (iii) *position bias inside the
  candidate list* — a 5-way "any of these?" is a multi-option comparison, the regime where the SE
  meta-evaluation found order-swap consistency of only ~11–24
  ([arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)); (iv) *prompt sensitivity large enough to
  change conclusions and rankings* ([arXiv 2604.16790](https://arxiv.org/abs/2604.16790));
  (v) *disjunctive leniency* — asking "does any of five verify the same check" gives five chances to
  say yes and makes the verdict sensitive to candidate-set size, so a score measured at k=5 is not
  comparable to one at k=10.
- **A defensible protocol, in the order of cheapest-to-most-valuable:** decide SUT, check type and
  applicability class structurally outside the judge (see the genre section) so the judge only rules on
  object identity and expected outcome; judge **one candidate at a time** (individual scoring, which
  the SE meta-evaluation found superior to comparison) and aggregate by OR, which removes candidate-set
  size and position effects; **shuffle candidate order** across repeated runs and report run-to-run
  agreement; run a **second judge from a different model family** over the full denominator and report
  both scores plus their κ; **report the score at two values of k** so the retrieval ceiling is
  visible; **calibrate against a human-labelled stratified sample** and report human–human κ next to
  judge–human κ on the same items; keep the calibration items out of prompt tuning; report the
  **direction** of the judge's errors.
- **Calibration size, worked for your prevalence.** With a ~14 % positive rate, a simple random sample
  is the wrong design — 150 random items would contain ~21 positives and the κ estimate would be
  dominated by the negative class, which is exactly the imbalance failure mode the calibration guides
  warn about. Use the disagreement-stratified design: label **all or most positives** from a sample
  (say every positive among ~250 drawn items, ≈35 cases), plus an equal-sized random sample of
  negatives, plus **every item where two cross-family judges disagree**, then reweight strata by
  frequency as in arXiv 2609.26241. That yields on the order of **100–150 human-labelled items with
  roughly balanced classes**, which is the regime the Monte Carlo study says κ can be used in provided
  the acceptance threshold is raised. Fix the acceptance threshold in advance (the `irr` worked example
  tests κ > 0.7 against a true κ of 0.85) and compute the required n with `N.cohen.kappa` from your
  pilot prevalences rather than quoting a rule of thumb — and report the power calculation's inputs,
  since the published good practice is to state the sampling and reweighting design explicitly.

### Gaps
- No retrieved study measures LLM-judge agreement with humans on the specific task of
  **test-case equivalence** ("do these two test descriptions verify the same check"). The nearest
  analogues are code-summarisation judging (weak, ρ 0.23) and code-generation judging (ρ 0.66).
  This means the κ for your judge must be measured locally; no literature value can be borrowed.
- No peer-reviewed reporting standard for judge calibration was found — the calibration conventions
  above come from vendor/practitioner guides and one applied preprint.
- Could not confirm that any of this LLM-as-judge material is actually published in ACM TOSEM; the
  closest is the SE 2030 roadmap paper whose metadata lists TOSEM but whose venue I could not verify.
  The well-identified peer-reviewed SE venue here is **ISSTA 2025** (arXiv 2502.06193).

---

## Alternatives to a human reference suite: adequacy criteria for a never-executed test plan

### Takeaway
For an artefact that is never executed, the defensible adequacy claims are *specification-side*, not
code-side: requirements/clause coverage (ISO/IEC/IEEE 29119-4 clause 6.2.12 "Requirements-based testing
coverage"), coverage-item coverage per the standard's own definition of test coverage, and
specification-element coverage of the kind NeTestLLM calls "key section coverage" and "semantic
coverage". Mutation adequacy is the strongest fault-oriented criterion but needs executable tests, so
it can only be borrowed by analogy (seeded *specification* defects), which is a legitimate and cheap
substitute: seed mutations into the standard text and ask whether the generated plan would catch them.

### Cited Findings
- **ISO/IEC/IEEE 29119's own definition of test coverage** is the degree, expressed as a percentage, to
  which specified **test coverage items** have been exercised by a test case or test cases — which
  makes "coverage" in the 29119 family a ratio over *specified coverage items*, not over code —
  [AKIT terminology entry citing ISO/IEC/IEEE 29119](https://akit.cyber.ee/term/11134)
- ISO/IEC/IEEE **24765** defines test coverage as the extent to which test cases test the
  requirements — the requirements-coverage framing — [same source](https://akit.cyber.ee/term/11134)
- **ISO/IEC/IEEE 29119-4:2021** provides standard definitions of software test design techniques and
  *corresponding coverage measures*; its clause **6 is "test coverage measurement"**, with **6.2 for
  specification-based techniques**, listing equivalence partition, boundary value, decision table,
  state transition and scenario coverage, ending at **6.2.12 Requirements-based testing coverage** —
  [ISO/IEC/IEEE 29119-4:2021 catalogue
  entry](https://iteh.eu/catalog/standards/iso/20536fd0-e74a-4b3c-8285-af54a8441204/iso-iec-ieee-29119-4-2021)
  · [IEC preview PDF](https://www.vde-verlag.de/iec-normen/preview-pdf/info_isoiecieee29119-4{ed1.0}en.pdf)
  · [ISO/IEC 29119 overview](https://en.wikipedia.org/wiki/ISO/IEC_29119)
- **Specification-coverage metric actually used by an LLM conformance-test generator**: NeTestLLM
  states that test cases expressed in natural language lack standardised quality metrics, making it
  difficult to assess their reliability and coverage, and therefore uses a **semi-quantitative
  evaluation based on key section coverage and semantic coverage**; it also reports **coverage breadth
  verification**, the extent to which important sections of the protocol specification are covered —
  [arXiv 2510.13248](https://arxiv.org/html/2510.13248v1) ·
  [third-party review](https://www.themoonlight.io/review/automated-network-protocol-testing-with-llm-agents)
- **Mutation adequacy, origin and definition**: mutation score = killed mutants / generated mutants;
  using mutants to measure test-suite adequacy was originally proposed by DeMillo et al. —
  [Mind the Gap: The Difference Between Coverage and Mutation Score Can Guide Testing Efforts,
  arXiv 2309.02395](https://arxiv.org/pdf/2309.02395)
- **Why it is a defensible surrogate**: prior work extensively examined the correlation between
  mutants and real-world faults, finding that in many cases mutation analysis can mimic such faults,
  so mutation score is recommended to measure adequacy in terms of likelihood of detecting bugs —
  [IJSEA (Univ. Colorado Colorado Springs
  mirror)](https://faculty.uccs.edu/kwalcott/wp-content/uploads/sites/49/2024/01/9318ijsea01-Hessah.pdf)
- **Coverage vs. mutation**: coverage measures execution, not "testedness"; an empirical study of four
  open-source systems found code coverage can sometimes be a sufficient indicator of expected defect
  density but mutation and reducibility are better in most cases; high branch coverage generally
  co-occurs with high mutation score — [arXiv 2309.02395](https://arxiv.org/pdf/2309.02395) ·
  [IJSEA](https://faculty.uccs.edu/kwalcott/wp-content/uploads/sites/49/2024/01/9318ijsea01-Hessah.pdf)
- **Cost is the standing objection**: mutation analysis has only recently begun to achieve industrial
  penetration, in large part due to its computational expense, and seldom as an actual adequacy metric
  — [Univ. Szeged mutation 2016 paper](https://www.inf.szte.hu/~beszedes/research/mutation16.pdf)
- **A low mutation score is not self-interpreting**: researchers ask whether the test suite should be
  reinforced or the production code improved, and examine testability and observability as
  explanations — [Univ. Szeged](https://www.inf.szte.hu/~beszedes/research/mutation16.pdf)
- **Stricter variant**: the diversity-aware "distinguishing mutation adequacy criterion" is satisfied
  when each considered mutant is identified by the *set* of tests that kill it; it detects **1.33×
  more unseen faults** than traditional mutation adequacy at the cost of a **1.56× larger** adequate
  suite — [KAIST, A Theoretical and Empirical Study of Diversity-aware Mutation Adequacy
  Criterion](https://koasas.kaist.ac.kr/handle/10203/246717)
- **Coverage does not guarantee fault detection** — a replication study finds high coverage does not
  necessarily imply strong fault detection for LLM-generated suites — [Do Coverage and Mutation Scores
  of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study),
  arXiv 2607.22880](https://arxiv.org/pdf/2607.22880)
- **Benchmark practice for multi-aspect evaluation of generated tests**: TestBench evaluates class-level
  generation along syntactic correctness, compilation correctness, test correctness, code coverage rate
  and defect detection rate — a template for a multi-axis adequacy claim —
  [arXiv 2409.17561](https://arxiv.org/html/2409.17561v1)
- **Redundancy/diversity metric**: TESTEVAL introduces **cov@k** specifically to check whether an LLM
  is generating redundant tests rather than a varied suite — the generated-suite-side counterpart to
  reference-suite recall — [TESTEVAL, arXiv 2407.00225](https://arxiv.org/abs/2407.00225) ·
  [review](https://themoonlight.io/review/testeval-benchmarking-large-language-models-for-test-case-generation)
- **Bug-coverage against a standards baseline** — a comparison form that works without executing the
  generated plan against code: NeTestLLM's 4 632 generated test cases for OSPF/RIP/BGP cover **41
  historical FRRouting bugs vs. 11 covered by current national standards** —
  [arXiv 2510.13248](https://arxiv.org/html/2510.13248v1)

### Inferences
- A defensible adequacy claim for a non-executable 29119-3 test plan has three legs, all citable:
  (1) **clause coverage** — the share of normative ("shall") clauses of the input standard for which
  the plan contains at least one test case, with 29119-4 §6.2.12 as the authority for calling this
  coverage; (2) **reference-suite recall** — the share of official tests matched, reported with the
  matching protocol and its own validation; (3) **a fault-oriented proxy** — specification mutation:
  perturb normative statements (negate a shall, change a bound, drop a condition, swap a data item)
  and measure the share of perturbations for which the plan's expected result would differ. Leg (3) is
  the direct transfer of DeMillo-style mutation adequacy to a non-executable artefact and is the single
  strongest addition available, because it is independent of both the reference suite's edition and
  the LLM judge.
- Clause coverage has a crucial property your current metric lacks: it is computable **without the
  reference suite**, so it is unaffected by the 2020-vs-2021 edition mismatch and generalises to any
  standard whether or not a conformance suite has been published. It is also the metric most likely to
  land in the 85–90 % range honestly, which is an argument for making it the headline and
  reference-suite recall the harder secondary number.
- "Coverage does not guarantee fault detection" cuts both ways and should be used symmetrically: it
  undercuts a high clause-coverage claim as proof of quality, so pair legs (1) and (3) rather than
  leaning on either alone.
- The TESTEVAL cov@k idea maps onto your 907/687 setting as a redundancy check on the *generated*
  side: how many distinct official tests the generated suite matches per generated test. A generator
  that produces 2 000 near-duplicates to maximise retrieval hits would be caught by it.

### Gaps
- Could not retrieve the **normative text of 29119-4 clause 6.2.12**, so the exact counting rule (when
  a requirement counts as covered; whether it is measured through other techniques' coverage items) is
  unconfirmed. Acquiring the standard is needed before citing a specific counting rule.
- Found **no published work applying mutation testing to a specification or to a non-executable test
  plan** as an adequacy measure. Notably, Masuda et al. propose mutation testing as *future work*
  precisely because embedding similarity is not correctness
  ([arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)) — i.e. this is an open slot in the
  literature, not a solved problem with a number to cite.

---

## Reported numbers from comparable systems

### Takeaway
The only published system that reports recall against an existing human-written high-level test suite
gets **0.84 (or 0.81 as reported in its own abstract) on Bluetooth and 0.37 on Mozilla**, using a far
more permissive matcher than yours (cosine ≥ 0.7, not semantic equivalence), with precision falling to
0.60 and 0.17 respectively. Everything else in the LLM-test-generation literature reports *code*
coverage or pass rates, not reference-suite coverage — a distinction that must be kept sharp, because
the frequently quoted "LLM tests match or beat human coverage" results are code-coverage results on
executable unit tests, a fundamentally easier task.

### Cited Findings — reference-suite recall (the directly comparable category)
- **Masuda et al., arXiv 2510.03641** (GPT-4o mini, temperature 0, fixed seed, 3 runs per document;
  methods: zero-shot, GHL = derive test design techniques then generate per technique, GHL-F = GHL plus
  function-combination cases). Full results table — [arXiv
  2510.03641 (HTML)](https://arxiv.org/html/2510.03641v1):

  | Dataset | Method | #Generated | Recall | Precision | F1 |
  |---|---|---|---|---|---|
  | Mozilla (19 truth) | zero-shot | 16 | **0.02** | 0.02 | 0.02 |
  | Mozilla | GHL | 108 | 0.20 | 0.07 | 0.10 |
  | Mozilla | GHL-F | 117 | **0.37** | 0.17 | 0.23 |
  | Bluetooth (90 truth) | zero-shot | 29 | 0.65 | 0.83 | 0.73 |
  | Bluetooth | GHL | 51 | 0.69 | 0.75 | 0.72 |
  | Bluetooth | GHL-F | 98 | **0.84** | 0.60 | 0.70 |

- Per-document variance inside one dataset is enormous: Mozilla GHL-F recall was **0.17 (Bookmarks),
  0.23 (History), 0.88 (Password Manager), 0.00 (Themes)** —
  [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- **Reporting inconsistencies in that paper** (relevant if you cite it as a baseline): the abstract and
  conclusion say Bluetooth recall 0.81 while Table IV says 0.84; the text gives GHL-F Bluetooth
  precision 0.62 and GHL precision 0.55 against the table's 0.60 and 0.75; the Mozilla GHL-F time is
  0:19:30 in text and 0:12:34 in the table; the aggregation rule (mean of per-document rates vs. pooled
  counts) is unstated and simple means do not reproduce the reported Mozilla averages (0.32 vs. 0.37
  recall) — [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- Their own stated explanation for the low Mozilla recall: requirement documents are small and
  heterogeneous (the "Themes" document is ~123 words and none of its truth cases were matched);
  similarity distributions are bimodal and overall low; low-similarity generated cases often address
  aspects unrelated to the reference cases (UI notifications, performance) —
  [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- **Zero-shot prompting is catastrophic for reference-suite recall** (0.02 on Mozilla) while
  structured, technique-first decomposition raises it 18× — the single largest reported effect of
  method design on this metric — [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)

### Cited Findings — protocol/conformance generators (specification coverage, not suite recall)
- **iPanda** (LLM agent for protocol conformance testing; keyword-based test case generation from the
  specification document, then RAG over the implementation to produce executable test code, plus
  iterative refinement). Evaluated on **CoAP and RSocket**; headline result is a **4.675× to 10.751×
  improvement in Pass@1 of test program generation over a pure-LLM baseline** — i.e. it reports
  executability, not coverage of a reference suite —
  [arXiv 2507.00378](https://arxiv.org/abs/2507.00378v1) · [HTML](https://arxiv.org/html/2507.00378v1)
- iPanda's own stated limitation: applicability and performance for specific or complex protocols
  requires further research — [arXiv 2507.00378](https://arxiv.org/html/2507.00378v1)
- **NeTestLLM** (multi-agent, hierarchical protocol understanding → iterative test case generation →
  executable artefacts → runtime feedback; deployed in production for several months). **4 632 test
  cases for OSPF, RIP and BGP**; covers **41 historical FRRouting bugs vs. 11 by current national
  standards**; **8.65×** efficiency improvement over manual methods in generating executable artefacts;
  evaluation is semi-quantitative key-section + semantic coverage —
  [arXiv 2510.13248](https://arxiv.org/html/2510.13248v1)
- **AutoSpec** takes the formal route instead: converts RFC prose into a formal protocol specification
  and generates tests from that specification with no LLM in the test-generation step, arguing this
  yields an inspectable specification that preserves traceability to the original text; evaluated on
  **SMTP, POP3, IMAP, FTP and ManageSieve** from their RFCs —
  [arXiv 2511.17977](https://web3.arxiv.org/pdf/2511.17977)
- **AI5GTest** (5G O-RAN, specification-aware): compares a generative LLM against GPT-4o and
  Gemini-1.5 on **test case procedural flow generation over 24 test cases**, and observes the
  closed-source models' procedures rely significantly on the test case *name* and the components listed
  in the prompt — a warning that apparent matches can come from the reference test's title leaking into
  the prompt — [arXiv 2506.10111](https://arxiv.org/pdf/2506.10111)
- **RAFT** (compliance test generation from regulations in financial, automotive and power domains)
  claims "expert-level performance" and substantial gains over state-of-the-art, with reduced
  generation and review time, but its abstract reports **no coverage, recall, precision or
  expert-agreement figure** — [arXiv 2601.09762](https://arxiv.org/abs/2601.09762)

### Cited Findings — code-coverage results (do NOT conflate with reference-suite coverage)
- **TDD-Bench Verified**: model-generated fail-to-pass tests achieve **0.91–0.95 coverage**, very close
  to developer-written tests, with the difference not statistically significant; other tests (e.g.
  fail-to-fail) fall **below 0.6** — [arXiv 2412.02883](https://arxiv.org/pdf/2412.02883)
- **LLMSuite (NLP libraries)**: manually written tests achieve mean branch coverage **33.99 %** vs.
  **68.49 %** for LLM-generated; combined **74.55 %** (a 27.7 % improvement). Caveat from the same
  paper: the manual baselines were weak, while actively maintained projects such as OpenNLP and
  CoreNLP had more comprehensive suites — [arXiv 2609.14784](https://arxiv.org/pdf/2609.14784)
- **ChatGPT unit tests** achieve coverage comparable to manual tests and the highest among the
  techniques compared — [No More Manual Tests?, arXiv 2305.04207](https://arxiv.org/pdf/2305.04207)
- **Automotive API case study (SPAPI-Tester)**: two engineers' manual suites averaged an **87.5 % pass
  rate** vs. **93–98 %** for LLM suites; coverage **82 %** manual vs. **73–85 %** LLM; failure
  detection **100 % recall for both**, precision 91 % manual vs. 90 % LLM — on a small sample of
  **10 APIs, 5 with known bugs** — [arXiv 2502.04008](https://arxiv.org/pdf/2502.04008)
- **Acceptance tests from functional requirements** can attain code coverage equivalent to
  human-devised ones (no exact figure in the retrieved excerpt) —
  [arXiv 2602.13611](https://arxiv.org/pdf/2602.13611)
- **Fault-exposure gap persists**: on TestCase-Eval (algorithmic problems), the best open model reached
  **43.8 % on fault exposure vs. 93.3 % for human experts** —
  [ACL 2025 short paper](https://aclanthology.org/2025.acl-short.82.pdf)
- A 2025 LLM comparison on requirement-based test generation notes that for larger systems
  LLM-generated tests usually still require manual validation by domain experts —
  [Test Case Generation for Requirements in Natural Language — An LLM Comparison Study,
  ACM](https://dl.acm.org/doi/10.1145/3717383.3717389)

### Inferences
- **Three distinct quantities must be labelled separately in the paper**, because the literature
  routinely blurs them: (a) *code coverage* of executable tests — where LLMs match or beat humans
  (0.91–0.95 on TDD-Bench; 68 % vs. 34 % branch coverage on LLMSuite); (b) *specification/clause
  coverage* — where NeTestLLM-style "key section coverage" lives and where high numbers are plausible;
  (c) *reference-suite recall under a semantic-equivalence criterion* — where the only published
  numbers are 0.37–0.84 under a much weaker matcher. Your 13.8 % belongs to category (c) and must be
  compared only to (c).
- Your 13.8 % and Masuda's 0.84 are **not on the same scale**, in at least four ways, all of which
  favour their number: (i) matcher strictness — cosine ≥ 0.7 topical similarity vs. your
  same-item/same-condition/same-outcome criterion; (ii) denominator size — 90 reference cases vs. 687,
  and small denominators make high recall far easier (their own per-document figures swing 0.00–0.88 at
  n≈5); (iii) generation budget — they generated 98 cases for 90 truth cases, a ~1.1 generation rate on
  a *narrow* document, whereas a whole-standard plan dilutes; (iv) edition alignment — their truth
  cases derive from the same document version they fed in. Stating these four differences converts
  "13.8 % looks bad" into "13.8 % is the first number reported under a strict criterion at scale".
- The AI5GTest observation (procedures rely on the test case *name*) is the strongest available
  argument that permissive matchers overstate: if a reference test's title is visible, topical
  similarity is nearly free. It supports your strict criterion and is worth citing as the reason for
  it.
- The honest comparable for your sub-metrics is the *grounded/actionable/correct-expected-result*
  triple (56/50/54 of 60 ≈ 93 %/83 %/90 %), which is the same kind of quantity as the "human evaluation
  survey confirmed the effectiveness of generated test cases" claims in the high-level-test-generation
  literature. Those papers report that qualitatively; yours reports it numerically, which is a
  strength, provided the judge is calibrated.

### Gaps
- Found **no published system that reports coverage of an official standards-body conformance suite**
  as ground truth. The conformance-testing generators (iPanda, NeTestLLM, AutoSpec, AI5GTest) report
  Pass@1, section coverage, bug coverage or qualitative coverage breadth — never recall against the
  official suite. If that holds up, your evaluation design is novel and should be positioned as such
  rather than benchmarked against an absent baseline.
- Masuda et al.'s venue: the arXiv listing (2510.03641) is the version retrieved; a peer-reviewed
  venue was not confirmed. "Automatic High-Level Test Case Generation using Large Language Models"
  (arXiv 2503.17998, MSR 2025) is peer-reviewed but its abstract reports only that "a final human
  evaluation survey confirmed the effectiveness of these generated test cases", with no reference-suite
  matching numbers retrievable from the abstract page.
- RAFT's actual numbers (closest work on regulation→compliance tests) were not retrievable from the
  abstract; the full paper would be needed.

---

## Is 85–90 % of a human conformance suite a plausible target?

### Takeaway
No. On the published evidence, 0.84 recall is the *maximum* reported against a human-written
high-level suite, and it was obtained under a permissive cosine-similarity matcher, on a single narrow
document with 90 reference cases, with precision collapsing to 0.60 and a sister dataset in the same
paper scoring 0.37. Under a semantic-equivalence criterion, on 687 reference tests, against a
different edition of the specification, 85–90 % is not a realistic target; a realistic engineering
ceiling is roughly 35–60 % and even that requires fixing the retrieval stage, the edition mismatch and
the generation strategy. The 85–90 % figure is achievable on a *different* metric — clause coverage of
the input standard — and the paper should either retarget it there or state it as an aspiration with
the evidence for why it is out of reach.

### Cited Findings
- Maximum published recall against an existing human high-level test suite: **0.84** (Bluetooth,
  GHL-F), with the same method scoring **0.37** on Mozilla; matcher = cosine ≥ 0.7 on
  `text-embedding-3-small`, which is topical similarity rather than semantic equivalence —
  [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- At that 0.84 recall, **precision was 0.60** with 98 generated cases against 90 truth cases: 40 % of
  generated cases matched nothing in the reference suite — [arXiv
  2510.03641](https://arxiv.org/html/2510.03641v1)
- Reference-suite recall is **highly sensitive to document scope**: per-document recall within one
  dataset spanned 0.00 to 0.88 — [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- Where LLMs *do* reach 0.91–0.95 against human tests, the metric is **code coverage of executable
  fail-to-pass unit tests**, not coverage of a reference suite, and even there a sibling category
  (fail-to-fail) drops below 0.6 — [arXiv 2412.02883](https://arxiv.org/pdf/2412.02883)
- Where LLM suites beat human suites outright (68.49 % vs. 33.99 % branch coverage), the paper itself
  notes the human baselines were weak and well-maintained projects had more comprehensive suites —
  [arXiv 2609.14784](https://arxiv.org/pdf/2609.14784)
- The fault-detection gap to human experts remains large on a controlled benchmark: **43.8 % vs.
  93.3 %** on fault exposure — [aclanthology 2025.acl-short.82](https://aclanthology.org/2025.acl-short.82.pdf)
- Even an LLM judge's *agreement with humans* tops out around Pearson 0.81 / Spearman 0.74 on the
  best-behaved SE task, below human inter-rater agreement of 0.86 / 0.83 —
  [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- Prompt-level bias effects in SE judging are large enough to change task-level conclusions and alter
  model rankings — so a judge-measured score has a wide, mostly unquantified error bar —
  [arXiv 2604.16790](https://arxiv.org/abs/2604.16790)
- Method design dominates: zero-shot 0.02 → technique-decomposed 0.20 → technique + function
  combination 0.37 on the same data; on Bluetooth 0.65 → 0.69 → 0.84 —
  [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- Union-of-techniques retrieval raised traceability recall from <40 % to **93 %** in the artefact-linking
  setting — the only retrieved evidence of a technique that pushes a matching-based recall into the
  high 80s/90s, and it worked by *adding matchers*, not by improving the generator —
  [SBES](https://sol.sbc.org.br/index.php/sbes/article/view/17022)

### Inferences
- The conditions under which something close to 85–90 % has been reported are all absent from your
  setting: narrow single-feature documents with ~5–90 reference cases; a permissive topical matcher;
  reference tests derived from the same document version; and a tolerance for precision at 0.60.
  Reviewers who know the Masuda numbers will not accept 85–90 % under a strict criterion as a credible
  target, and will accept the ceiling argument if you make it explicitly.
- A credible headline structure: report **clause coverage** of normative requirements (where 85–90 % is
  defensible and verifiable without the reference suite), and report **reference-suite recall** as the
  strict secondary metric with a stated ceiling argument and an upper bound for the measurable
  fraction. Specifically, of 907 official tests, 687 cite a clause, and some fraction of those cite
  2021-only text — so the *measurable* denominator is strictly smaller than 687 and must be computed
  and reported (see next section). Recall against the measurable denominator is the number that can
  honestly be pushed.
- **For a test-purpose suite specifically, 85–90 % is plausible only on the genre's native metric,
  which is not suite-to-suite recall.** ISO/IEC 9646-2's own coverage concern is coverage of
  *conformance requirements by test purposes*; the suite-to-suite direction has no standard metric and
  no published figure anywhere near 0.85 under a strict criterion. So the honest construction is:
  claim 85–90 % for **clause coverage** (normative requirements of the input standard addressed by at
  least one generated test purpose) and/or for **family/clause-level breadth** against the official
  taxonomy, and report strict per-TP recall as the hard number with its ceiling argument. Note also
  that the only >0.8 datapoint in the literature came from a **Bluetooth specification document with
  90 reference cases** — a specification-derived suite much like yours but two orders of magnitude
  narrower, and matched by cosine ≥ 0.7 rather than by block equivalence
  ([arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)).
- Expect realistic improvement from, in descending order of likely effect: (1) restricting the
  denominator to officially-testable, in-edition clauses; (2) a structured, technique-first generation
  strategy (the 18× effect in Masuda); (3) a better retrieval stage (embeddings + union with lexical,
  larger k, measured recall@k); (4) partial credit. A move from 13.8 % to the 35–55 % band is a
  plausible, defensible claim; 85–90 % under a strict criterion is not supported by any published
  result.

### Gaps
- No study reports an *asymptote* or a theoretical ceiling for reference-suite recall, so the "realistic
  ceiling" band above is an inference from the distribution of published numbers (0.02–0.84 under a weak
  matcher; 0.37–0.84 for the best method), not a cited figure. Flag it as such in the paper.
- No data on how much stricter a semantic-equivalence criterion is than cosine ≥ 0.7. This is directly
  measurable in your harness by scoring the same 687 tests under both matchers and reporting the ratio
  — the single most useful experiment for calibrating your number against the literature.

---

## Methodological advice: version mismatch, partial credit, reporting conventions

### Takeaway
There is no retrieved publication on specification-edition mismatch between an input document and a
reference suite, so this must be handled with standard benchmark hygiene rather than a citation:
stratify the reference suite into in-edition and out-of-edition tests, report both the raw and the
"measurable-denominator" score, and treat the out-of-edition stratum as a diagnostic (a generated test
matching 2021-only text is evidence of memorisation, not generalisation). Partial credit is likewise
uncited for test-suite matching; the transferable conventions come from traceability evaluation
(ranked + set-based measures reported together, recall prioritised over precision) and from judge
calibration (κ against a human-labelled stratified sample with reweighting, calibration set held out
from prompt development).

### Cited Findings — version/edition mismatch and benchmark contamination
- **Possible training-data overlap is a recognised threat in exactly this evaluation design**: the
  Bluetooth and Mozilla documents used as ground truth are public and may appear in the LLM's training
  data, which could inflate results (noted as an unraised threat in the critique of
  [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1))
- The same risk is identified from the generator side in 5G testing: closed-source models' generated
  procedures rely significantly on the **test case name and the components listed in the prompt**,
  i.e. the model can reproduce a reference test without deriving it from the specification —
  [arXiv 2506.10111](https://arxiv.org/pdf/2506.10111)
- The formal-specification alternative is motivated explicitly by traceability to the original text:
  AutoSpec converts RFC prose to an inspectable formal specification so that generated tests preserve
  traceability to the source clauses — the architectural answer to "which edition does this test come
  from" — [arXiv 2511.17977](https://web3.arxiv.org/pdf/2511.17977)

### Cited Findings — partial credit and matching conventions
- **Many-to-many matching is the published convention**, not one-to-one: Masuda et al. allow one truth
  case to match several generated cases and one generated case to match several truth cases, and define
  recall and precision over *unique matched* items on each side, which is what makes the two metrics
  independent — [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- **Graded rather than binary matching is standard in trace retrieval**: report Average Precision /
  Mean Average Precision for the ranked candidate list *and* an interpolated precision-recall graph,
  because ranked and set-based measures answer different questions —
  [arXiv 1807.11454](https://arxiv.org/pdf/1807.11454) ·
  [U. Kentucky dissertation](https://uknowledge.uky.edu/cs_etds/5)
- **F2 as well as F1** is used in traceability work when recall is weighted above precision —
  [arXiv 1807.11454](https://arxiv.org/pdf/1807.11454)
- **Recall-over-precision is a justifiable, cited choice** in this artefact-matching setting: detecting
  a false positive is much simpler and faster than discovering an error of omission —
  [arXiv 1807.11454](https://arxiv.org/pdf/1807.11454)
- Different denominators answer different questions and must not be mixed: requirement coverage and
  branch coverage have different denominators (practitioner guidance, non-normative) —
  [Measuring test coverage beyond code coverage](https://macmyths.com/how-to-measure-test-coverage-beyond-code-coverage/)
- NL test cases **lack standardised quality metrics**, which is why NeTestLLM resorts to a
  semi-quantitative key-section + semantic coverage scheme — a citable acknowledgement that the field
  has no agreed metric, licensing a clearly-defined bespoke one —
  [arXiv 2510.13248](https://arxiv.org/html/2510.13248v1)

### Cited Findings — judge-calibration reporting a reviewer will expect
- Report **human–human agreement alongside LLM–human agreement, computed on the same items with the
  same metric**; pick the statistic by annotation design (Cohen's κ / weighted κ / Krippendorff's α);
  report the confusion matrix, per-class counts, precision/recall/F1 and uncertainty intervals, not κ
  alone; build the gold label by adjudication or majority vote and keep low-consensus items; have
  labellers work independently before discussion; keep the calibration set separate from the examples
  used to write or tune the judge prompt —
  [Arize](https://arize.com/blog/measuring-human-llm-judge-alignment/) ·
  [Oneuptime](https://oneuptime.com/blog/post/2026-08-31-calibrate-llm-judge-cohens-kappa/markdown)
- **Stratified sampling with reweighting** is the practical design when full human labelling is too
  expensive: label every judge-disagreement case plus a random sample of agreement cases, then reweight
  strata by frequency; that study reports κ = 0.83 judge-vs-human and 0.76 judge-vs-judge, and notes
  the two judges erred in **opposite directions** — [arXiv 2609.26241](https://arxiv.org/pdf/2609.26241)
- **Report bias sensitivity alongside accuracy**, with explicit controls, so SE model comparisons are
  trustworthy — [arXiv 2604.16790](https://arxiv.org/abs/2604.16790)
- **Validate the judge per task before relying on it**; prefer individual scoring to pairwise; for
  tasks where judge–human correlation is weak, use the judge alongside conventional metrics —
  [arXiv 2502.06193v3](https://arxiv.org/html/2502.06193v3)
- Multi-axis reporting is the norm for generated-test evaluation (TestBench: syntactic correctness,
  compilation correctness, test correctness, coverage rate, defect detection rate) —
  [arXiv 2409.17561](https://arxiv.org/html/2409.17561v1)
- Report a **redundancy/diversity statistic** on the generated side, cov@k-style, so a high recall
  cannot be bought with near-duplicates — [arXiv 2407.00225](https://arxiv.org/abs/2407.00225)
- **Deterministic, repeated runs** are the convention: fixed seed, temperature 0, each document
  processed three times per method — [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)
- The same paper demonstrates by negative example what reviewers punish: unstated aggregation rule,
  abstract/table disagreement (0.81 vs. 0.84), threshold stated as both 0.7 and 0.65, no variance or
  significance reporting on four documents × three runs, and an unspecified expert-validation protocol
  — [arXiv 2510.03641](https://arxiv.org/html/2510.03641v1)

### Inferences — concrete protocol to adopt
- **Stratify the denominator and report three numbers.** (a) raw recall over all 687 clause-citing
  tests; (b) recall over the *in-edition* stratum — official tests whose cited clause exists with
  equivalent normative content in the 2020 draft; (c) recall over the *out-of-edition* stratum,
  reported separately and expected to be near zero. Report the stratum sizes. (b) is the scientifically
  meaningful score; (a) is the conservative one; a non-trivial (c) is a **memorisation signal** worth
  reporting as such. This single change is likely the largest honest improvement available and it is
  also the correct fix for the threat, not a workaround.
- **The genre makes the edition problem tractable, because the `Reference` field is the RQ ref.** In the
  TPLan/9646 structure the requirement reference is a first-class header field, not prose, and 9646-2
  treats requirement→TP traceability as normative. So the edition stratification is a join on that
  field, not an inference: for each official TP, resolve its cited clause in the 2021 edition, locate
  the corresponding clause in the 2020 draft, and classify the normative text as
  *unchanged / reworded / changed / absent*. Report the four counts. Only *unchanged* and *reworded*
  clauses belong in the scored denominator; *changed* and *absent* go to a separately reported stratum.
  This is auditable, generalises to any standard with clause-referenced test purposes, and — crucially
  — is a legitimate fix for the threat rather than a workaround, because a test whose requirement text
  is absent from the input is unanswerable by construction.
- **Three distinct denominators exist and all three should be stated.** 907 total cases; 687 citing a
  clause of the standard under test; and the in-edition subset of those 687. The 220 cases that do not
  cite a clause of the standard under test are, by the suite's own `Reference` field, grounded in
  external specifications such as RFCs — i.e. they test requirements that are *not in the input
  document at all* and are outside the tool's remit unless the external specs are also supplied.
  Saying this explicitly, with the counts, converts an apparent 13.8 %-of-907 into a correctly scoped
  figure and pre-empts the obvious reviewer question. If the external references are resolvable, a
  second experiment that supplies the cited RFCs and re-measures that stratum is the clean way to show
  the limitation is an input-scope limitation rather than a generator limitation.
- **Make the edition mapping mechanical and auditable**, since it must generalise to any standard:
  match official tests to input clauses by clause number, then verify normative-text equivalence
  between editions (diff the clause text; classify as unchanged / reworded / changed / absent). Report
  the classification counts. "Absent" and "changed" clauses go to the out-of-edition stratum.
- **Partial credit with a defensible shape, derived from the genre's own notation rather than invented.**
  The TPLan block structure (`RQ ref` + `with {precondition}` + `ensure that { when {stimulus} then
  {expected response} }`) gives four natural match predicates, and the official records map onto them
  one-to-one (Reference → RQ ref; Technology/Profile/Preconditions → `with` + Config; Test scenario →
  `when`; Expected results → `then`), with the ID taxonomy supplying SUT and object. So score a
  candidate against an official TP as a **vector of block verdicts**, not a scalar:
  `(same SUT, same object, same check type, same applicability condition, same expected outcome)`.
  Then report, in this order:
  1. **Strict recall** — all blocks agree. This is the headline and is what the current 13.8 % means.
  2. **Core recall** — SUT + object + check type + expected outcome agree, applicability condition
     differs. This is the "right test, wrong profile/technology" case and is the single most defensible
     partial-credit level, because in the 9646 tradition applicability is carried by the ICS/profile
     and the *same* TP is routinely instantiated under several applicability conditions (ETSI even
     splits the TSS&TP per SUT into separate documents). A generated case that checks the right object
     and outcome but names the wrong profile is a parameterisation defect, not a missing test.
  3. **Intent recall** — SUT + object + check type agree, expected outcome differs. Report this
     *separately and never merge it into a coverage headline*: a different expected outcome means the
     test would pass a non-conforming implementation, so it is a correctness failure. Reporting it is
     valuable as a diagnostic (and ties to the 54/60 "correct expected result" sub-score), but counting
     it as coverage would be the move a reviewer rejects.
  4. **Family/clause recall** — at least one generated case in the official case's ID family or cited
     clause. Breadth, judge-free, computable from the taxonomy.
  Report 1 and 4 as the two headline numbers, 2 as credited partial coverage with the criterion stated,
  and 3 as a diagnostic only. This is consistent with the rubric-decomposition advice for judges, keeps
  the strict number intact and auditable, and avoids inventing a similarity-weighted score that has no
  citation behind it.
- **Do not use a single weighted sum of the block verdicts.** Any weighting is arbitrary and a reviewer
  will attack it; a vector of named levels with explicit definitions cannot be attacked the same way,
  and the traceability literature's own convention is to report several measures side by side (ranked
  plus set-based) rather than to fuse them.
- **Also report retrieval recall@5 separately**, measured on a human-labelled sample, so the
  generator's failure is separable from the retriever's. Masuda's threshold-sensitivity problems and
  the term-mismatch literature both predict the retriever is a material loss channel.
- **Judge-calibration plan matching the published conventions**: sample ~100–150 official tests
  stratified by judge verdict (all or most positives, plus a random sample of negatives, reweighted by
  stratum frequency); two independent human labellers using the written rubric, adjudicating
  disagreements; report human–human κ and judge–human κ on the same items with the confusion matrix and
  per-class counts; run a **second judge from a different model family** over the full 687 and report
  both scores plus their κ; hold the calibration items out of any prompt tuning. Report error
  direction, not just agreement.
- **Threats-to-validity section the reviewers will look for**: construct validity (lexical retrieval
  caps measurable matches; semantic-equivalence criterion is stricter than published cosine thresholds,
  so the number is not comparable to 0.84); internal validity (same-family judge, position bias within
  the candidate list, prompt sensitivity, argued direction of bias); external validity (one standard,
  one suite; edition mismatch; whether the method transfers to standards without a published suite);
  conclusion validity (single run vs. repeated runs with a seed, no significance testing, denominator
  ambiguity). Each of these has a citation above.

### Gaps
- **No publication found on specification-edition/version mismatch between an input document and a
  reference test suite.** This appears genuinely uncovered; the nearest-adjacent literature is
  benchmark data contamination and the traceability work's treatment of vocabulary drift. The protocol
  above is constructed from general benchmark hygiene, not cited.
- **No publication found defining partial credit for a generated test that covers part of a reference
  test.** Traceability work grades the *ranking* of candidate links, not the *completeness* of a match.
  The rubric-decomposition approach above is an inference.
- Could not locate an ACM TOSEM article on LLM-as-judge in software engineering; if the paper needs a
  TOSEM citation specifically, the venue claim should be verified against TOSEM issue listings before
  use. The solid peer-reviewed anchor is ISSTA 2025 (arXiv 2502.06193).
- No peer-reviewed guideline document for LLM-judge calibration reporting; the conventions cited are
  practitioner guides plus one applied preprint, which is weak citation material for a research paper.
