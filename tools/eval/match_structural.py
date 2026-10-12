"""Judge-free structural match of an official conformance suite against a generated test plan.

Each official test case is reduced by rule to a `(data_item, check_type)` pair. `check_type` is one of
a closed seven-value vocabulary of check families; `data_item` is the token the purpose text names as
the thing under check. A generated plan matches an official case when it carries a coverage item whose
source object is named by that data item and whose `check` belongs to the same family.

No model is involved, so the figure is reproducible and carries none of the self-preference bias of a
judge drawn from the generator's own model family. The rules are over ordinary English and over the
labelled-field structure of a test-purpose record, so they apply to any conformance suite written in
the ISO/IEC 9646-2 style.

Both inferences deliberately read the purpose and scenario text with parenthesised spans removed: a
parenthetical is an aside ("(if present)", "(Tag 'A1')", "(e.g. ...)") and taking it as the subject of
the check mis-classified a large minority of cases in a hand audit.

Usage: match_structural.py <plan.json> <ground_truth.json> [out.json]
"""
import collections
import json
import pathlib
import random
import re
import sys

from tpg.models import KIND_WORDS

# Nouns that label a thing a standard can place under test. Reused from the object-kind vocabulary so
# the two halves of the tool agree on what counts as a nameable artefact.
_NOUNS = "|".join(sorted((re.escape(w) for w in KIND_WORDS), key=len, reverse=True))
_IDENT = r"[A-Za-z][A-Za-z0-9_]*"
_PARENS = re.compile(r"\([^()]*\)")
# straight, curly and backtick quoting, plus a code-styled token in angle brackets
_QUOTED = re.compile(r"[\"'\u2018\u2019\u201c\u201d\u00ab\u00bb`<]\s*(" + _IDENT + r")\s*"
                     r"[\"'\u2018\u2019\u201c\u201d\u00ab\u00bb`>]")
_DATA_X = re.compile(r"\bdata (?:element|item|object|field)s?\s+(" + _IDENT + r")")
_X_NOUN = re.compile(r"\b(?:the|each|a|an|its)\s+(" + _IDENT + r")\s+(?:data\s+)?(?:" + _NOUNS + r")s?\b",
                     re.IGNORECASE)
# A capture that is an ordinary English function word or a bare participial adjective names nothing:
# "data element in each ..." has the preposition where the name would be, and "each DrivingPrivilege
# data item present" has the adjective there. Rejecting these and taking the next match is what keeps
# the extraction honest. "data" itself is a label, never a name.
STOPWORDS = frozenset("""a an the this that these those it its all any each both other another same
such following first last no not and or if when where which while of in on at by to for with from as
is are be been was were has have had does do did may shall should must can could will would
data test case tests cases above below respectively
present absent correct incorrect valid invalid specified unspecified indicated defined listed
requested required supported received sent selected expected generated used applicable""".split())

# The check-type ladder, most specific rung first. The order matters: a size bound stated over a value
# ("the value shall be at most 32 bytes") is a size check, a value stated relative to another value
# ("different from the value of ...") is a consistency check, and "the presence of X" is a more specific
# claim than the word "value", so all three outrank the plain value rung. `behaviour` is last because it
# is the catch-all for a purpose that states an observable reaction rather than a property of a datum.
# ponytail: the keyword sets were tuned by reading about thirty purposes of one suite, so the rungs are
# calibrated English, not measured English. Re-read a sample on any new suite before trusting a rung.
LADDER = [
    ("reuse", r"\bre-?use[ds]?\b|\breused\b|\buniqu|\bephemeral\b|\bonly once\b|\bfresh\b|\breplay"),
    ("size", r"\blength\b|\bsize[ds]?\b|\bbyte\b|\bbytes\b|\bmaximum\b|\bminimum\b|\bat most\b|\bat least\b"
             r"|\bno (?:longer|more|less) than\b|\bexceed|\bupper bound\b|\blower bound\b|\bout of range\b"),
    ("consistency", r"\bsame (?:as|value|values)\b|\bmatch(?:es|ing|ed)?\b|\bidentical\b|\bconsistent\b"
                    r"|\bcorrespond|\bdiffer(?:s|ent)? from\b|\bequal to\b|\bderived from\b|\bagree[sd]? with\b"),
    ("encoding", r"\bencod|\bwell.?formed\b|\bsyntax\b|\bcanonical|\bformat(?:ted|ting)?\b|\bserial"
                 r"|\bparse[ds]?\b|\bparsing\b|\bdecod|\bmalformed\b"),
    ("presence", r"\bpresence\b|\bpresent\b|\babsen|\bomit|\bmissing\b|\bnot included\b"
                 r"|\bnumber (?:and|of)\b|\bmandatory\b|\boptional\b"),
    ("value_domain", r"\bvalues?\b|\ballowed\b|\bpermitted\b|\bvalid\b|\bset to\b|\bone of\b|\bcontent of\b"),
    ("behaviour", r"\bindicat|\bsend[s]?\b|\bsent\b|\brespond|\breject|\baccept|\breturn|\bwait"
                  r"|\bperform|\bhandle|\bcontinue|\babort|\bterminate|\bretriev|\bestablish|\bprocess"
                  r"|\bact(?:s|ing)? as\b|\bserve[sd]?\b|\bbehaviour\b|\bbehavior\b"),
]
LADDER = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in LADDER]
CHECK_TYPES = [name for name, _ in LADDER]

# Which `check` values of a generated coverage item belong to each official check family. `reuse` has
# no rung of its own in the generator's vocabulary; a uniqueness or freshness obligation is a relation
# between two instances, which is what `consistency` covers, so it maps there and the mapping is a
# known weakness rather than a claim. The unspecific `nominal`/`negative`/`boundary` checks come from
# the requirement ladder, which states prose obligations, so they sit in `behaviour`.
FAMILIES = {
    "presence": {"presence", "absence", "capability"},
    "encoding": {"encoding_valid", "encoding_invalid"},
    "value_domain": {"value_valid", "value_invalid"},
    "size": {"boundary_min", "boundary_max", "boundary_outside", "boundary"},
    "consistency": {"consistency", "reference"},
    "reuse": {"consistency"},
    "behaviour": {"nominal", "negative", "condition_true", "condition_false", "inopportune"},
}


def normalise(name: str) -> str:
    """A name reduced to its letters and digits, so spacing, case and punctuation cannot decide a match."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _clean(*parts: object) -> str:
    """Text the rules read: the given fields joined, with parenthesised asides removed."""
    text = " ".join(str(p or "") for p in parts)
    for _ in range(3):   # nested parentheses, innermost first
        text, n = _PARENS.subn(" ", text)
        if not n:
            break
    return " ".join(text.split())


def _subject_texts(case: dict) -> tuple[str, str]:
    """The purpose alone, then the purpose with the scenario. The rules read the purpose first because a
    scenario recites setup steps whose incidental wording outranks the actual check when both are one
    blob; the scenario is the fallback for a purpose too terse to classify."""
    return _clean(case.get("purpose")), _clean(case.get("purpose"), case.get("scenario"))


def _first_capture(pattern: re.Pattern, text: str) -> str | None:
    for m in pattern.finditer(text):
        if m.group(1).lower() not in STOPWORDS:
            return m.group(1)
    return None


def infer_data_item(text: str) -> str | None:
    """The token the text names as the thing under check: the first quoted or code-styled token, else the
    first `data element X` capture, else the first `the X <artefact noun>` capture, else None."""
    for pattern in (_QUOTED, _DATA_X, _X_NOUN):
        hit = _first_capture(pattern, text)
        if hit:
            return hit
    return None


def infer_check_type(text: str) -> str | None:
    """The first rung of the ladder whose keywords the text hits, or None when it hits none."""
    for name, pattern in LADDER:
        if pattern.search(text):
            return name
    return None


def annotate(case: dict) -> dict:
    """`check_type` and `data_item` for one official case, inferred by rule."""
    purpose, both = _subject_texts(case)
    return {"check_type": infer_check_type(purpose) or infer_check_type(both),
            "data_item": infer_data_item(purpose) or infer_data_item(both)}


def object_checks(plan: dict) -> dict[str, set[str]]:
    """Normalised source name -> the set of `check` values the plan's coverage items carry for it.

    Requirements carry a `name` too since Task 9, so a requirement-derived item is scorable whenever
    the extraction named what the requirement constrains. An unnamed source is skipped rather than
    bucketed under the empty string, which would merge every unnamed requirement into one key.
    """
    names = {
        s["id"]: normalise(s.get("name") or "")
        for s in list(plan.get("objects", [])) + list(plan.get("requirements", []))
    }
    index: dict[str, set[str]] = collections.defaultdict(set)
    for item in plan.get("coverage_items", []):
        name = names.get(item.get("source_id") or "")
        if name:
            index[name].add(item["check"])
    return index


def match(plan: dict, ground_truth: list[dict]) -> list[dict]:
    """One record per official case: its inferred pair and whether the plan structurally covers it."""
    index = object_checks(plan)
    out = []
    for case in ground_truth:
        rec = {"gt_id": case["id"], "appendix": case.get("appendix"),
               "clauses": case.get("clauses_18013_5") or [], **annotate(case)}
        family = FAMILIES.get(rec["check_type"] or "", set())
        checks = index.get(normalise(rec["data_item"]), set()) if rec["data_item"] else set()
        rec["object_found"] = bool(checks)
        rec["matched"] = bool(checks & family) if rec["check_type"] else False
        out.append(rec)
    return out


def report(records: list[dict]) -> None:
    """The matched/unmatched counts, the per-family breakdown and a sample of the inferred pairs."""
    usable = [r for r in records if r["data_item"] and r["check_type"]]
    matched = [r for r in usable if r["matched"]]
    print(f"official cases              {len(records)}")
    print(f"with an inferred check type {sum(1 for r in records if r['check_type'])}")
    print(f"with an inferred data item  {sum(1 for r in records if r['data_item'])}")
    print(f"with both (scorable)        {len(usable)}")
    print(f"matched                     {len(matched)} = {100 * len(matched) / max(len(usable), 1):.1f}% of scorable,"
          f" {100 * len(matched) / max(len(records), 1):.1f}% of all")
    print(f"unmatched                   {len(usable) - len(matched)}")
    near = [r for r in usable if r["object_found"] and not r["matched"]]
    print(f"  of which the object was extracted but no check of the family: {len(near)}")
    print(f"  of which the data item names no extracted object:             {len(usable) - len(matched) - len(near)}")
    print("\nper check family (matched / scorable / all cases inferred to that family):")
    for name in CHECK_TYPES:
        fam = [r for r in records if r["check_type"] == name]
        sc = [r for r in fam if r["data_item"]]
        hit = sum(1 for r in sc if r["matched"])
        print(f"  {name:13s} {hit:4d} / {len(sc):4d} / {len(fam):4d}"
              f"  {100 * hit / max(len(sc), 1):5.1f}%")


def sample(records: list[dict], n: int = 25, seed: int = 1) -> None:
    """Print inferred pairs for a sample of cases so a human can audit the inference."""
    rnd = random.Random(seed)
    print(f"\nsample of {n} inferred pairs (audit the inference here):")
    for r in rnd.sample(records, min(n, len(records))):
        print(f"  {r['gt_id']:34s} {str(r['check_type']):13s} {str(r['data_item'])[:28]:30s}"
              f" {'matched' if r['matched'] else ('object only' if r['object_found'] else '-')}")


def main(plan_path: str, gt_path: str, out_path: str | None = None) -> None:
    print("== structural match (no model)")
    plan_file, gt_file = pathlib.Path(plan_path), pathlib.Path(gt_path)
    if not plan_file.exists() or not gt_file.exists():
        for f in (plan_file, gt_file):
            if not f.exists():
                print(f"missing input: {f}")
        print("nothing to match")
        return
    plan = json.loads(plan_file.read_text())
    ground_truth = json.loads(gt_file.read_text())
    records = match(plan, ground_truth)
    report(records)
    sample(records)
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps(records, indent=1, ensure_ascii=False))
        print(f"\nwrote {out_path}")


def selftest() -> None:
    """The smallest check that fails if the inference rules break."""
    q = "\u201c"
    assert infer_data_item('the "documents" data item') == "documents"
    assert infer_data_item(q + "Size" + q + " field") == "Size"
    assert infer_data_item("the presence of data element in each thing") is None, "stopword must be rejected"
    assert infer_data_item("verify data element family_name") == "family_name"
    assert infer_data_item("the DeviceResponse structure is correct") == "DeviceResponse"
    assert infer_check_type("the value shall be at most 32 bytes") == "size"
    assert infer_check_type("the value differs from the value in the header") == "consistency"
    assert infer_check_type("the structure is a well-formed encoding") == "encoding"
    assert infer_check_type("verifies the presence of the field") == "presence"
    assert infer_check_type("the value of the field is correct") == "value_domain"
    assert infer_check_type("the reader sends a response") == "behaviour"
    assert infer_check_type("the key shall not be reused") == "reuse"
    assert infer_check_type("qwerty") is None
    # a parenthesised aside is never the subject of the check
    assert annotate({"purpose": "the value of the field (if present) is correct",
                     "scenario": ""})["check_type"] == "value_domain"
    assert annotate({"purpose": "the Subtype data element (Tag 'A1') is present",
                     "scenario": ""})["data_item"] == "Subtype", "the aside must not become the subject"
    assert normalise("Device Engagement!") == "deviceengagement"
    plan = {"objects": [{"id": "O1", "name": "docType"}],
            "coverage_items": [{"id": "C1", "source_id": "O1", "check": "value_valid"}]}
    gt = [{"id": "T1", "purpose": 'the "docType" value is correct', "scenario": ""},
          {"id": "T2", "purpose": 'the "docType" value is at most 3 bytes', "scenario": ""},
          {"id": "T3", "purpose": 'the "other" value is correct', "scenario": ""}]
    got = {r["gt_id"]: r["matched"] for r in match(plan, gt)}
    assert got == {"T1": True, "T2": False, "T3": False}, got
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--selftest"]:
        selftest()
    elif len(a) < 2:
        sys.exit(__doc__)
    else:
        main(a[0], a[1], a[2] if len(a) > 2 else None)
