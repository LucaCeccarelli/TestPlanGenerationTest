"""Formal declarations -> test objects. Deterministic, no LLM, standard library only.

A clause that declares a structure formally - in CDDL, ABNF, JSON Schema or ASN.1 - states the field
names, their types, their presence and their value and size constraints exactly. Asking a language
model to read that back out of the prose loses most of it, so each notation gets a handler here and
the result is the same `TestObjectDraft` the model stage produces: the derivation ladder downstream
is unchanged.

A handler is a pair: `detect(text)` returns candidate blocks and `parse(block)` returns the drafts it
can read. Detection is deliberately permissive - a signature match on the notation's own syntax -
because the parser is the acceptance gate: a block it cannot read contributes nothing and raises
nothing. Every handler keys on its notation's published syntax only; nothing here knows any document,
standard, domain or field name.

Each draft's `source_quote` is the declaration line itself, so `model.check_object` grounds it
against the clause text exactly as it grounds an LLM-produced object. `direction` is left `internal`
throughout: which party receives or produces a structure is prose knowledge, not syntax, and is not
guessed here.
"""
import json
import re

from tpg.extract import norm
from tpg.models import Clause, TestObjectDraft

RANGE_RE = re.compile(r"(\d+)\s*\.\.\s*(\d+)")


def _bracket_delta(line: str) -> int:
    return sum(c in "([{" for c in line) - sum(c in ")]}" for c in line)


def _blocks(text: str, start_re: re.Pattern) -> list[list[str]]:
    """Every run of lines from one matching `start_re` to the line where the bracket depth that line
    opened returns to zero. A declaration that is never closed is not a block.
    ponytail: brackets are counted as characters, so a bracket inside a string literal miscounts the
    depth; carry a per-notation tokeniser only if a real document trips on it."""
    lines = text.splitlines()
    out: list[list[str]] = []
    i = 0
    while i < len(lines):
        if not start_re.match(lines[i].strip()):
            i += 1
            continue
        depth = 0
        end = None
        for j in range(i, len(lines)):
            depth += _bracket_delta(lines[j])
            if depth <= 0:
                end = j
                break
        if end is None:
            i += 1
            continue
        out.append(lines[i:end + 1])
        i = end + 1
    return out


def _members(lines: list[str]) -> list[str]:
    """The stripped lines of a block that sit directly inside the declaration's outermost bracket and
    open no group of their own. A nested group's members belong to that group, not to this
    declaration, and the line that opens one is no complete member, so neither is returned."""
    depth = _bracket_delta(lines[0])
    out: list[str] = []
    for line in lines[1:]:
        before, delta = depth, _bracket_delta(line)
        depth += delta
        if before == 1 and delta == 0:
            out.append(line.strip())
    return out


def _strip_innermost(text: str, pattern: str) -> str:
    """Remove bracketed groups until none is left, innermost first, so nesting is handled."""
    while True:
        new = re.sub(pattern, " ", text)
        if new == text:
            return text
        text = new


# --- CDDL (RFC 8610) ------------------------------------------------------------------------------

CDDL_START_RE = re.compile(r"^[A-Za-z][\w-]*\s*=\s*[({\[]")
CDDL_RULE_RE = re.compile(r"^([A-Za-z][\w-]*)")
# an occurrence indicator, then a member key (bareword or text literal), then ":" or "=>", then a type
CDDL_MEMBER_RE = re.compile(r"^(?P<occ>\?|\+|\d*\*\d*)?\s*(?P<key>\"[^\"]+\"|[A-Za-z_][\w-]*)\s*(?::|=>)\s*(?P<type>.+?)\s*,?$")
CDDL_SIZE_RE = re.compile(r"\.size\s*(\([^)]*\)|\S+)")
CDDL_CONTROL_RE = re.compile(r"\.[a-z]+\s*(?:\([^)]*\)|\S+)")
CDDL_LITERAL_RE = re.compile(r"\"[^\"]*\"|-?\d+(?:\.\d+)?|true|false|null|h'[0-9a-fA-F]*'")


def cddl_detect(text: str) -> list[str]:
    return ["\n".join(b) for b in _blocks(text, CDDL_START_RE)]


def cddl_parse(block: str) -> list[TestObjectDraft]:
    lines = block.splitlines()
    rule = CDDL_RULE_RE.match(lines[0].strip())
    if not rule:
        return []
    out: list[TestObjectDraft] = []
    for quote in _members(lines):
        m = CDDL_MEMBER_RE.match(quote)
        if not m:
            continue
        occ = m.group("occ") or ""
        type_text = m.group("type").strip()
        size = None
        ms = CDDL_SIZE_RE.search(type_text)
        if ms:
            size = " ".join(ms.group(1).strip("()").split())
        type_text = CDDL_CONTROL_RE.sub("", type_text).strip()
        if size is None:
            mr = RANGE_RE.search(type_text)
            if mr:
                size = f"{mr.group(1)}..{mr.group(2)}"
                type_text = RANGE_RE.sub("", type_text).strip()
        if size is None and occ and occ != "?":
            size = occ                     # an occurrence indicator is a count constraint
        value_domain = None
        alts = [a.strip() for a in type_text.split("/") if a.strip()]
        if alts and all(CDDL_LITERAL_RE.fullmatch(a) for a in alts):
            value_domain = " / ".join(alts)
            type_text = ""                 # the alternation is the value domain, not an encoding
        out.append(TestObjectDraft(name=m.group("key").strip('"'), kind="field",
                                   presence="optional" if occ == "?" else "mandatory",
                                   type=type_text or None, value_domain=value_domain, size=size,
                                   relations=[f"member of {rule.group(1)}"], source_quote=quote))
    return out


# --- ABNF (RFC 5234) -----------------------------------------------------------------------------

ABNF_RULE_RE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9-]*)\s*=/?\s*(?P<elements>\S.*)$")
# the acceptance gate: an element list is made of terminal values, rule names, repetitions,
# alternations and groups, and of nothing else
ABNF_ELEMENTS_RE = re.compile(r"^(?:\"[^\"]*\"|%[bdx][0-9A-Fa-f]+(?:[.-][0-9A-Fa-f]+)*|[A-Za-z][A-Za-z0-9-]*|\d+|\*|/|[()\[\]]|\s)+$")
ABNF_REPEAT_RE = re.compile(r"\d+\*\d*|\d*\*\d+")
ABNF_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
ABNF_QUOTED_RE = re.compile(r"\"[^\"]*\"")


def abnf_detect(text: str) -> list[str]:
    """One block holding every rule line of the text: an optional group in one rule is what makes a
    rule defined elsewhere optional, so the rules have to be read together."""
    rules = [line.strip() for line in text.splitlines() if _abnf_rule(line.strip())]
    return ["\n".join(rules)] if rules else []


def _abnf_rule(line: str) -> tuple[str, str] | None:
    m = ABNF_RULE_RE.match(line)
    if not m or not ABNF_ELEMENTS_RE.match(m.group("elements")):
        return None
    return m.group("name"), m.group("elements").strip()


def abnf_parse(block: str) -> list[TestObjectDraft]:
    rules = [(*r, line.strip()) for line in block.splitlines() if (r := _abnf_rule(line.strip()))]
    required: set[str] = set()
    bracketed: set[str] = set()
    for _, elements, _quote in rules:
        outside = _strip_innermost(elements, r"\[[^\[\]]*\]")
        required |= set(ABNF_NAME_RE.findall(ABNF_QUOTED_RE.sub(" ", outside)))
        bracketed |= set(ABNF_NAME_RE.findall(ABNF_QUOTED_RE.sub(" ", elements)))
    out: list[TestObjectDraft] = []
    for name, elements, quote in rules:
        presence = "mandatory" if name in required else ("optional" if name in bracketed else "unspecified")
        alts = [a.strip() for a in elements.split("/") if a.strip()]
        value_domain = " / ".join(alts) if alts and all(ABNF_QUOTED_RE.fullmatch(a) for a in alts) else None
        repeat = ABNF_REPEAT_RE.search(elements)
        out.append(TestObjectDraft(name=name, kind="structure", presence=presence, type=elements,
                                   value_domain=value_domain, size=repeat.group(0) if repeat else None,
                                   source_quote=quote))
    return out


# --- JSON Schema ---------------------------------------------------------------------------------

JSON_START_RE = re.compile(r"^\{")
JSON_SIZE_KEYS = ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems")


def _json_object(block: str) -> dict | None:
    try:
        doc = json.loads(block)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("properties"), dict) else None


def json_schema_detect(text: str) -> list[str]:
    return [b for b in ("\n".join(lines) for lines in _blocks(text, JSON_START_RE)) if _json_object(b)]


def _json_text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def json_schema_parse(block: str) -> list[TestObjectDraft]:
    doc = _json_object(block)
    if doc is None:
        return []
    lines = [line.strip() for line in block.splitlines()]
    required = doc.get("required") if isinstance(doc.get("required"), list) else []
    out: list[TestObjectDraft] = []
    for name, schema in doc["properties"].items():
        if not isinstance(schema, dict) or not name:
            continue
        declared = re.compile(r"^\s*\"" + re.escape(name) + r"\"\s*:")
        quote = next((l for l in lines if declared.match(l)), None) or next((l for l in lines if f'"{name}"' in l), lines[0])
        kinds = schema.get("type")
        kinds = " / ".join(kinds) if isinstance(kinds, list) else kinds
        fmt = schema.get("format")
        value_domain = None
        if isinstance(schema.get("enum"), list):
            value_domain = " / ".join(_json_text(v) for v in schema["enum"])
        elif "const" in schema:
            value_domain = _json_text(schema["const"])
        elif isinstance(schema.get("pattern"), str):
            value_domain = schema["pattern"]
        size = ", ".join(f"{k} {schema[k]}" for k in JSON_SIZE_KEYS if k in schema)
        out.append(TestObjectDraft(name=name, kind="field",
                                   presence="mandatory" if name in required else "optional",
                                   type=(f"{kinds} ({fmt})" if kinds and fmt else kinds or fmt) or None,
                                   value_domain=value_domain, size=size or None, source_quote=quote))
    return out


# --- ASN.1 (ITU-T X.680) -------------------------------------------------------------------------

ASN1_START_RE = re.compile(r"^(?P<name>[A-Z][\w-]*)\s*::=\s*(?P<construct>SEQUENCE|SET|CHOICE)\s*\{")
ASN1_MEMBER_RE = re.compile(r"^(?P<field>[a-z][\w-]*)\s+(?P<rest>[A-Z].*)$")
ASN1_SIZE_RE = re.compile(r"SIZE\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
ASN1_NAMED_RE = re.compile(r"\{([^{}]*)\}")
ASN1_TAIL_RE = re.compile(r"\b(?:OPTIONAL|DEFAULT)\b.*$")


def asn1_detect(text: str) -> list[str]:
    return ["\n".join(b) for b in _blocks(text, ASN1_START_RE)]


def asn1_parse(block: str) -> list[TestObjectDraft]:
    lines = block.splitlines()
    head = ASN1_START_RE.match(lines[0].strip())
    if not head:
        return []
    # exactly one alternative of a CHOICE is present, so no alternative of it is mandatory
    choice = head.group("construct") == "CHOICE"
    out: list[TestObjectDraft] = []
    for quote in _members(lines):
        m = ASN1_MEMBER_RE.match(quote)
        if not m:
            continue
        rest = m.group("rest").strip().rstrip(",").strip()
        optional = choice or bool(re.search(r"\b(?:OPTIONAL|DEFAULT)\b", rest))
        value_domain = None
        named = ASN1_NAMED_RE.search(rest)
        if named:
            value_domain = " ".join(named.group(1).split()) or None
            rest = rest[:named.start()] + " " + rest[named.end():]
        size = None
        ms = ASN1_SIZE_RE.search(rest)
        if ms:
            size = " ".join(ms.group(1).split())
        else:
            mr = RANGE_RE.search(rest)
            if mr:
                size = f"{mr.group(1)}..{mr.group(2)}"
        rest = ASN1_TAIL_RE.sub("", _strip_innermost(rest, r"\([^()]*\)"))
        out.append(TestObjectDraft(name=m.group("field"), kind="field",
                                   presence="optional" if optional else "mandatory",
                                   type=" ".join(rest.split()) or None, value_domain=value_domain, size=size,
                                   source_quote=quote))
    return out


HANDLERS = {
    "cddl": (cddl_detect, cddl_parse),
    "abnf": (abnf_detect, abnf_parse),
    "json_schema": (json_schema_detect, json_schema_parse),
    "asn1": (asn1_detect, asn1_parse),
}


def harvest(clause: Clause) -> list[TestObjectDraft]:
    """Every object the clause declares formally, in handler order, de-duplicated by name and quote.
    A draft whose quote is not in the clause text is dropped: the quote grounds the object downstream."""
    body = norm(clause.text)
    out: list[TestObjectDraft] = []
    seen: set[tuple[str, str]] = set()
    for detect, parse in HANDLERS.values():
        for block in detect(clause.text):
            for d in parse(block):
                key = (norm(d.name), norm(d.source_quote))
                if not key[0] or key in seen or key[1] not in body:
                    continue
                seen.add(key)
                out.append(d)
    return out
