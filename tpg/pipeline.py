"""ingest -> grammar -> extract -> model -> ICS -> derive -> generate -> plan. One `log` line per stage
with its counts, including the ICS total and the ICS coverage that is the headline metric (D21, D27)."""
import hashlib
from datetime import datetime, timezone

from tpg.derive import derive
from tpg.emit import build_plan
from tpg.extract import extract
from tpg.grammar import harvest
from tpg.ics import build_ics
from tpg.generate import generate
from tpg.ingest import ingest
from tpg.model import assemble, extract_objects
from tpg.models import CoverageItem, ICSItem, Source, TestPlan

DUE = ("mandatory", "optional")


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
        use_model: bool = True, use_grammar: bool = True, deflate: bool = True, batch: bool = True) -> TestPlan:
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
    items = derive(reqs, objs, ics, deflate)
    log(f"{len(items)} coverage items, {ics_coverage_line(ics, items)}")
    cases, gen_gaps = generate(items, reqs, objs, clauses, llm, attempts, log, batch)
    log(f"{len(cases)} test cases, {len(gen_gaps)} gaps")
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    source = Source(path=path, sha256=digest, model=model, generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    plan = build_plan(source, reqs, objs, ics, items, cases, gaps + model_gaps + gen_gaps)
    log(f"plan: {len(plan.traceability)} traceability links, {len(plan.gaps)} gaps")
    return plan
