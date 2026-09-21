"""Annotation-then-conversion: regex marks candidate sentences, the LLM converts them, rules check them."""
import re

from tpg.llm import LLMError
from tpg.models import Clause, Gap, Requirement, RequirementBatch, RequirementDraft

CANDIDATE_RE = re.compile(r"\b(shall|must|should|may|is required to)\b", re.I)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\"'])")
MODAL_WORDS = {"shall": "shall", "shall_not": "shall not", "should": "should", "may": "may"}


def norm(s: str) -> str:
    return " ".join(s.split()).lower()


def find_candidates(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(flat) if CANDIDATE_RE.search(s)]


def build_extract_prompt(clause: Clause, candidates: list[str], failures: list[str]) -> str:
    cands = "\n".join(f"- {c}" for c in candidates)
    feedback = ""
    if failures:
        feedback = "\nYour previous answer was rejected for these reasons; fix them:\n" + "\n".join(f"- {f}" for f in failures) + "\n"
    return f"""You extract atomic, testable requirements from a technical standard.

Clause {clause.id} "{clause.title}":
\"\"\"
{clause.text}
\"\"\"

Candidate sentences (each contains a modal verb):
{cands}

Rules:
- Produce one requirement per atomic obligation. Split a sentence that contains several obligations.
- Do not invent requirements that are not in the candidate sentences.
- "text": one self-contained testable statement, keep the modal verb.
- "modality": one of shall, shall_not, should, may. Use "must" as shall and "must not" as shall_not.
- "conditions": the list of conditions under which the obligation applies (e.g. ["request is malformed", "session has expired"] for "if A or B then ..."); empty list if unconditional.
- "source_quote": a VERBATIM substring of the clause text that contains THIS requirement's own modal verb, not one belonging to a
  different obligation nearby. Keep it as short as possible while still containing that modal verb: the word matching "modality"
  (shall/must, shall not/must not, should, may) must literally appear inside source_quote. If a bullet elaborates or restates a
  preceding obligation without a modal verb of its own, that elaboration is not a separate requirement: fold its detail into the
  "text" of the requirement whose sentence does carry the modal verb, and quote that sentence, not the elaboration.
- Copy source_quote exactly as printed in the clause text, including any unusual or non-ASCII characters. Escape any control
  character as a JSON \\u escape (e.g. \\u0001) so the reply stays valid JSON; do not drop or alter the character itself.
{feedback}
Reply with JSON only: {{"requirements": [{{"text": ..., "modality": ..., "conditions": [...], "source_quote": ...}}]}}"""


def check_requirements(clause: Clause, drafts: list[RequirementDraft]) -> list[str]:
    if not drafts:
        return ["no requirements returned although candidates exist"]
    body = norm(clause.text)
    msgs: list[str] = []
    for n, d in enumerate(drafts, 1):
        if not d.text.strip():
            msgs.append(f"requirement {n}: text is empty")
        q = norm(d.source_quote)
        if not q or q not in body:
            msgs.append(f"requirement {n}: source_quote is not a verbatim substring of the clause: {d.source_quote!r}")
        elif MODAL_WORDS[d.modality] not in q and not (d.modality == "shall" and "must" in q) \
                and not (d.modality == "shall_not" and "must not" in q):
            msgs.append(f"requirement {n}: modality {d.modality!r} does not appear in source_quote {d.source_quote!r}")
    return msgs


def extract_clause(clause: Clause, llm, attempts: int = 3) -> tuple[list[Requirement], Gap | None]:
    candidates = find_candidates(clause.text)
    failures: list[str] = []
    for _ in range(attempts):
        try:
            batch = llm.complete(build_extract_prompt(clause, candidates, failures), RequirementBatch)
        except LLMError as e:
            failures = [str(e)]
            continue
        failures = check_requirements(clause, batch.requirements)
        if not failures:
            reqs = [Requirement(id=f"REQ-{clause.id}-{n}", clause_id=clause.id, **d.model_dump())
                    for n, d in enumerate(batch.requirements, 1)]
            return reqs, None
    return [], Gap(requirement_id=None, clause_id=clause.id, stage="extract",
                   reason="; ".join(failures), attempts=attempts)


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
