"""ingest -> extract -> generate -> plan. Progress goes through `log`."""
import hashlib
from datetime import datetime, timezone

from tpg.emit import build_plan
from tpg.extract import extract
from tpg.generate import generate
from tpg.ingest import ingest
from tpg.models import Source, TestPlan


def run(path: str, llm, model: str, clause_ids: list[str] | None = None, attempts: int = 3, log=lambda s: None) -> TestPlan:
    clauses = ingest(path)
    log(f"{len(clauses)} clauses")
    if clause_ids:
        known = {c.id for c in clauses}
        missing = [c for c in clause_ids if c not in known]
        if missing:
            raise ValueError(f"unknown clause ids: {', '.join(missing)}")
        clauses = [c for c in clauses if c.id in clause_ids]
    reqs, gaps = extract(clauses, llm, attempts, log)
    cases, gen_gaps = generate(reqs, clauses, llm, attempts, log)
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    source = Source(path=path, sha256=digest, model=model,
                    generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return build_plan(source, reqs, cases, gaps + gen_gaps)
