# Running the generator and its evaluation on another machine

The repository carries the tool, its tests, two redistributable fixtures and the evaluation harness.
It deliberately does not carry the ISO documents or any secret, so three things have to be copied by
hand. Everything below assumes a local Ollama daemon, which needs no API key and, unlike Ollama
Cloud, enforces the JSON schema the tool sends.

## 1. Get the code

The work is on the branch `feat/test-model`; `master` is still at the planning commit.

```
git clone git@github.com:LucaCeccarelli/TestPlanGenerationTest.git
cd TestPlanGenerationTest
git checkout feat/test-model
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

## 3. Check the model

```
ollama list
```

The tool defaults to `gemma4:31b`. Pass `--model <tag>` for anything else, and use the same tag for
the evaluation. A wrong or absent tag fails immediately with a clear message rather than part way
through a run.

## 4. Verify the install

```
uv run pytest -q -m "not slow"                 # no network, about a minute
TPG_E2E=1 uv run pytest -m slow -v -s          # four real runs on small clause subsets
```

The slow suite is the real check that the model and the pipeline agree: it asserts zero gaps on four
documents. Expect roughly ten to twenty minutes on a local model. If it reports gaps, send the gap
reasons; they say which stage disagreed with the model's output.

## 5. Generate a plan

```
uv run tpg generate tests/fixtures/iso_18013_5.pdf --out plan.json
uv run tpg generate tests/fixtures/iso_18013_5.pdf --out plan.json --clauses 7.4.1,9.2.2.4
uv run tpg generate tests/fixtures/iso_18013_5.pdf --out plan.json --no-model
```

Exit code 0 means no gaps, 2 means the plan was written but something could not be produced, 1 means
a bad input or an unreachable model.

**Budget the time.** The tool makes one model call per coverage item, and the full ISO document
produced about 4000 of them. On a local 31B that is a long run, plausibly overnight; on a subset of
clauses it is minutes. Scope a first pass with `--clauses`, confirm the output looks right, then
decide whether to spend a night on the whole document. `--no-model` skips the object stage and costs
roughly a third as many calls, at the price of the granularity the object stage exists for.

`OLLAMA_TIMEOUT` bounds each call and defaults to 120 seconds. A cold load of a large model can
exceed that, so warm it once (`ollama run <tag> hi`) or raise the variable; the evaluation runner
does both for you.

## 6. Run the evaluation

```
tools/eval/run.sh tests/fixtures/iso_18013_5.pdf /path/to/appendices [model]
```

It warms the model, parses the appendices into ground truth, generates the plan, judges how many of
the official test cases a generated case covers, samples 60 generated cases for validity, and prints
a summary. Everything lands in `eval/`, which is gitignored because the outputs quote the documents.

The two judging steps are themselves model calls, roughly 700 and 60 of them, so allow for that.

## 7. What to report back

The last thing `run.sh` prints is the whole summary, also saved to `eval/summary.txt`. That block is
enough to compare against the previous numbers. If the files can come back too, `eval/plan.json`,
`eval/judge_results.json` and `eval/precision_results.json` allow a per-clause analysis.

Previous measurement, for comparison, from the version before the test-model stage:

| | before |
|---|---|
| requirements | 215 |
| test cases | 428 |
| coverage of the official suite | 4.2 % |
| generated cases grounded / actionable / correct | 52 / 50 / 51 of 60 |
