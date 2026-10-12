"""ingest -> grammar -> extract -> model -> ICS -> derive -> generate -> plan. One `log` line per stage
with its counts, including the ICS total and the ICS coverage that is the headline metric (D21, D27).

Given `out`, the run also persists as it goes, because the run it is built for takes hours: before the
first generation call `<out>.partial.json` holds the whole plan but its test cases, and during
generation `<out>.cases.jsonl` gains one record per case and per gap as each source is answered.
Generation is the only expensive stage -- some 1600 model calls against under a minute for ingest,
grammar, ICS and derive together -- so it is the one that must not be paid for twice. The final plan
is unchanged and is written by the caller, which drops both sidecars once it is on disk."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from tpg.derive import derive
from tpg.emit import build_plan, write_plan
from tpg.extract import extract
from tpg.grammar import harvest
from tpg.ics import build_ics
from tpg.generate import generate
from tpg.ingest import ingest
from tpg.model import assemble, extract_objects
from tpg.models import CoverageItem, Gap, ICSItem, Source, TestCase, TestPlan

DUE = ("mandatory", "optional")
PARTIAL_SUFFIX = ".partial.json"
JOURNAL_SUFFIX = ".cases.jsonl"


def partial_paths(out: str) -> tuple[str, str]:
    """The two sidecars of `out`: the plan without its test cases, and the cases as they arrive."""
    return out + PARTIAL_SUFFIX, out + JOURNAL_SUFFIX


def clear_partial(out: str) -> None:
    """Drop the sidecars, which the caller does only once `out` itself is written: a run whose plan
    fails to serialise at the last second is still a run whose work is on disk."""
    for p in partial_paths(out):
        Path(p).unlink(missing_ok=True)


def _append(path: str, records: list[tuple[str, Gap | TestCase]]) -> None:
    """One JSON object per line, tagged by what it is. Opened and closed per source, so what the
    journal holds has reached the operating system before the next model call starts."""
    with open(path, "a", encoding="utf-8") as f:
        for kind, obj in records:
            f.write(json.dumps({kind: obj.model_dump(mode="json")}, ensure_ascii=False) + "\n")


def _units(items: list[CoverageItem], batch: bool) -> list[list[CoverageItem]]:
    """The largest slices of `items` that `generate` treats exactly as it treats the whole list, so
    that persisting between them changes neither a prompt nor the order of the result: one source per
    slice when batching, since `generate` groups by source itself, and one item per slice when not,
    since it then walks the items in order. One slice is one or two model calls, which is the natural
    granularity for a stage whose unit of cost is a model call."""
    if not batch:
        return [[i] for i in items]
    groups: dict[str, list[CoverageItem]] = {}
    for i in items:
        groups.setdefault(i.source_id, []).append(i)
    return list(groups.values())


def _source(path: str, digest: str, model: str) -> Source:
    return Source(path=path, sha256=digest, model=model,
                  generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def ics_coverage(ics: list[ICSItem], items: list[CoverageItem]) -> tuple[int, int]:
    """Covered and total ICS items of status mandatory or optional: the X.291 clause 10.4 criterion of
    D21, "at least one test purpose per mandatory or optional ICS item". A conditional or unspecified
    feature is not part of the denominator."""
    covered = {i.source_id for i in items}
    due = [i.source_id for i in ics if i.status in DUE]
    return sum(s in covered for s in due), len(due)


def ics_coverage_line(ics: list[ICSItem], items: list[CoverageItem]) -> str:
    """The headline metric as one line. A document from which no feature was read has no criterion to
    satisfy, so it reports no figure rather than a vacuous 100 per cent."""
    cov, due = ics_coverage(ics, items)
    if not due:
        return "ICS coverage n/a (no mandatory or optional ICS item)"
    return f"ICS coverage {100.0 * cov / due:.1f}% ({cov}/{due})"


def run(path: str, llm, model: str, clause_ids: list[str] | None = None, attempts: int = 3, log=lambda s: None,
        use_model: bool = True, use_grammar: bool = True, deflate: bool = True, batch: bool = True,
        out: str | None = None) -> TestPlan:
    clauses = ingest(path)
    log(f"{len(clauses)} clauses")
    if clause_ids:
        known = {c.id for c in clauses}
        missing = [c for c in clause_ids if c not in known]
        if missing:
            raise ValueError(f"unknown clause ids: {', '.join(missing)}")
        clauses = [c for c in clauses if c.id in clause_ids]
    reqs, gaps = extract(clauses, llm, attempts, log)
    log(f"{len(reqs)} requirements, {len(gaps)} gaps")
    grammar = {c.id: harvest(c) for c in clauses} if use_grammar else {}
    log(f"{sum(len(d) for d in grammar.values())} objects from formal declarations")
    if use_model:
        objs, model_gaps = extract_objects(clauses, llm, attempts, log, grammar)
    else:
        objs, model_gaps = [o for c in clauses for o in assemble(c, grammar.get(c.id, []), [])], []
    log(f"{len(objs)} objects in the test model")
    ics = build_ics(reqs, objs)
    log(f"{len(ics)} ICS items")
    items = derive(reqs, objs, ics, deflate, log)  # rule (b) deletes test purposes: it reports here, not on stderr
    log(f"{len(items)} coverage items, {ics_coverage_line(ics, items)}")
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    journal = None
    if out:
        partial, journal = partial_paths(out)
        clear_partial(out)  # the journal records this run, never the one that crashed before it
        write_plan(build_plan(_source(path, digest, model), reqs, objs, ics, items, [], gaps + model_gaps), partial)
        log(f"wrote {partial}: every stage but generation")
    cases: list[TestCase] = []
    gen_gaps: list[Gap] = []
    for unit in _units(items, batch):
        got, unit_gaps = generate(unit, reqs, objs, clauses, llm, attempts, log, batch)
        cases += got
        gen_gaps += unit_gaps
        if journal:
            _append(journal, [("test_case", c) for c in got] + [("gap", g) for g in unit_gaps])
    log(f"{len(cases)} test cases, {len(gen_gaps)} gaps")
    plan = build_plan(_source(path, digest, model), reqs, objs, ics, items, cases, gaps + model_gaps + gen_gaps)
    log(f"plan: {len(plan.traceability)} traceability links, {len(plan.gaps)} gaps")
    return plan
