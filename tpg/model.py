"""Test model stage: the LLM lists the objects a clause defines or constrains; rules ground each object."""
from tpg.extract import chunks, find_candidates, norm
from tpg.llm import LLMError
from tpg.models import Clause, Gap, TestObject, TestObjectBatch, TestObjectDraft


def has_rows(text: str) -> bool:
    return any(" | " in line and ": " in line for line in text.splitlines())


def build_model_prompt(clause: Clause, chunk: str, part: str, failures: list[str], accepted_names: list[str]) -> str:
    feedback = ""
    if failures:
        feedback = ("\nSome objects of your previous answer were rejected for these reasons; return ONLY corrected versions of "
                    "those rejected objects, nothing else:\n" + "\n".join(f"- {f}" for f in failures) + "\n")
        if accepted_names:
            feedback += "Already accepted, do not repeat: " + ", ".join(accepted_names) + "\n"
    return f"""You build a test model from one clause of a technical specification: the list of OBJECTS the clause defines or
constrains, each with the attributes the text states. Objects are data elements or fields, structures, messages, parameters,
distinguished values, or behaviours. The system under test is the party that must conform (infer it from the clause).

Clause {clause.id} "{clause.title}" (part {part}):
\"\"\"
{chunk}
\"\"\"

Rules:
- One object per named element. A line "Header: value | Header: value" is one table row: produce one object per row that names
  an element, parameter, field, message or value, and read its attributes from the other columns.
- "kind": field | structure | message | parameter | value | behaviour.
- "direction": received (the system under test receives or parses it), produced (it creates or sends it), internal.
- "presence": mandatory if the text says it shall be present, is required, or marks it M/mandatory; optional if it may be
  present or is marked O/optional; conditional if presence depends on something (then give "condition"); else unspecified.
- "type": the encoding or data type as written (e.g. "text string", "unsigned integer", "URI", "map of ..."); null if not stated.
- "value_domain": allowed values, format or pattern as written; null if not stated.
- "size": length, range or count constraint with its numbers as written; null if not stated.
- "relations": constraints tying this object to other objects (e.g. "same value as X", "unique within Y"); empty if none.
- "source_quote": a VERBATIM substring of the clause text that names the object (a table row line is valid text). Copy it exactly.
- Do not invent attributes; leave them null or unspecified when the text does not state them.
{feedback}
Reply with JSON only: {{"objects": [{{"name": ..., "kind": ..., "direction": ..., "presence": ..., "condition": ..., "type": ...,
"value_domain": ..., "size": ..., "relations": [...], "source_quote": ...}}]}}"""


def check_object(clause: Clause, n: int, d: TestObjectDraft) -> str | None:
    if not d.name.strip():
        return f"object {n}: name is empty"
    q = norm(d.source_quote)
    if not q or q not in norm(clause.text):
        return f"object {n} ({d.name}): source_quote is not a verbatim substring of the clause: {d.source_quote!r}"
    if d.presence == "conditional" and not (d.condition or "").strip():
        return f"object {n} ({d.name}): presence is conditional but no condition is given"
    if d.presence != "conditional" and d.condition:
        return f"object {n} ({d.name}): a condition is given but presence is {d.presence!r}, set presence to conditional"
    return None


def merge_objects(drafts: list[TestObjectDraft]) -> list[TestObjectDraft]:
    """Same name (case-insensitive) within a clause: keep the first, fill its unset attributes from later ones."""
    out: list[TestObjectDraft] = []
    by_name: dict[str, TestObjectDraft] = {}
    for d in drafts:
        key = norm(d.name)
        if key not in by_name:
            by_name[key] = d
            out.append(d)
            continue
        first = by_name[key]
        for f in ("condition", "type", "value_domain", "size"):
            if getattr(first, f) is None and getattr(d, f) is not None:
                setattr(first, f, getattr(d, f))
        if first.presence == "unspecified" and d.presence != "unspecified":
            first.presence = d.presence
        if first.direction == "internal" and d.direction != "internal":
            first.direction = d.direction
        for r in d.relations:
            if r not in first.relations:
                first.relations.append(r)
    return out


def _accept(clause: Clause, drafts: list[TestObjectDraft], accepted: list[TestObjectDraft]) -> list[str]:
    """Move valid, non-duplicate drafts into `accepted`; return the failure messages of the rest.
    Re-emitting an already accepted object must not count as resolving an open failure."""
    failures = []
    seen = {(norm(a.name), norm(a.source_quote)) for a in accepted}
    for n, d in enumerate(drafts, 1):
        msg = check_object(clause, n, d)
        if msg:
            failures.append(msg)
        elif (norm(d.name), norm(d.source_quote)) not in seen:
            accepted.append(d)
            seen.add((norm(d.name), norm(d.source_quote)))
    return failures


def extract_objects_clause(clause: Clause, llm, attempts: int = 3) -> tuple[list[TestObject], Gap | None]:
    accepted: list[TestObjectDraft] = []
    open_failures: list[str] = []
    parts = chunks(clause.text)
    for i, chunk in enumerate(parts, 1):
        if not (find_candidates(chunk) or has_rows(chunk)):
            continue
        failures: list[str] = []
        for _ in range(attempts):
            prompt = build_model_prompt(clause, chunk, f"{i}/{len(parts)}", failures, [a.name for a in accepted])
            try:
                batch = llm.complete(prompt, TestObjectBatch)
            except LLMError as e:
                failures = failures + [str(e)]
                continue
            before = len(accepted)
            new_failures = _accept(clause, batch.objects, accepted)
            resolved = len(accepted) - before          # newly accepted objects count as resolved open failures
            failures = failures[resolved:] + new_failures
            if not failures:
                break
        open_failures.extend(failures)
    merged = merge_objects(accepted)
    body = norm(clause.text)
    ordered = sorted(merged, key=lambda d: body.index(norm(d.source_quote)))
    objs = [TestObject(id=f"OBJ-{clause.id}-{n}", clause_id=clause.id, **d.model_dump()) for n, d in enumerate(ordered, 1)]
    gap = None
    if open_failures:
        gap = Gap(source_id=None, clause_id=clause.id, stage="model", reason="; ".join(open_failures), attempts=attempts)
    return objs, gap


def extract_objects(clauses: list[Clause], llm, attempts: int = 3, log=lambda s: None) -> tuple[list[TestObject], list[Gap]]:
    objs: list[TestObject] = []
    gaps: list[Gap] = []
    for clause in clauses:
        if not (find_candidates(clause.text) or has_rows(clause.text)):
            continue
        got, gap = extract_objects_clause(clause, llm, attempts)
        objs.extend(got)
        if gap:
            gaps.append(gap)
        log(f"clause {clause.id}: {len(got)} objects" + (" (GAP)" if gap else ""))
    return objs, gaps
