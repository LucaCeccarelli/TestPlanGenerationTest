"""Print the numbers an evaluation run is judged on, small enough to paste into a conversation.

Three things make this more than a reformatting of the raw results.

*Three denominators.* The official suite's size is not its scored size. A case that cites no clause of
the standard under test is grounded in some other specification the tool never reads, and a case whose
cited clause id does not occur among the input document's clause ids is testing a requirement that is
not in the input at all -- a different edition, or a clause the ingest never segmented. All three
counts are printed and the score is stated against the third, which is the only honest in-edition test
available without a semantic crosswalk between editions.

*ICS coverage is the headline.* The share of mandatory and optional Implementation Conformance
Statement items that got a coverage item, and the share whose items all produced a test case, need no
official suite at all, so they are the figures that transfer to a standard that has none.

*Macro beside micro.* A per-case rate lets the single most-cited clause and the largest test family
dominate. The mean of the per-clause rates and the mean of the per-family rates do not.

Usage: summarise.py [standard path]   (reads eval/plan.json and the other eval/ artefacts)
"""
import collections
import json
import pathlib
import re
import subprocess
import sys

from match_structural import CHECK_TYPES

EVAL = pathlib.Path("eval")
# A suite numbers the cases of one family in sequence ("mDL_MS_DE_Gen_05"), so dropping the trailing
# serial recovers the family. This is the suite's own grouping, not one we impose.
SERIAL = re.compile(r"[_-]?\d+$")


def load(name):
    p = EVAL / name
    return json.loads(p.read_text()) if p.exists() else None


def family(case_id: str) -> str:
    return SERIAL.sub("", case_id) or case_id


def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def input_clause_ids(standard: str) -> set[str] | None:
    """The clause ids of the input standard, or None when the document is not available. Ingesting the
    document is the only authority on what is in the input: the plan lists only the clauses that
    survived extraction."""
    if not standard or not pathlib.Path(standard).exists():
        print(f"input standard not readable at {standard!r}: the in-edition denominator is not computable")
        return None
    try:
        from tpg.ingest import ingest
        return {c.id for c in ingest(standard)}
    except Exception as exc:                                     # noqa: BLE001 - a research harness
        print(f"ingest of the input standard failed ({type(exc).__name__}: {exc});"
              " the in-edition denominator is not computable")
        return None


def plan_section(plan) -> None:
    print("\n== plan")
    for key in ("requirements", "objects", "ics", "coverage_items", "test_cases", "gaps"):
        print(f"{key:15s} {len(plan.get(key, []))}")
    items = plan.get("coverage_items", [])
    print("gaps by stage:", dict(collections.Counter(g["stage"] for g in plan.get("gaps", []))))
    covered = {t["coverage_item_id"] for t in plan["test_cases"]}
    print("coverage items with a test case:", len(covered), "of", len(items))
    print("item kinds:", dict(collections.Counter(i["kind"] for i in items)))
    print("item groups:", dict(collections.Counter(i.get("group", "(not recorded)") for i in items)))
    print("object origins:", dict(collections.Counter(o.get("origin", "(not recorded)")
                                                      for o in plan.get("objects", []))))
    print("checks:", collections.Counter(i["check"] for i in items).most_common())
    reasons = collections.Counter()
    for g in plan.get("gaps", []):
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


def ics_section(plan) -> None:
    """The suite-independent headline: how much of the conformance statement the plan actually tests."""
    print("\n== ICS coverage (the suite-independent headline)")
    ics = plan.get("ics") or []
    if not ics:
        print("the plan carries no ICS proforma, so this metric is not computable for it")
        return
    by_source = collections.defaultdict(list)
    for item in plan.get("coverage_items", []):
        by_source[item["source_id"]].append(item)
    tested = {t["coverage_item_id"] for t in plan["test_cases"]}
    rows = []
    for entry in ics:
        items = by_source.get(entry["source_id"], [])
        rows.append((entry, bool(items), bool(items) and all(i["id"] in tested for i in items)))
    print("ICS items by status:", dict(collections.Counter(e["status"] for e in ics)))
    for status in ("mandatory and optional", "mandatory", "optional"):
        want = ("mandatory", "optional") if status == "mandatory and optional" else (status,)
        scope = [r for r in rows if r[0]["status"] in want]
        if not scope:
            continue
        with_item = sum(1 for r in scope if r[1])
        all_tested = sum(1 for r in scope if r[2])
        print(f"{status:24s} {len(scope):4d} items |"
              f" with a coverage item {with_item:4d} = {100 * with_item / len(scope):5.1f}% |"
              f" every item tested {all_tested:4d} = {100 * all_tested / len(scope):5.1f}%")
    naked = [e["id"] for e, has, _ in rows if not has and e["status"] in ("mandatory", "optional")]
    if naked:
        print("untested mandatory/optional ICS items (first 10):", naked[:10])


def denominator_section(ground_truth, clause_ids) -> tuple[list, list, list]:
    """The three denominators. Returns the three case lists, widest first."""
    print("\n== denominators of the official suite")
    cited = [g for g in ground_truth if g.get("clauses_18013_5")]
    if clause_ids is None:
        in_edition = []
    else:
        in_edition = [g for g in cited if any(c in clause_ids for c in g["clauses_18013_5"])]
    print(f"all official cases                                  {len(ground_truth)}")
    print(f"citing a clause of the standard under test          {len(cited)}"
          f"  ({100 * len(cited) / max(len(ground_truth), 1):.1f}%)")
    if clause_ids is None:
        print("cited id present among the input's clause ids       not computable")
    else:
        strict = sum(1 for g in cited if all(c in clause_ids for c in g["clauses_18013_5"]))
        print(f"cited id present among the input's clause ids       {len(in_edition)}"
              f"  ({100 * len(in_edition) / max(len(ground_truth), 1):.1f}% of all,"
              f" {100 * len(in_edition) / max(len(cited), 1):.1f}% of cited)   <- scored on this")
        print(f"  of those, every cited id present                  {strict}")
        print(f"  input clause ids ingested                         {len(clause_ids)}")
        absent = sorted({c for g in cited for c in g["clauses_18013_5"] if c not in clause_ids})
        print(f"  distinct cited ids absent from the input          {len(absent)}: {absent[:12]}")
        print("  an absent id is either a clause of another edition or one the ingest never segmented;"
              " separating the two needs a human crosswalk")
    return ground_truth, cited, in_edition


def verdicts(judge, matches) -> tuple[dict, dict]:
    """gt_id -> covered, for the judge (errors dropped) and for the structural matcher."""
    j = {r["gt_id"]: bool(r["covered"]) for r in (judge or []) if r.get("covered") is not None}
    m = {r["gt_id"]: bool(r["matched"]) for r in (matches or [])
         if r.get("data_item") and r.get("check_type")}
    return j, m


def rates(cases, covered) -> str:
    """Micro rate, macro over cited clauses and macro over official test families, for one scope."""
    rows = [(g, covered[g["id"]]) for g in cases if g["id"] in covered]
    if not rows:
        return "        no verdicts in scope"
    micro = mean(float(c) for _, c in rows)
    by_clause = collections.defaultdict(list)
    by_family = collections.defaultdict(list)
    for g, c in rows:
        for clause in g.get("clauses_18013_5") or ["(none cited)"]:
            by_clause[clause].append(float(c))
        by_family[family(g["id"])].append(float(c))
    return (f"        scored {len(rows):4d} | micro {100 * micro:5.1f}%"
            f" | macro over {len(by_clause):3d} clauses {100 * mean(mean(v) for v in by_clause.values()):5.1f}%"
            f" | macro over {len(by_family):3d} families {100 * mean(mean(v) for v in by_family.values()):5.1f}%")


def coverage_section(scopes, judge, matches) -> None:
    print("\n== coverage of the official suite: structural matcher beside the LLM judge")
    j, m = verdicts(judge, matches)
    if not j:
        print("no LLM judge results (eval/judge_results.json missing or every verdict errored)")
    if not m:
        print("no structural match results (eval/match_results.json missing)")
    for label, cases in scopes:
        print(f"\n  {label}  (n={len(cases)})")
        print("    structural (no model)")
        print(rates(cases, m))
        print("    LLM judge (same model family as the generator: a self-preference risk)")
        print(rates(cases, j))
    if j and m:
        both = [i for i in j if i in m]
        agree = sum(1 for i in both if j[i] == m[i])
        print(f"\n  the two agree on {agree} of {len(both)} cases both scored"
              f" ({100 * agree / max(len(both), 1):.1f}%);"
              f" judge only {sum(1 for i in both if j[i] and not m[i])},"
              f" structural only {sum(1 for i in both if m[i] and not j[i])}")
    if m and matches:
        print("\n  structural match by inferred check family (matched / scorable):")
        for name in CHECK_TYPES:
            fam = [r for r in matches if r.get("check_type") == name and r.get("data_item")]
            print(f"    {name:13s} {sum(1 for r in fam if r['matched']):4d} / {len(fam):4d}")
        unscorable = sum(1 for r in matches if not (r.get("data_item") and r.get("check_type")))
        print(f"    no inferred pair, so unscorable structurally: {unscorable}")


def precision_section(prec) -> None:
    print("\n== precision of generated cases (sample, LLM judge)")
    if not prec:
        print("eval/precision_results.json missing")
        return
    ok = [x for x in prec if "error" not in x]
    for key in ("grounded", "actionable", "expected_correct"):
        print(f"{key:17s} {sum(1 for x in ok if x.get(key))}/{len(ok)}")
    kinds = collections.Counter(x["kind"] for x in ok)
    good = collections.Counter(x["kind"] for x in ok if x.get("grounded") and x.get("expected_correct"))
    print("grounded and correct by kind:", {k: f"{good[k]}/{kinds[k]}" for k in kinds})
    print("\nsample failures:")
    for x in ok:
        if not (x.get("grounded") and x.get("actionable") and x.get("expected_correct")):
            print(f"  {x['tc_id']} [{x['kind']}] {x.get('reason', '')[:110]}")


def main() -> None:
    standard = sys.argv[1] if len(sys.argv) > 1 else ""
    plan = load("plan.json")
    print("== environment")
    try:
        print("ollama:", subprocess.run(["ollama", "--version"], capture_output=True, text=True).stdout.strip() or "n/a")
    except OSError:
        print("ollama: not on PATH")
    print("standard:", standard or "(not given)")
    if plan:
        print("model:", plan["source"]["model"], "| generated_at:", plan["source"]["generated_at"])
        plan_section(plan)
        ics_section(plan)
    else:
        print("\n== plan: eval/plan.json missing")
        print("\n== ICS coverage: eval/plan.json missing")

    ground_truth = load("ground_truth.json")
    judge = load("judge_results.json")
    matches = load("match_results.json")
    if ground_truth:
        clause_ids = input_clause_ids(standard)
        scopes = list(zip(("all official cases", "citing a clause of the standard under test",
                           "in-edition: cited id present in the input (the scored denominator)"),
                          denominator_section(ground_truth, clause_ids)))
        coverage_section([(l, c) for l, c in scopes if c], judge, matches)
    else:
        print("\n== denominators: eval/ground_truth.json missing")
        print("\n== coverage: eval/ground_truth.json missing, so no denominator can be stated")

    precision_section(load("precision_results.json"))

    log = EVAL / "plan.log"
    if log.exists():
        wall = [l for l in log.read_text().splitlines() if l.startswith("plan wall time")]
        print("\n==", wall[0] if wall else "plan wall time: not recorded")


if __name__ == "__main__":
    main()
