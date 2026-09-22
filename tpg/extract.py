"""Annotation-then-conversion: regex marks candidate sentences, the LLM converts them, rules check each
draft; valid drafts are kept and only invalid ones are retried."""
import re

from tpg.llm import LLMError
from tpg.models import Clause, Gap, Requirement, RequirementBatch, RequirementDraft

CANDIDATE_RE = re.compile(r"\b(shall|must|should|may|is required to)\b", re.I)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"'])")
MODAL_RE = {
    "shall": re.compile(r"\b(shall|must)\b(?!\s+(not|never)\b)"),
    "shall_not": re.compile(r"\b(shall|must)\s+(not|never)\b"),
    "should": re.compile(r"\bshould\b(?!\s+(not|never)\b)"),
    "should_not": re.compile(r"\bshould\s+(not|never)\b"),
    "may": re.compile(r"\bmay\b(?!\s+not\b)"),
}
CHUNK_LIMIT = 8000


def norm(s: str) -> str:
    return " ".join(s.split()).lower()


def find_candidates(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(flat) if CANDIDATE_RE.search(s)]


def chunks(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Split at line boundaries into pieces of at most `limit` characters (a single over-long line
    stays whole)."""
    out: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.split("\n"):
        if buf and size + len(line) + 1 > limit:
            out.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        out.append("\n".join(buf))
    return out


def build_extract_prompt(clause: Clause, chunk: str, part: str, candidates: list[str], failures: list[str],
                         accepted_texts: list[str]) -> str:
    cands = "\n".join(f"- {c}" for c in candidates)
    feedback = ""
    if failures:
        feedback = ("\nSome requirements of your previous answer were rejected for these reasons; return ONLY corrected "
                    "versions of those rejected requirements, nothing else:\n" + "\n".join(f"- {f}" for f in failures) + "\n")
        if accepted_texts:
            feedback += "Already accepted, do not repeat:\n" + "\n".join(f"- {t}" for t in accepted_texts) + "\n"
    return f"""You extract atomic, testable requirements from a technical specification.

Clause {clause.id} "{clause.title}" (part {part}):
\"\"\"
{chunk}
\"\"\"

Candidate sentences (each contains a modal verb):
{cands}

Rules:
- Produce one requirement per atomic obligation. Split a sentence that contains several obligations.
- Do not invent requirements that are not in the candidate sentences.
- "text": one self-contained testable statement, keep the modal verb.
- "modality": one of shall, shall_not, should, should_not, may. Use "must" as shall, "must not" / "shall never" as shall_not,
  "should not" as should_not.
- "conditions": the list of conditions under which the obligation applies (e.g. ["request is malformed", "session has expired"] for "if A or B then ..."); empty list if unconditional.
- "source_quote": a VERBATIM substring of the clause text that contains THIS requirement's own modal verb, not one belonging to a
  different obligation nearby. Keep it as short as possible while still containing that modal verb. If a bullet elaborates or
  restates a preceding obligation without a modal verb of its own, fold its detail into the "text" of the requirement whose
  sentence does carry the modal verb, and quote that sentence.
- Copy source_quote exactly as printed, including unusual characters. A table row line "Header: value | Header: value" is text too.
- If none of the candidate sentences states an obligation of the system under test (e.g. bibliography entries, definitions of the
  words shall/should/may, dates), return an empty list.
{feedback}
Reply with JSON only: {{"requirements": [{{"text": ..., "modality": ..., "conditions": [...], "source_quote": ...}}]}}"""


def check_draft(clause: Clause, n: int, d: RequirementDraft) -> str | None:
    if not d.text.strip():
        return f"requirement {n}: text is empty"
    q = norm(d.source_quote)
    if not q or q not in norm(clause.text):
        return f"requirement {n}: source_quote is not a verbatim substring of the clause: {d.source_quote!r}"
    if not MODAL_RE[d.modality].search(q):
        return f"requirement {n}: modality {d.modality!r} does not appear in source_quote {d.source_quote!r}"
    return None


def check_requirements(clause: Clause, drafts: list[RequirementDraft]) -> list[str]:
    return [m for m in (check_draft(clause, n, d) for n, d in enumerate(drafts, 1)) if m]


def _accept(clause: Clause, drafts: list[RequirementDraft], accepted: list[RequirementDraft]) -> list[str]:
    """Move valid, non-duplicate drafts into `accepted`; return the failure messages of the rest."""
    failures = []
    seen = {(norm(a.text), norm(a.source_quote)) for a in accepted}
    for n, d in enumerate(drafts, 1):
        msg = check_draft(clause, n, d)
        if msg:
            failures.append(msg)
        elif (norm(d.text), norm(d.source_quote)) not in seen:
            accepted.append(d)
            seen.add((norm(d.text), norm(d.source_quote)))
    return failures


def extract_clause(clause: Clause, llm, attempts: int = 3) -> tuple[list[Requirement], Gap | None]:
    accepted: list[RequirementDraft] = []
    open_failures: list[str] = []
    parts = chunks(clause.text)
    for i, chunk in enumerate(parts, 1):
        candidates = find_candidates(chunk)
        if not candidates:
            continue
        failures: list[str] = []
        for _ in range(attempts):
            prompt = build_extract_prompt(clause, chunk, f"{i}/{len(parts)}", candidates, failures, [a.text for a in accepted])
            try:
                batch = llm.complete(prompt, RequirementBatch)
            except LLMError as e:
                failures = [str(e)]
                continue
            failures = _accept(clause, batch.requirements, accepted)
            if not failures:
                break
        open_failures.extend(failures)
    body = norm(clause.text)
    ordered = sorted(accepted, key=lambda d: body.index(norm(d.source_quote)))
    reqs = [Requirement(id=f"REQ-{clause.id}-{n}", clause_id=clause.id, **d.model_dump()) for n, d in enumerate(ordered, 1)]
    gap = None
    if open_failures:
        gap = Gap(requirement_id=None, clause_id=clause.id, stage="extract", reason="; ".join(open_failures), attempts=attempts)
    return reqs, gap


def extract(clauses: list[Clause], llm, attempts: int = 3, log=lambda s: None) -> tuple[list[Requirement], list[Gap]]:
    reqs: list[Requirement] = []
    gaps: list[Gap] = []
    for clause in clauses:
        if not find_candidates(clause.text):
            continue
        got, gap = extract_clause(clause, llm, attempts)
        reqs.extend(got)
        if gap:
            gaps.append(gap)
        log(f"clause {clause.id}: {len(got)} requirements" + (" (GAP)" if gap else ""))
    return reqs, gaps
