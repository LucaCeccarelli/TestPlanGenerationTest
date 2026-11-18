# Test plan generation from technical standards

Three methods for generating a conformance test plan from the text of a standard, compared in one
article. Each method is a self-contained project with its own README, dependencies and docs.

| Directory | Method |
|---|---|
| [`method1-rag/`](method1-rag/README.md) | Agentic RAG pipeline (extract and index, generate with agents, audit) |
| [`method2-deterministic/`](method2-deterministic/README.md) | Deterministic pipeline `tpg` with an explicit test model |
| [`method3-harness/`](method3-harness/README.md) | The same task given to an industrial agentic harness |
| [`docs/article/`](docs/article/) | The article, common to the three methods |
