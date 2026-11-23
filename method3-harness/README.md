# Method 3: agentic harness

The third method of the article: the same task (a conformance test plan from the text of
ISO/IEC 18013-5) given to an industrial agentic harness, Claude Code, with Anthropic models and with
open-source models. There is no pipeline here: the method is the prompt below.

No run has been made yet. Results go into the "Method 3" section of
`../docs/article/experiments.tex`.

## Running it

1. Copy the standard to `input/iso_18013_5.pdf` (ignored by git, like `output/` and `work/`).
2. Start Claude Code from this directory with no customization (skills, plugins, hooks, MCP servers,
   `CLAUDE.md`) and no web access, and give it the prompt below, unchanged for every model:
   ```bash
   claude --safe-mode --disallowedTools "WebSearch,WebFetch"
   ```
3. Note the model, the wall time and the token cost of the run.
4. Score `output/plan.json` with the evaluation scripts of method 2
   (`../method2-deterministic/tools/eval/`); the plan format is the same.

The prompt forbids reading this README, the web and anything outside this directory, but a prompt
rule is not enforced. Two things make it hold:

- Deny the tools in the permission settings of the run: web search, web fetch, and `Read` on
  `README.md` and on `../`.
- Claude Code loads the `CLAUDE.md` of parent directories by itself, and the one at the root of this
  repository names the ground truth. Run from a copy of this directory outside the repository to
  avoid it.

## At the end of a run

Before closing the session, keep a trace of it in `trace/` (ignored by git: it quotes the standard).
In Claude Code:

1. `/status` shows the Claude Code version and the model: copy both into `trace/run.md`.
2. `/usage` shows the cost and token use of the session: copy them into `trace/run.md`, with the
   start and end time of the run.
3. `/context` shows what filled the context: check that no skill, MCP server or `CLAUDE.md` appears.
4. `/export trace/session.txt` writes the whole conversation to a file.

Then, in a terminal:

```bash
# The raw transcript (every tool call, with timestamps) is the exact record of the run.
# Claude Code stores it under ~/.claude/projects/, in a folder named after the run directory.
cp ~/.claude/projects/*tpg-method3-run1*/*.jsonl trace/
sha256sum input/iso_18013_5.pdf output/plan.json >> trace/run.md
```

If the run was made from a copy outside the repository, copy `output/`, `work/` and `trace/` back
into this directory, in a subfolder per run (for example `runs/<model>-<date>/`) once there is more
than one.

## Prompt

```txt
You are given one document: input/iso_18013_5.pdf (ISO/IEC DIS 18013-5:2020, 126 pages).
Your task is to write a conformance test plan for it: the set of test cases a test
laboratory would run to decide whether an implementation (an mDL or an mDL reader)
conforms to this standard.

## Rules

1. Your only source is input/iso_18013_5.pdf. Do not search the web. Do not read any
   file outside this directory. Do not use ISO/IEC TS 18013-6 or any existing test
   suite for this standard, including from memory: every test case must be derived
   from the text of the PDF.
2. Do not read README.md or any other file already present in this directory, except
   input/iso_18013_5.pdf. You may read the files you create yourself.
3. Cover the whole document, including annexes and tables, not a sample. Work clause
   by clause and keep a progress file (work/progress.md) listing each clause and its
   status, so that you can resume without redoing or skipping anything.
4. Never invent. Every requirement and every object carries a `source_quote` copied
   verbatim from the PDF. If you cannot produce a sound test case for something,
   record a gap with the reason instead.
5. Do not stop to ask questions. Make a reasonable choice and note it in work/notes.md.
6. Write no test code. Test cases are descriptions a test engineer can execute.

## Method

You are free to organise the work as you wish (scripts, intermediate files, several
passes). The result must contain, in this order of dependency:

- requirements: every normative statement (shall, shall not, should, should not, may).
- objects: every thing the standard defines that can be checked: data elements,
  structures, messages, parameters, fixed values, behaviours. Give each its exact
  name as written in the standard (for example the data element identifier).
- coverage items: for each requirement or object, the distinct checks worth testing
  (valid and invalid sides, boundaries, conditions true and false).
- test cases: exactly one per coverage item.

## Output

Write one file, output/plan.json, with this structure. Field names and the listed
vocabularies are mandatory; identifiers are yours to choose but must be unique.

{
  "source": {"path": "input/iso_18013_5.pdf", "generated_at": "<ISO 8601>", "model": "<your model id>"},
  "requirements": [{
    "id": "R-0001", "clause_id": "8.3.2.1.2", "name": "<short name, may be empty>",
    "text": "<the requirement restated>",
    "modality": "shall | shall_not | should | should_not | may",
    "conditions": [], "applies_when": [], "source_quote": "<verbatim>"}],
  "objects": [{
    "id": "O-0001", "clause_id": "7.2.1", "name": "<exact name in the standard>",
    "kind": "field | structure | message | parameter | value | behaviour",
    "direction": "received | produced | internal",
    "presence": "mandatory | optional | conditional | unspecified",
    "condition": null, "type": null, "value_domain": null, "size": null,
    "relations": [], "applies_when": [], "source_quote": "<verbatim>", "origin": "prose"}],
  "coverage_items": [{
    "id": "CI-0001", "source_id": "<a requirement or object id>", "clause_id": "7.2.1",
    "check": "presence | absence | encoding_valid | encoding_invalid | value_valid |
              value_invalid | boundary_min | boundary_max | boundary_outside |
              consistency | condition_true | condition_false | nominal | negative |
              boundary | capability | inopportune | reference",
    "kind": "nominal | negative | boundary",
    "group": "capability | valid_behaviour | invalid_behaviour | inopportune_behaviour",
    "purpose": "<one sentence: what this item verifies>"}],
  "test_cases": [{
    "id": "TC-0001", "source_id": "<same as its coverage item>",
    "coverage_item_id": "CI-0001", "kind": "nominal | negative | boundary",
    "objective": "<one sentence>", "preconditions": [], "inputs": [],
    "steps": ["<at least one concrete step>"],
    "expected_result": "<observable outcome>", "pass_criteria": "<how to decide pass or fail>"}],
  "traceability": [{"source_id": "R-0001", "coverage_item_ids": ["CI-0001"], "test_case_ids": ["TC-0001"]}],
  "gaps": [{"source_id": "<id or null>", "clause_id": "9.1.2", "stage": "extract | model | generate",
            "reason": "<why>", "attempts": 1}]
}

`clause_id` is the clause number as printed in the PDF.

## Before you finish

Write and run a script (work/check.py) that loads output/plan.json and verifies:
valid JSON; all vocabularies respected; all identifiers unique; every `source_id`
and `coverage_item_id` resolves; every coverage item has exactly one test case or a
gap; every `source_quote` occurs in the text extracted from the PDF (whitespace
normalised). Fix what fails, or turn it into a gap.

Then write output/report.md with: the counts of requirements, objects, coverage items,
test cases and gaps; the list of clauses with nothing extracted and why; and the
choices you noted in work/notes.md.
```
