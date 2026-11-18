# Test plan generation: three methods, one article

This repository holds three independent projects that answer the same research question: how to
generate a conformance test plan from the text of a technical standard (ISO/IEC 18013-5 is the
running example). They are compared in one article.

| Directory | Method | Origin |
|---|---|---|
| `method1-rag/` | Agentic RAG pipeline: axes A (extract and index), B (agents generate), C (audit) | the former `TestPlanGeneration` repository |
| `method2-deterministic/` | Deterministic pipeline `tpg`: fixed stages, the LLM only extracts and writes | the former `TestPlanGenerationTest` repository |
| `method3-harness/` | The same task given to an industrial agentic harness (Claude Code) | not started |
| `docs/article/` | The article, common to the three methods | |

## Treat each method directory as its own repository

The three methods share a goal and an article, nothing else.

- Each method directory has its own code, tests, dependencies, virtual environment, `.gitignore`,
  `README.md` and docs. Work inside one as if it were the root of a separate repository: `cd` into
  it before running anything, and read its own README first.
- Do not share code between methods and do not import across them. A change to one method must not
  touch another.
- Process documents stay with their method: `docs/superpowers/` (specs and plans), `.superpowers/`,
  evaluation reports and research notes live inside the method directory they belong to. Create new
  ones there, never at the root.
- Dependencies differ: `method1-rag/requirements.txt` (pip, LangChain, FAISS, Ollama) and
  `method2-deterministic/pyproject.toml` with `uv.lock` (uv). There is no root environment.

## What is common

- `docs/article/` is the only shared content. `experiments.tex` is the experiments and results
  section; `outline.md` is the working outline. When a method produces a new result, the figure
  goes into its own evaluation docs first and is then reported in `docs/article/`.
- The article compares the three methods on the same input and the same ground truth (the official
  test cases of ISO/IEC TS 18013-6), so a metric reported for one method should be reported the
  same way for the others.
- Git history is shared: the two former repositories were merged with their full histories.

## Data that is not in git

Standards and anything derived from their text are ignored by git and exist only locally:
`method1-rag/data/`, `method2-deterministic/eval/` and
`method2-deterministic/tests/fixtures/iso_18013_5.pdf`. Never commit them.
