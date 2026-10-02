"""Throwaway evaluation: for each ground-truth 18013-6 test case, retrieve the closest generated test cases
by token overlap, then ask the model whether any of them verifies the same thing. Writes eval/judge_results.json."""
import collections, json, math, os, re, sys, time
from pydantic import BaseModel
from tpg.llm import OllamaLLM, load_dotenv

STOP = set("the a an of in to is are be and or for with that this by on as it its if not shall should may must "
           "verify verifies verified test case data value values present presence check checks correct valid".split())
def toks(s):
    return [t for t in re.findall(r"[a-z0-9_]+", s.lower()) if t not in STOP and len(t) > 1]

class Verdict(BaseModel):
    covered: bool
    best_candidate: str | None = None
    reason: str

PROMPT = """You compare an official conformance test case against candidate generated test cases.

OFFICIAL TEST CASE
Purpose: {purpose}
Test scenario: {scenario}
Expected results: {expected}

CANDIDATE GENERATED TEST CASES
{cands}

Question: does at least one candidate verify the SAME check as the official test case (same data item or behaviour, same condition, same expected outcome)? A candidate that only tests something related, broader, or a different property does not count.
Reply with JSON only: {{"covered": true|false, "best_candidate": "<candidate id or null>", "reason": "<one sentence>"}}"""

def main(plan_path, gt_path, out_path, model=None, limit=None, k=5):
    load_dotenv()
    llm = OllamaLLM(model=model or os.environ.get("TPG_EVAL_MODEL", "gemma4:31b")); llm.check()
    plan = json.load(open(plan_path)); gt = json.load(open(gt_path))
    reqs = {r["id"]: r for r in plan["requirements"]}
    for o in plan.get("objects", []):
        reqs[o["id"]] = {"text": " ".join(f"{k}: {v}" for k, v in o.items() if k in ("name", "kind", "presence", "type", "value_domain", "size", "relations") and v)}
    src = lambda t: t.get("source_id") or t["requirement_id"]
    gen = plan["test_cases"]
    docs = [(t, collections.Counter(toks(" ".join([t["objective"], t["expected_result"], t["pass_criteria"], " ".join(t["steps"]), reqs[src(t)]["text"]])))) for t in gen]
    df = collections.Counter(); [df.update(set(c)) for _, c in docs]
    N = len(docs)
    def score(q, c):
        return sum(q[w] * c[w] * math.log(1 + N / (1 + df[w])) for w in q if w in c)
    gt = [g for g in gt if g["clauses_18013_5"]]
    if limit: gt = gt[:limit]
    results = []; t0 = time.time()
    for n, g in enumerate(gt, 1):
        q = collections.Counter(toks(" ".join([g["purpose"], g["scenario"], g["expected"]])))
        top = sorted(docs, key=lambda d: -score(q, d[1]))[:k]
        cands = "\n".join(f"- {t['id']} [{t['kind']}] (from: {reqs[src(t)]['text'][:200]})\n  objective: {t['objective']}\n  steps: {' / '.join(t['steps'])[:300]}\n  expected: {t['expected_result'][:200]}" for t, _ in top)
        prompt = PROMPT.format(purpose=g["purpose"], scenario=g["scenario"][:800], expected=g["expected"][:600], cands=cands)
        try:
            v = llm.complete(prompt, Verdict)
            results.append({"gt_id": g["id"], "appendix": g["appendix"], "clauses": g["clauses_18013_5"], "covered": v.covered,
                            "best": v.best_candidate, "reason": v.reason, "candidates": [t["id"] for t, _ in top]})
        except Exception as e:
            results.append({"gt_id": g["id"], "appendix": g["appendix"], "clauses": g["clauses_18013_5"], "covered": None, "error": str(e)[:200]})
        if n % 25 == 0:
            cov = sum(1 for r in results if r.get("covered")); print(f"{n}/{len(gt)} covered so far {cov} ({time.time()-t0:.0f}s)", file=sys.stderr, flush=True)
            json.dump(results, open(out_path, "w"), indent=1)
    json.dump(results, open(out_path, "w"), indent=1)
    cov = sum(1 for r in results if r.get("covered")); err = sum(1 for r in results if r.get("covered") is None)
    print(f"done: {cov}/{len(results)} covered, {err} judge errors, {time.time()-t0:.0f}s")

if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], limit=int(a[3]) if len(a) > 3 else None)
