# Running the generator and its evaluation on another machine

The repository carries the tool, its tests, two redistributable fixtures and the evaluation harness.
It deliberately does not carry the ISO documents or any secret, so three things have to be copied by
hand. Everything below assumes a local Ollama daemon, which needs no API key and, unlike Ollama
Cloud, enforces the JSON schema the tool sends.

Written against commit `b9a6421` of `feat/conformance-methodology`, with the fixes to
`cli.py` and `pipeline.py` still uncommitted in the working tree as it was written. The flags, the
environment variables, the log lines and the exit codes below were read off that state. Two things
could not be confirmed against a commit and are marked where they appear: that `--out` is probed for
writability at startup, and that the run persists as it goes into `<out>.partial.json` and
`<out>.cases.jsonl`. Both were present in the working tree and both only help; sections 5 to 7 are
correct whether or not they land.

## 1. Get the code

The work is on the branch `feat/conformance-methodology`; `master` is still at the planning commit.

```
git clone git@github.com:LucaCeccarelli/TestPlanGenerationTest.git
cd TestPlanGenerationTest
git checkout feat/conformance-methodology
uv sync
```

`uv` installs Python 3.12 or newer itself if the machine has none.

## 2. Copy what git does not carry

| What | Where it goes | Why it is not in git |
|---|---|---|
| `iso_18013_5.pdf` | `tests/fixtures/iso_18013_5.pdf` | an ISO text, not redistributable |
| the three `Appendix_*_to_ISO_IEC_*TS_18013_6_2025.pdf` files | any directory, passed as an argument | the same |
| `.env` | repository root | holds a key; not needed at all for a local daemon |

Without the ISO fixture the test suite still passes: the tests that need it skip.

## 3. The model and the server

```
ollama list
```

The tool defaults to `gemma4:31b`. Pass `--model <tag>` for anything else, and use the same tag for
the evaluation. A wrong or absent tag fails immediately with a clear message rather than part way
through a run.

**Client-side environment variables**, all read by `tpg/llm.py`:

| variable | default in the code | what to do |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | leave it alone for a local daemon |
| `OLLAMA_API_KEY` | unset | only for a server that wants a bearer token |
| `OLLAMA_TIMEOUT` | **120** seconds per call | **raise it to 600** for any real run: `tools/eval/run.sh` already exports `600`, but a manual `uv run tpg generate` does not, and a batched call that writes four to six test cases from a 31B model is a long call. A timeout counts as one failed attempt, so a short timeout turns into gaps, not into an error |
| `TPG_EVAL_MODEL` | `gemma4:31b` | the model the judge and precision scripts use; `run.sh` sets it from its third argument |
| `TPG_E2E` | unset | set to `1` to let the slow test suite talk to a real model |

**Server-side settings**, on the machine running `ollama serve`:

- `OLLAMA_CONTEXT_LENGTH` should be at least `8192`. The tool never sends `num_ctx`, so the server's
  own default decides the window, and Ollama 0.20 picks 4k, 32k or 256k from the available VRAM: a
  31B model on one GPU can well be served a 4k window. Measured prompt sizes on the ISO fixture are
  up to 12.6 KB for an extract prompt and 13.3 KB for a generation prompt, which is 3 to 4 thousand
  tokens before the reply is counted. An over-long reply is salvaged (the finished cases of a
  truncated JSON array are kept) rather than lost, but the rest of that batch becomes gaps.
- Keep the model resident: `OLLAMA_KEEP_ALIVE=4h` or longer. A cold load of a 31B model can exceed
  even a 600-second per-call timeout, and a long run with any idle gap otherwise pays that load
  again mid-run. `run.sh` warms the model once before the long step for the same reason.
- Leave `OLLAMA_NUM_PARALLEL` at 1. The tool issues one request at a time, and a higher value only
  divides the context window between slots.
- Use the local daemon, not Ollama Cloud: the local server enforces the JSON schema the tool sends,
  and that enforcement is what keeps the reply parseable.

## 4. Verify the install

```
uv run pytest -q -m "not slow"                 # no network, about two minutes
TPG_E2E=1 uv run pytest -m slow -v -s          # four real runs on small clause subsets
```

The fast suite was 469 passed, 1 skipped in 131 s at the commit above; the skip is the e2e test that
wants `TPG_E2E`. The slow suite is the real check that the model and the pipeline agree: it asserts
zero gaps on four documents, and it also asserts the ICS guarantee of section 9. Expect roughly ten
to twenty minutes on a local model. If it reports gaps, send the gap reasons; they say which stage
disagreed with the model's output.

## 5. One cheap check before the long run

The most expensive mistake available here is to discover a problem six hours in, because nothing is
written until the run ends. Spend three minutes first:

```
mkdir -p eval
OLLAMA_TIMEOUT=600 uv run tpg generate tests/fixtures/iso_18013_5.pdf \
    --clauses 8.2.1.1,9.2.2.4 --out eval/smoke.json > eval/smoke.log 2>&1
echo "exit $?"        # 0 or 2 is fine, 1 is not; do not pipe this, a pipe reports tee's status
tail -5 eval/smoke.log
uv run python -c "import json; p=json.load(open('eval/smoke.json')); print({k: len(v) for k, v in p.items() if isinstance(v, list)})"
```

This proves the model answers, that the clause ids exist in the ingest, that `eval/` is writable, and
what a gap looks like, for the price of a few dozen calls. Read one or two of the generated cases; a
run is only worth six hours if the cases are worth reading.

## 6. Create the output directory before anything is redirected into it

`mkdir -p eval` first, every time. Two ways this has already cost a run:

- `... | tee eval/plan.log` fails instantly if `eval/` does not exist, and so does any `> eval/...`
  redirection, before the generator has done anything.
- The plan itself is written only at the very end, by `write_plan`. The working-tree version of
  `cli.py` probes `--out` for writability before the first model call and the pipeline writes two
  sidecars beside it during the run (`<out>.partial.json` with every stage but generation, and
  `<out>.cases.jsonl` with one record per case or gap as it arrives), so a missing directory fails in
  the first seconds instead of after six hours and a crashed run keeps its cases. Neither was
  committed when this was written, so do not rely on them: the smoke run of section 5 proves the same
  thing for the price of a few calls.

## 7. Generate a plan

```
mkdir -p eval
export OLLAMA_TIMEOUT=600
uv run tpg generate tests/fixtures/iso_18013_5.pdf --out eval/plan.json 2>&1 | tee eval/plan.log
```

The five flags, each disabling exactly one stage or rule so that its contribution is the difference
between two runs on the same input:

| flag | what it measures | why you would set it |
|---|---|---|
| `--clauses 8.2.1.1,9.2.2.4` | nothing; it scopes the run | the only way to try the pipeline in minutes. An unknown id is an error, not a silent skip |
| `--no-model` | what the LLM test-model stage adds over the deterministic stages | it removes 242 of the clause-level calls on the ISO fixture and leaves the 152 objects the grammar stage reads out of the formal declarations. Compare `objects`, `ics` and `coverage_items` against the full run |
| `--no-grammar` | what the formal declarations (CDDL, ABNF, JSON Schema, ASN.1) add | the objects of `origin: "grammar"` and everything derived from them disappear; on the ISO fixture that is 152 objects |
| `--no-deflate` | the cost of the two deflation rules | the difference in `coverage_items` is exactly what the generic-group and overlap rules removed. Deflation cannot change ICS coverage, so a difference there would be a defect |
| `--no-batch` | the cost of batching | one model call per coverage item instead of one per source, with the same plan, so case quality can be compared at a known call count. Roughly twice the calls of the batched path on a real item distribution |

**Budget the time.** Batching is the default now, and the cost is three stages of calls:

| stage | calls on the ISO fixture | how it was counted |
|---|---|---|
| extract, one per clause text chunk | **181** | measured with a stub model that answers nothing, so it is a floor: a failed chunk is retried up to `--attempts` times |
| test model, one per clause | **242** | the same stub; skipped entirely by `--no-model` |
| generate, one per source carrying up to 8 of its coverage items | about **1600** | the branch review's projection over the last recorded full run's item distribution (1611 sources). `--no-batch` makes this one call per item instead |

So order 2000 calls for a full run. The one measured full run of the previous iteration took
**45557 s (12.7 hours)** for 3257 per-item generation calls at about 10.7 s per call; the ledger's
estimate for the batched path on the same machine class is **about 6.3 hours**. Treat both as
order-of-magnitude on different hardware, and scope a first pass with `--clauses`.

**Watch it, and let it survive the terminal.** The pipeline logs to stderr, one line per clause in
extract and in the test model and one line per source in generate, so the log grows steadily while
the plan file stays absent until the end. Start it detached and watch the log:

```
mkdir -p eval
OLLAMA_TIMEOUT=600 nohup uv run tpg generate tests/fixtures/iso_18013_5.pdf \
    --out eval/plan.json > eval/plan.log 2>&1 &
tail -f eval/plan.log         # or: wc -l eval/plan.log, repeated
```

A log that has not grown in several minutes means the call in flight is stuck, which the timeout
will turn into a gap; a log that has not grown in much more than the timeout means the server is
gone. The last lines of a healthy run are the counts and the `ICS coverage` line. If the sidecars of
section 6 are in the version you cloned, `wc -l eval/plan.json.cases.jsonl` counts the generated
cases directly, and `eval/plan.json.partial.json` already holds every stage but generation.

**Exit codes.** 0 means no gaps; **2 means the plan was written but some clause or coverage item
ended in `gaps`** -- that is the normal outcome of a real run and not a failure, the plan is complete
and usable, and `plan.gaps` is itself a result worth reporting; 1 means a bad input, an unknown
clause id, an unwritable output or an unreachable model, and nothing was produced. `run.sh` lets a
non-zero exit through on purpose, so one gap does not abandon the evaluation.

## 8. Run the evaluation

```
tools/eval/run.sh tests/fixtures/iso_18013_5.pdf /path/to/appendices [model]
```

It creates `eval/`, exports `OLLAMA_TIMEOUT=600` if it is unset, and runs five steps, writing a
`.log` beside each artefact:

1. `parse_appendices.py` turns the three appendix PDFs into `eval/ground_truth.json`. No model.
2. `tpg generate` writes `eval/plan.json` and `eval/plan.log`. The long step, with the wall time
   appended to the log.
3. `match_structural.py` writes `eval/match_results.json`: the judge-free structural match of the
   official cases against the plan. **No model**, so this figure exists even if the model dies, and
   it carries none of the self-preference of a judge drawn from the generator's own model family.
4. `judge.py` writes `eval/judge_results.json`: one model call per official case that cites a clause
   of the standard under test, **687 calls** on this suite, checkpointed to disk every 25 cases and
   printing progress to stderr as it goes.
5. `precision.py` writes `eval/precision_results.json`: **60 model calls**, one per sampled
   generated case, judging it grounded, actionable and correct against its own clause.

Then `summarise.py` prints everything, also saved to `eval/summary.txt`. Steps 4 and 5 cannot fail
the run, and every script prints its sections with its inputs missing and no model reachable, so a
partial evaluation still produces a summary.

Everything lands in `eval/`, which is gitignored because the outputs quote the documents.

## 9. How to read the three headline numbers, before you quote any of them

**ICS coverage is a guarantee, not a score.** The derive stage emits one `capability` coverage item
per mandatory or optional ICS item by construction, and no deflation rule can remove it, so the
`ICS coverage P% (covered/due)` line is 100 per cent in every run and in all sixteen flag
combinations and cannot be otherwise unless derive is broken. The summary labels it `(invariant)`.
The figure that carries information is its **denominator**, the ICS item count: a claim about how
many testable features the tool found in the document, which needs no official suite and is what
compares across runs and across standards. The share of due items whose every coverage item did get
a test case is labelled `(measured)` and can fail.

**The structural match rate is a rate over a population that moves.** A case counts only if the
rules infer both a data item and a check type from its wording, and only if the plan names the
source that data item points at. Requirements only gained a `name` late in this branch, which made
about 1575 previously keyless coverage items scorable, worth roughly 4 points of rate by the branch
review's projection and no more coverage of the standard at all. Both the matcher and the summary
therefore print a `scorable population` block, and the match twice: over every named source, and
over the named objects alone, which is the figure comparable with the earlier runs. **Quote a rate
only together with its population block.**

**The suite has three denominators** -- all official cases, those citing a clause of the standard
under test, and those whose cited clause id exists in the ingested input -- and the score is stated
against the third. An absent clause id is either another edition's numbering or a clause the ingest
never segmented, and separating those two needs a human crosswalk.

## 10. What to send back

The whole of `eval/summary.txt` as text, plus these files:

| file | what it is for |
|---|---|
| `eval/summary.txt` | the block that is compared against previous numbers |
| `eval/plan.json` | everything; allows any per-clause or per-item re-analysis |
| `eval/plan.log` | the per-clause and per-source log, the gap reasons and the wall time |
| `eval/match_results.json` | the structural verdict and inferred pair per official case |
| `eval/judge_results.json` | the judge verdict and its reason per official case |
| `eval/precision_results.json` | the 60 sampled cases with the judge's reasons |
| `eval/ground_truth.json` | only if the appendix parse looks wrong; it is large and quotes ISO text |
| `eval/plan.json.partial.json`, `eval/plan.json.cases.jsonl` | only if the run died before writing the plan: between them they hold everything it had reached. A finished run deletes them |

Also send the exit code of the generate step, `ollama --version`, the GPU and VRAM of the machine,
and the values of `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_KEEP_ALIVE` and `OLLAMA_TIMEOUT` actually in
force. Everything in `eval/` quotes the ISO documents, so send it privately and never commit it.

## 11. Previous measurement, for comparison

From the last full run of the **previous** iteration (`eval/eval_remote_1`, 3257 coverage items, no
ICS stage, requirements with no `name`, unbatched generation). The structural and judge rates below
are over that run's population, which section 9 says is not this run's population:

| | previous run |
|---|---|
| requirements / objects | 842 / 921 |
| coverage items / test cases / gaps | 3257 / 3231 / 66 |
| ICS items | not produced by that version |
| structural match of the official suite | 22.5 % (168 of 747 scorable; 18.5 % of all 907) |
| LLM judge | 13.8 % (95 of 687) |
| sampled cases grounded / actionable / correct | 56 / 50 / 54 of 60 |
| wall time | 45557 s (12.7 h) |

For this branch, the branch review projects 1463 ICS items and about 4629 coverage items from the
same sources (x1.42), with the generation calls roughly unchanged because the new items ride along in
existing batches. Those are projections, not a run: the run you are about to do is the first real
measurement of them.
