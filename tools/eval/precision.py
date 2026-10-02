"""Throwaway evaluation: sample generated test cases and ask the model whether each is grounded in its
requirement, actionable, and has a correct expected result. Writes eval/precision_results.json."""
import json, os, random, sys, time
from pydantic import BaseModel
from tpg.llm import OllamaLLM, load_dotenv
from tpg.ingest import ingest

class Verdict(BaseModel):
    grounded: bool
    actionable: bool
    expected_correct: bool
    reason: str

PROMPT = """You audit one generated conformance test case against the standard's text.

CLAUSE {clause_id} (excerpt around the requirement):
\"\"\"{context}\"\"\"

REQUIREMENT {req_id} (modality {modality}): {req_text}
source quote: "{quote}"

GENERATED TEST CASE {tc_id} [{kind}]
objective: {objective}
preconditions: {pre}
inputs: {inputs}
steps: {steps}
expected result: {expected}
pass criteria: {pass_criteria}

Judge three things:
- grounded: the test case checks the obligation stated in the requirement (for a negative case: checks the reaction when the obligation's condition is violated or absent), not something else or something invented.
- actionable: a test engineer with the standard could execute the steps and observe the expected result without guessing what is meant.
- expected_correct: the expected result is what the clause actually requires (for a negative case: the correct rejection/error behaviour), with no contradiction of the clause text.
Reply with JSON only: {{"grounded": true|false, "actionable": true|false, "expected_correct": true|false, "reason": "<one sentence>"}}"""

def main(plan_path, std_path, out_path, n=60, model=None, seed=1):
    load_dotenv(); llm = OllamaLLM(model=model or os.environ.get("TPG_EVAL_MODEL", "gemma4:31b")); llm.check()
    plan = json.load(open(plan_path)); reqs = {r["id"]: r for r in plan["requirements"]}
    for o in plan.get("objects", []):
        reqs[o["id"]] = {"id": o["id"], "clause_id": o["clause_id"], "modality": "object", "source_quote": o["source_quote"],
                         "text": "object " + json.dumps({k: v for k, v in o.items() if k in ("name", "kind", "direction", "presence", "condition", "type", "value_domain", "size", "relations") and v}, ensure_ascii=False)}
    src = lambda t: t.get("source_id") or t["requirement_id"]
    clauses = {c.id: c for c in ingest(std_path)}
    random.seed(seed); sample = random.sample(plan["test_cases"], min(n, len(plan["test_cases"])))
    results = []; t0 = time.time()
    for i, t in enumerate(sample, 1):
        r = reqs[src(t)]; c = clauses.get(r["clause_id"])
        text = c.text if c else ""
        pos = text.lower().find(r["source_quote"].lower()[:40]); pos = max(pos, 0)
        ctx = text[max(0, pos-700): pos+900]
        prompt = PROMPT.format(clause_id=r["clause_id"], context=ctx, req_id=r["id"], modality=r["modality"], req_text=r["text"],
                               quote=r["source_quote"][:300], tc_id=t["id"], kind=t["kind"], objective=t["objective"],
                               pre="; ".join(t["preconditions"]), inputs="; ".join(t["inputs"]), steps=" / ".join(t["steps"]),
                               expected=t["expected_result"], pass_criteria=t["pass_criteria"])
        try:
            v = llm.complete(prompt, Verdict)
            results.append({"tc_id": t["id"], "kind": t["kind"], "clause": r["clause_id"], **v.model_dump()})
        except Exception as e:
            results.append({"tc_id": t["id"], "kind": t["kind"], "clause": r["clause_id"], "error": str(e)[:200]})
        if i % 20 == 0: print(f"{i}/{len(sample)} ({time.time()-t0:.0f}s)", file=sys.stderr, flush=True)
    json.dump(results, open(out_path, "w"), indent=1)
    ok = [x for x in results if "error" not in x]
    for key in ("grounded", "actionable", "expected_correct"):
        print(f"{key}: {sum(1 for x in ok if x[key])}/{len(ok)}")
    print("by kind:", {k: f"{sum(1 for x in ok if x['kind']==k and x['grounded'] and x['expected_correct'])}/{sum(1 for x in ok if x['kind']==k)}" for k in ("nominal","negative","boundary")})

if __name__ == "__main__":
    a = sys.argv[1:]; main(a[0], a[1], a[2], n=int(a[3]) if len(a) > 3 else 60)
