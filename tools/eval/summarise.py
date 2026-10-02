"""Print the numbers an evaluation run is judged on, small enough to paste into a conversation.

Usage: summarise.py [standard path]   (reads eval/plan.json, judge_results.json, precision_results.json)
"""
import collections
import json
import pathlib
import re
import subprocess
import sys

EVAL = pathlib.Path("eval")


def load(name):
    p = EVAL / name
    return json.loads(p.read_text()) if p.exists() else None


def main() -> None:
    standard = sys.argv[1] if len(sys.argv) > 1 else "(not given)"
    plan = load("plan.json")
    print("== environment")
    try:
        print("ollama:", subprocess.run(["ollama", "--version"], capture_output=True, text=True).stdout.strip() or "n/a")
    except OSError:
        print("ollama: not on PATH")
    print("standard:", standard)
    if plan:
        print("model:", plan["source"]["model"], "| generated_at:", plan["source"]["generated_at"])
        print("\n== plan")
        for key in ("requirements", "objects", "coverage_items", "test_cases", "gaps"):
            print(f"{key:15s} {len(plan[key])}")
        print("gaps by stage:", dict(collections.Counter(g["stage"] for g in plan["gaps"])))
        items = {i["id"]: i for i in plan["coverage_items"]}
        covered = {t["coverage_item_id"] for t in plan["test_cases"]}
        print("coverage items with a test case:", len(covered), "of", len(items))
        print("item kinds:", dict(collections.Counter(i["kind"] for i in plan["coverage_items"])))
        print("checks:", collections.Counter(i["check"] for i in plan["coverage_items"]).most_common())
        reasons = collections.Counter()
        for g in plan["gaps"]:
            r = g["reason"]
            reasons[("LLM call failed" if "LLM call failed" in r else
                     "reply not parseable" if ("schema" in r or "JSON" in r) else
                     "source_quote not verbatim" if "verbatim" in r else
                     "modality" if "modality" in r else
                     "vocabulary" if "is not one of" in r else
                     "negative case wording" if "negative case must expect" in r else
                     r.split(":")[-1].strip()[:40])] += 1
        if reasons:
            print("gap reasons:", reasons.most_common(8))
    else:
        print("\n== plan: eval/plan.json missing")

    judge = load("judge_results.json")
    if judge:
        done = [r for r in judge if r.get("covered") is not None]
        cov = [r for r in done if r["covered"]]
        print("\n== coverage of the official suite")
        print(f"judged {len(done)} of {len(judge)} | covered {len(cov)} = {100 * len(cov) / max(len(done), 1):.1f}%")
        by_app = collections.defaultdict(lambda: [0, 0])
        for r in done:
            by_app[r["appendix"]][0] += r["covered"]
            by_app[r["appendix"]][1] += 1
        print("by document:", {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_app.items())})
        by_cl = collections.defaultdict(lambda: [0, 0])
        for r in done:
            for c in r["clauses"]:
                by_cl[c][0] += r["covered"]
                by_cl[c][1] += 1
        print("most-tested clauses (>=10 official tests):")
        for c, v in sorted(by_cl.items(), key=lambda kv: -kv[1][1])[:12]:
            if v[1] >= 10:
                print(f"  {c:14s} {v[0]:3d}/{v[1]:3d} {100 * v[0] / v[1]:5.1f}%")
    else:
        print("\n== coverage: eval/judge_results.json missing")

    prec = load("precision_results.json")
    if prec:
        ok = [x for x in prec if "error" not in x]
        print("\n== precision of generated cases (sample)")
        for key in ("grounded", "actionable", "expected_correct"):
            print(f"{key:17s} {sum(1 for x in ok if x.get(key))}/{len(ok)}")
        kinds = collections.Counter(x["kind"] for x in ok)
        good = collections.Counter(x["kind"] for x in ok if x.get("grounded") and x.get("expected_correct"))
        print("grounded and correct by kind:", {k: f"{good[k]}/{kinds[k]}" for k in kinds})
        print("\nsample failures:")
        for x in ok:
            if not (x.get("grounded") and x.get("actionable") and x.get("expected_correct")):
                print(f"  {x['tc_id']} [{x['kind']}] {x.get('reason', '')[:110]}")
    else:
        print("\n== precision: eval/precision_results.json missing")

    log = EVAL / "plan.log"
    if log.exists():
        wall = [l for l in log.read_text().splitlines() if l.startswith("plan wall time")]
        print("\n==", wall[0] if wall else "plan wall time: not recorded")


if __name__ == "__main__":
    main()
