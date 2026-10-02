#!/usr/bin/env bash
# Reproduce the evaluation end to end. Everything it writes lands in eval/, which is gitignored
# because the outputs quote the source documents.
#
#   tools/eval/run.sh <standard.pdf> <directory of test-specification PDFs> [model]
#
# Point OLLAMA_HOST at a remote server if the model does not run on this machine; the default is a
# local daemon. OLLAMA_TIMEOUT bounds each call and defaults to 120 seconds, which is short for a
# cold model load: the script warms the model first so the first real call is not the one that waits.
set -euo pipefail

if [ $# -lt 2 ]; then
  sed -n '2,12p' "$0" >&2
  exit 2
fi
standard=$1
appendices=$2
export TPG_EVAL_MODEL=${3:-gemma4:31b}
export OLLAMA_TIMEOUT=${OLLAMA_TIMEOUT:-600}
mkdir -p eval

echo "== model: $TPG_EVAL_MODEL at ${OLLAMA_HOST:-http://localhost:11434}, warming it"
uv run python -c "
from pydantic import BaseModel
from tpg.llm import OllamaLLM, load_dotenv
class Ping(BaseModel):
    answer: str
load_dotenv()
c = OllamaLLM(model='$TPG_EVAL_MODEL'); c.check()
print('warm:', c.complete('Reply with JSON only: {\"answer\": \"ok\"}', Ping).answer)
"

echo "== 1/4 ground truth from the test specification"
uv run python tools/eval/parse_appendices.py "$appendices" eval/ground_truth.json 2>&1 | tee eval/ground_truth.log

echo "== 2/4 generate the plan from the standard (the long step)"
start=$(date +%s)
uv run tpg generate "$standard" --model "$TPG_EVAL_MODEL" --out eval/plan.json 2>&1 | tee eval/plan.log || true
echo "plan wall time: $(( $(date +%s) - start ))s" | tee -a eval/plan.log

echo "== 3/4 coverage of the official test cases"
uv run python tools/eval/judge.py eval/plan.json eval/ground_truth.json eval/judge_results.json 2>&1 | tee eval/judge.log

echo "== 4/4 precision of a sample of generated cases"
uv run python tools/eval/precision.py eval/plan.json "$standard" eval/precision_results.json 60 2>&1 | tee eval/precision.log

echo
echo "================ paste everything below back ================"
uv run python tools/eval/summarise.py "$standard" | tee eval/summary.txt
