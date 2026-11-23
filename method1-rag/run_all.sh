#!/usr/bin/env bash
# Run the three axes in order: A (extract + index), B (generate), C (audit).
#
#   ./run_all.sh                                  # ISO/IEC 18013-5, the default
#   ./run_all.sh data/input/RFC8949.pdf "RFC 8949"
#   SKIP_PAGES="1 2 3" ./run_all.sh other.pdf "Other norm"
#
# Long run (hours): start it detached and come back later:
#   screen -dmS tpg ./run_all.sh        then: tail -f run_all.log
#
# Stops at the first axis that fails. Everything is logged to run_all.log.
set -euo pipefail
cd "$(dirname "$0")"

pdf=${1:-data/input/iso_18013_5.pdf}
norm=${2:-ISO/IEC 18013-5}
skip_pages=${SKIP_PAGES-1 2 3 4 5 6 7 8}   # cover and table of contents of the ISO PDF

stem=$(basename "$pdf" .pdf)
chunks=data/output/chunks/${stem}_chunks.jsonl
index=data/output/index/${stem}_faiss_index
plan=data/output/test_plans/${stem}_test_plan.json

exec > >(tee -a run_all.log) 2>&1
echo "== $(date '+%F %T') run_all: $pdf ($norm)"

[ -f .venv/bin/activate ] && source .venv/bin/activate
[ -f "$pdf" ] || { echo "PDF not found: $pdf"; exit 1; }
# faiss-cpu 1.14.2 dies with an illegal instruction on CPUs without AVX; 1.13.2 works there.
python -c "import faiss" 2>/dev/null || { echo "faiss does not load: pip install faiss-cpu==1.13.2"; exit 1; }
curl -s -m 5 "${OLLAMA_HOST:-http://127.0.0.1:11434}/api/version" >/dev/null \
  || { echo "Ollama is not reachable: sudo systemctl start ollama"; exit 1; }
mkdir -p data/output/chunks data/output/index data/output/test_plans

echo "== $(date '+%F %T') Axis A"
# shellcheck disable=SC2086  # skip_pages is a deliberate word list
python scripts/run_axis_a.py --pdf "$pdf" --norm "$norm" \
  --output-chunks "$chunks" --output-index "$index" ${skip_pages:+--skip-pages $skip_pages}

echo "== $(date '+%F %T') Axis B"
python scripts/run_axis_b.py --chunks "$chunks" --index "$index" --norm "$norm" --output "$plan"

echo "== $(date '+%F %T') Axis C"
python scripts/run_axis_c.py --plan "$plan" --chunks "$chunks" --index "$index"

echo "== $(date '+%F %T') done: $plan and ${plan%.json}_audit_report.json"
