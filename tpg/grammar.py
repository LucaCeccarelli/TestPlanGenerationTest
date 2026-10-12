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

RANGE_RE = re.compile(r"(\d+)\s*\.\.\.?\s*(\d+)")
# a repetition carrying at least one bound, written the same way in CDDL (RFC 8610 section 3.2) and
# in ABNF (RFC 5234 section 3.6); a bare "*" carries no bound and is therefore not matched
REPEAT_RE = re.compile(r"\d+\*\d*|\d*\*\d+")


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


def _without_closers(line: str, count: int) -> str:
    """The line without the `count` brackets at its end that close an enclosing declaration, and
    without the separators around them. Only those: a bracket closing the member's own constraint
    belongs to the member."""
    out = line.rstrip().rstrip(",").rstrip()
    while count and out and out[-1] in ")]}":
        out = out[:-1].rstrip().rstrip(",").rstrip()
        count -= 1
    return out


def _members(lines: list[str]) -> list[str]:
    """The stripped lines of a block that sit directly inside the declaration's outermost bracket and
    open no group of their own. A nested group's members belong to that group, not to this
    declaration, and the line that opens one is no complete member, so neither is returned. A
    declaration may close on its last member's line; that member is returned without the closer."""
    depth = _bracket_delta(lines[0])
    out: list[str] = []
    for line in lines[1:]:
        before, delta = depth, _bracket_delta(line)
        depth += delta
        if before != 1:
            continue
        if delta == 0:
            out.append(line.strip())
        elif depth == 0 and (member := _without_closers(line.strip(), -delta)):
            out.append(member)
    return out


def _strip_comment(line: str) -> str:
    """The line without its trailing comment: in CDDL a ";" outside a text literal starts one
    (RFC 8610 section 2.1) and the rest of the line is prose about the declaration, not part of it."""
    quoted = False
    for i, ch in enumerate(line):
        if ch == '"' and (i == 0 or line[i - 1] != "\\"):
            quoted = not quoted
        elif ch == ";" and not quoted:
            return line[:i].rstrip()
    return line


def _declaration(name: str, type_text: str | None, quote: str) -> TestObjectDraft:
    """The named block itself, as one object beside the objects of its members.

    A standard's top-level structures are what a conformance test case names as the thing under
    check far more often than any one member, so a declaration that exists as no object can never be
    matched and its own ladder - presence, encoding validity and invalidity, consistency - is never
    derived. Four rulings, one per attribute:

    - `kind="structure"`: a declared block is a structure and not a member of one, which is the kind
      an ABNF rule already takes for the same thing, so the notations agree.
    - `presence="unspecified"`: a declaration states that the name exists, never that it appears
      anywhere; whether a structure is present is stated in prose, which the model stage reads. The
      settled rule that an unspecified presence emits no presence and no absence item then applies,
      and such an object is no ICS feature either.
    - `relations=[]`: each member already records the edge as `member of <name>`, in the direction
      that is a testable statement. Repeating the member list here would mint one `consistency` item
      per member whose purpose is that member's own presence item, and would key the generic group
      (D31) on the same member list twice.
    - `source_quote`: the declaring line alone. It is the construct that states both the name and the
      type, it is verbatim clause text as D24 requires, and a whole block is a quote no plan page can
      print and no provenance comparison (D25 rule b) can use.
    """
    return TestObjectDraft(name=name, kind="structure", presence="unspecified", type=type_text,
                           source_quote=quote)


def _strip_innermost(text: str, pattern: str) -> str:
    """Remove bracketed groups until none is left, innermost first, so nesting is handled."""
    while True:
        new = re.sub(pattern, " ", text)
        if new == text:
            return text
        text = new


# --- CDDL (RFC 8610) ------------------------------------------------------------------------------

CDDL_ID = r"[A-Za-z@_$][\w@$.-]*"
CDDL_START_RE = re.compile(r"^(?P<name>[A-Za-z][\w-]*)\s*=\s*(?P<bracket>[({\[])")
# RFC 8610 section 2.1: braces enclose a map, square brackets an array, parentheses a group. The
# bracket a rule opens is the construct that declares the name, so it states what the name denotes.
CDDL_CONSTRUCT = {"{": "map", "[": "array", "(": "group"}
# RFC 8610 section 3.5.1: a member key is a bareword or a value followed by ":", or a type followed
# by "=>". A bareword before "=>" is a type, so it names no field and is deliberately not a key here.
CDDL_MEMBER_RE = re.compile(r"^(?P<occ>\?|\+|\d*\*\d*)?\s*"
                            r"(?:(?P<key>\"[^\"]+\"|[A-Za-z_][\w-]*)\s*:|(?P<vkey>\"[^\"]+\")\s*=>)"
                            r"\s*(?P<type>.+?)\s*,?$")
CDDL_TYPE_KEY_RE = re.compile(r"^(?:\?|\+|\d*\*\d*)?\s*[A-Za-z_][\w-]*\s*\^?\s*=>")
# a one-line rule (RFC 8610 section 3.1) whose right-hand side is one type: an identifier or a tagged
# type, optionally carrying control operators. Anything else - a bracket, an alternation, a second
# bare word - is not a lone type, which is what keeps a sentence with an equals sign out.
CDDL_ASSIGN_RE = re.compile(r"^(?P<name>" + CDDL_ID + r")\s*=\s*(?P<type>"
                            r"(?:#\d(?:\.\d+)?(?:\([^()]*\))?|" + CDDL_ID + r")"
                            r"(?:\s*\.[a-z]+\s*(?:\([^()]*\)|\"[^\"]*\"|[^\s()]+))*)$")
CDDL_SIZE_RE = re.compile(r"\.size\s*(\([^)]*\)|\S+)")
# RFC 8610 sections 3.8.2 and 3.8.3: these operators bound the value, not the encoded length
CDDL_VALUE_CONTROL_RE = re.compile(r"\.(regexp|bits|lt|le|gt|ge|eq|ne)\s*(\([^)]*\)|\"[^\"]*\"|\S+)")
CDDL_CONTROL_RE = re.compile(r"\.[a-z]+\s*(?:\([^)]*\)|\S+)")
CDDL_LITERAL_RE = re.compile(r"\"[^\"]*\"|-?\d+(?:\.\d+)?|true|false|null|h'[0-9a-fA-F]*'")
CDDL_GROUP_CHOICE_RE = re.compile(r",?\s*//\s*$")
# the comparison and matching operators are symbols a test purpose cannot read back, so the domain
# they state is written in the words of their definition rather than left as the marker
CONTROL_TEXT = {"lt": "less than", "le": "at most", "gt": "greater than", "ge": "at least",
                "eq": "equal to", "ne": "not equal to", "regexp": "matching", "bits": "bits set within"}
# an occurrence indicator carrying no number states no limit, so it is written out rather than left
# as a marker: a boundary case derived from "*" would read as nonsense
OCCURRENCE_TEXT = {"*": "any number of occurrences", "+": "one or more occurrences"}


def _cddl_assignments(text: str) -> list[str]:
    """Every one-line type assignment the text writes at bracket depth zero. A line inside a
    declaration is a member of it, not a rule, so the depth is tracked rather than assumed."""
    out: list[str] = []
    depth = 0
    for line in text.splitlines():
        delta = _bracket_delta(line)
        if depth == 0 and delta == 0 and CDDL_ASSIGN_RE.match(_strip_comment(line).strip()):
            out.append(line.strip())
        depth = max(0, depth + delta)
    return out


def _cddl_constraints(type_text: str) -> tuple[str, str | None, str | None]:
    """A type with its constraints removed, plus the value domain and the size they state.

    RFC 8610 section 3.8.1: `.size` bounds the encoded length, so it is a size and no domain of
    values. Sections 3.8.2 and 3.8.3: the comparison and matching operators bound the value, so they
    are a domain and no length. Section 2.2.2: a range is a range of *values*, so it is both a domain
    to violate and a pair of bounds to probe - equivalence partitioning and boundary value analysis
    (ISO/IEC/IEEE 29119-4 clauses 5.2.2 and 5.2.3) apply to the same construct. A bounded repetition
    inside the type bounds how many occurrences it holds, which is a size.

    A tagged type (section 3.6) is returned verbatim: what stands inside the tag constrains the
    tagged type, not the one the tag builds, and reading it as this type's own domain would be false.
    """
    if type_text.startswith("#"):
        return type_text, None, None
    size = value_domain = None
    if ms := CDDL_SIZE_RE.search(type_text):
        size = " ".join(ms.group(1).strip("()").split())
        type_text = type_text[:ms.start()] + " " + type_text[ms.end():]
    if mv := CDDL_VALUE_CONTROL_RE.search(type_text):
        value_domain = f"{CONTROL_TEXT[mv.group(1)]} {' '.join(mv.group(2).strip('()').split())}"
        type_text = type_text[:mv.start()] + " " + type_text[mv.end():]
    type_text = CDDL_CONTROL_RE.sub(" ", type_text)
    if mr := RANGE_RE.search(type_text):
        bound = f"{mr.group(1)}..{mr.group(2)}"
        value_domain, size = value_domain or bound, size or bound
        type_text = RANGE_RE.sub(" ", type_text)
    elif size is None and (mo := REPEAT_RE.search(type_text)):
        size = mo.group(0)
    return " ".join(type_text.split()), value_domain, size


def cddl_detect(text: str) -> list[str]:
    """Every bracketed declaration, then every one-line type assignment - but the latter only where
    the text independently shows CDDL, i.e. where a bracketed declaration was found. `name = type` is
    a shape an ordinary sentence takes too, and the shape alone is too thin a gate for it."""
    blocks = ["\n".join(b) for b in _blocks(text, CDDL_START_RE)]
    return blocks + (_cddl_assignments(text) if blocks else [])


def cddl_parse(block: str) -> list[TestObjectDraft]:
    """The declaration itself, then one draft per named member. The declaration's type is the
    bracket it opens (`CDDL_CONSTRUCT`); see `_declaration` for its other attributes.

    A member whose line the parser cannot read contributes nothing, and positional members have no
    name to emit at all: the positions an array holds are not objects, and which position holds what
    is a nesting the object model does not carry (D29). A block none of whose lines is a readable
    member and which is neither an array nor a map of type-keyed entries is not a declaration this
    handler read: the parser is the acceptance gate, so it yields nothing at all - not even the name
    on its first line, which would otherwise let an ordinary sentence carrying an equals sign and a
    bracket mint an object.

    A block of one line whose right-hand side is a bare type is no member list at all: it is a type
    assignment (RFC 8610 section 3.1), and it declares its name. That name gets one `structure`
    object - the same kind an ABNF rule gets, because a named type is a declared structure and not a
    member of one - with `presence="unspecified"`, since an assignment states nothing about whether
    the type appears anywhere."""
    lines = block.splitlines()
    if len(lines) == 1 and (a := CDDL_ASSIGN_RE.match(_strip_comment(lines[0]).strip())):
        type_text, value_domain, size = _cddl_constraints(a.group("type"))
        return [TestObjectDraft(name=a.group("name"), kind="structure", presence="unspecified",
                                type=type_text or None, value_domain=value_domain, size=size,
                                source_quote=lines[0].strip())]
    head = CDDL_START_RE.match(lines[0].strip())
    if not head:
        return []
    out: list[TestObjectDraft] = []
    type_keyed = False
    for quote in _members(lines):
        stripped = _strip_comment(quote)
        m = CDDL_MEMBER_RE.match(stripped)
        if not m:
            type_keyed = type_keyed or bool(CDDL_TYPE_KEY_RE.match(stripped))
            continue
        occ = m.group("occ") or ""
        type_text, value_domain, size = _cddl_constraints(
            CDDL_GROUP_CHOICE_RE.sub("", m.group("type").strip()).strip())
        if size is None and occ and occ != "?":
            size = OCCURRENCE_TEXT.get(occ, occ)   # an occurrence indicator is a count constraint
        alts = [a.strip() for a in type_text.split("/") if a.strip()]
        if alts and all(CDDL_LITERAL_RE.fullmatch(a) for a in alts):
            value_domain = value_domain or " / ".join(alts)
            type_text = ""                 # the alternation is the value domain, not an encoding
        out.append(TestObjectDraft(name=(m.group("key") or m.group("vkey")).strip('"'), kind="field",
                                   presence="optional" if occ == "?" else "mandatory",
                                   type=type_text or None, value_domain=value_domain, size=size,
                                   relations=[f"member of {head.group('name')}"], source_quote=quote))
    if not (out or type_keyed or head.group("bracket") == "["):
        return []
    return [_declaration(head.group("name"), CDDL_CONSTRUCT[head.group("bracket")],
                         lines[0].strip())] + out


# --- ABNF (RFC 5234) -----------------------------------------------------------------------------

ABNF_RULE_RE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9-]*)\s*=/?\s*(?P<elements>\S.*)$")
# the acceptance gate: an element list is made of terminal values, rule names, repetitions,
# alternations and groups, and of nothing else
ABNF_ELEMENTS_RE = re.compile(r"^(?:\"[^\"]*\"|%[bdx][0-9A-Fa-f]+(?:[.-][0-9A-Fa-f]+)*|[A-Za-z][A-Za-z0-9-]*|\d+|\*|/|[()\[\]]|\s)+$")
ABNF_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
ABNF_QUOTED_RE = re.compile(r"\"[^\"]*\"")
ABNF_NUMERIC_RE = re.compile(r"%[bdx][0-9A-Fa-f]+(?:[.-][0-9A-Fa-f]+)*")
ABNF_OPERATOR_RE = re.compile(r"[*/()\[\]]")
# a terminal value, text or numeric (RFC 5234 sections 2.3 and 3.4): it states which values are
# allowed, so an element list made of nothing but terminals is a value domain
ABNF_TERMINAL_RE = re.compile(r"\"[^\"]*\"|%[bdx][0-9A-Fa-f]+(?:[.-][0-9A-Fa-f]+)*")
ABNF_RANGE_RE = re.compile(r"%[bdx][0-9A-Fa-f]+-[0-9A-Fa-f]+")
# RFC 5234 section 3.7, specific repetition: `<n>element` is exactly n occurrences. Searched after
# the terminals have been blanked out, so a digit inside a value is never read as a count.
ABNF_SPECIFIC_RE = re.compile(r"\d+(?=[A-Za-z(\[])")


def abnf_detect(text: str) -> list[str]:
    """One block holding every line of the text shaped like a rule: an optional group in one rule is
    what makes a rule defined elsewhere optional, and a bare reference is an element list only if the
    rule it names is declared here, so the rules have to be read together. Detection is the shape
    alone; `abnf_parse` is the acceptance gate."""
    lines = [line.strip() for line in text.splitlines() if ABNF_RULE_RE.match(line.strip())]
    return ["\n".join(lines)] if lines else []


def _bare_names(elements: str) -> list[str]:
    """The rule names an element list references: its words outside its text and numeric values."""
    return ABNF_NAME_RE.findall(ABNF_NUMERIC_RE.sub(" ", ABNF_QUOTED_RE.sub(" ", elements)))


def _balanced(elements: str) -> bool:
    depth = 0
    for ch in ABNF_QUOTED_RE.sub(" ", elements):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _abnf_rule(line: str, declared: set[str]) -> tuple[str, str] | None:
    """The rule a line declares, or None. A line passes only if its element list is one: made of
    nothing but the constructs of RFC 5234, with its groups and options closed, with at least one
    complete element in it, and either carrying a construct of the notation - a repetition variable
    or specific, an alternation, a group, a text value, a numeric value - or referencing rule names
    that this same text declares. Without a construct and without a declared reference, a sentence
    carrying an equals sign would be an element list of bare words, and a rule head of another
    notation an element list of one bracket."""
    m = ABNF_RULE_RE.match(line)
    if not m:
        return None
    elements = m.group("elements").strip()
    names = _bare_names(elements)
    terminal = ABNF_QUOTED_RE.search(elements) or ABNF_NUMERIC_RE.search(elements)
    if not ABNF_ELEMENTS_RE.match(elements) or not _balanced(elements):
        return None
    if not (names or terminal):
        return None
    if not (terminal or ABNF_OPERATOR_RE.search(elements)
            or ABNF_SPECIFIC_RE.search(ABNF_QUOTED_RE.sub(" ", ABNF_NUMERIC_RE.sub(" ", elements)))
            or all(n in declared for n in names)):
        return None
    return m.group("name"), elements


def abnf_parse(block: str) -> list[TestObjectDraft]:
    lines = [line.strip() for line in block.splitlines()]
    declared = {m.group("name") for line in lines if (m := ABNF_RULE_RE.match(line))}
    rules = [(*r, line) for line in lines if (r := _abnf_rule(line, declared))]
    required: set[str] = set()
    bracketed: set[str] = set()
    for _, elements, _quote in rules:
        outside = _strip_innermost(elements, r"\[[^\[\]]*\]")
        required |= set(_bare_names(outside))
        bracketed |= set(_bare_names(elements))
    out: list[TestObjectDraft] = []
    for name, elements, quote in rules:
        presence = "mandatory" if name in required else ("optional" if name in bracketed else "unspecified")
        alts = [a.strip() for a in elements.split("/") if a.strip()]
        value_domain = " / ".join(alts) if alts and all(ABNF_TERMINAL_RE.fullmatch(a) for a in alts) else None
        bare = ABNF_QUOTED_RE.sub(" ", ABNF_NUMERIC_RE.sub(" ", elements))
        # a repetition bounds how many occurrences the rule holds, and the two endpoints of a value
        # range bound which values it may take: each is a number to probe at
        size = next((m.group(0) for m in (REPEAT_RE.search(elements), ABNF_SPECIFIC_RE.search(bare),
                                          ABNF_RANGE_RE.search(elements)) if m), None)
        out.append(TestObjectDraft(name=name, kind="structure", presence=presence, type=elements,
                                   value_domain=value_domain, size=size, source_quote=quote))
    return out


# --- JSON Schema ---------------------------------------------------------------------------------

JSON_START_RE = re.compile(r"^\{")
# a bound that a boundary case can be probed at: a length, a count, or the two ends of a numeric
# range, which bounds the value and is therefore in both lists
JSON_SIZE_KEYS = ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems",
                  "minProperties", "maxProperties")
# the assertions that restrict which values are valid rather than how long the instance is
JSON_VALUE_KEYS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf")


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


def _json_type(schema: dict) -> str | None:
    """A schema's declared type: the `type` keyword of the validation vocabulary, narrowed by
    `format` where it carries one. The root schema declares its own the same way a property does."""
    kinds = schema.get("type")
    kinds = " / ".join(kinds) if isinstance(kinds, list) else kinds
    fmt = schema.get("format")
    return (f"{kinds} ({fmt})" if kinds and fmt else kinds or fmt) or None


def json_schema_parse(block: str) -> list[TestObjectDraft]:
    doc = _json_object(block)
    if doc is None:
        return []
    lines = [line.strip() for line in block.splitlines()]
    required = doc.get("required") if isinstance(doc.get("required"), list) else []
    # `$id` is the only name the notation gives a schema, so it is the only thing the merge can key
    # on to tell two schemas of one clause apart. A schema without one stays anonymous.
    schema_id = doc["$id"] if isinstance(doc.get("$id"), str) and doc["$id"] else None
    out: list[TestObjectDraft] = []
    if schema_id:
        # the declaration object of this notation: `$id` is its only name, so a schema without one
        # declares no name and gets none invented for it
        quote = next((l for l in lines if re.match(r"^\s*\"\$id\"\s*:", l)), lines[0])
        out.append(_declaration(schema_id, _json_type(doc), quote))
    for name, schema in doc["properties"].items():
        if not isinstance(schema, dict) or not name:
            continue
        declared = re.compile(r"^\s*\"" + re.escape(name) + r"\"\s*:")
        quote = next((l for l in lines if declared.match(l)), None) or next((l for l in lines if f'"{name}"' in l), lines[0])
        value_domain = None
        if isinstance(schema.get("enum"), list):
            value_domain = " / ".join(_json_text(v) for v in schema["enum"])
        elif "const" in schema:
            value_domain = _json_text(schema["const"])
        elif isinstance(schema.get("pattern"), str):
            value_domain = schema["pattern"]
        else:
            value_domain = ", ".join(f"{k} {_json_text(schema[k])}" for k in JSON_VALUE_KEYS if k in schema)
        size = ", ".join(f"{k} {_json_text(schema[k])}" for k in JSON_SIZE_KEYS if k in schema)
        out.append(TestObjectDraft(name=name, kind="field",
                                   presence="mandatory" if name in required else "optional",
                                   type=_json_type(schema),
                                   value_domain=value_domain or None, size=size or None,
                                   relations=[f"member of {schema_id}"] if schema_id else [],
                                   source_quote=quote))
    return out


# --- ASN.1 (ITU-T X.680) -------------------------------------------------------------------------

ASN1_START_RE = re.compile(r"^(?P<name>[A-Z][\w-]*)\s*::=\s*(?P<construct>SEQUENCE|SET|CHOICE)\s*\{")
ASN1_MEMBER_RE = re.compile(r"^(?P<field>[a-z][\w-]*)\s+(?P<rest>[A-Z].*)$")
ASN1_SIZE_RE = re.compile(r"SIZE\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
ASN1_NAMED_RE = re.compile(r"\{([^{}]*)\}")
# X.680 clause 51: a permitted-alphabet constraint and a pattern constraint each restrict which
# values are valid. The pattern is matched first because its regular expression may itself carry
# braces, which the named-number list would otherwise read as a list of named values.
ASN1_PATTERN_RE = re.compile(r"PATTERN\s*\"[^\"]*\"")
ASN1_FROM_RE = re.compile(r"FROM\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
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
        if pattern := ASN1_PATTERN_RE.search(rest):
            value_domain = " ".join(pattern.group(0).split())
            rest = rest[:pattern.start()] + " " + rest[pattern.end():]
        if named := ASN1_NAMED_RE.search(rest):
            value_domain = value_domain or " ".join(named.group(1).split()) or None
            rest = rest[:named.start()] + " " + rest[named.end():]
        if alphabet := ASN1_FROM_RE.search(rest):
            value_domain = value_domain or " ".join(alphabet.group(0).split())
        size = None
        if ms := ASN1_SIZE_RE.search(rest):       # a length constraint, never a domain of values
            size = " ".join(ms.group(1).split())
        elif (mr := RANGE_RE.search(rest)) and not alphabet:
            # a value range is both the domain to violate and the pair of bounds to probe
            size = f"{mr.group(1)}..{mr.group(2)}"
            value_domain = value_domain or size
        rest = ASN1_TAIL_RE.sub("", _strip_innermost(rest, r"\([^()]*\)"))
        out.append(TestObjectDraft(name=m.group("field"), kind="field",
                                   presence="optional" if optional else "mandatory",
                                   type=" ".join(rest.split()) or None, value_domain=value_domain, size=size,
                                   relations=[f"member of {head.group('name')}"], source_quote=quote))
    if not out:                 # the parser read no member of it, so it read no declaration either
        return []
    # X.680 clauses 25, 27 and 29: the keyword after `::=` is the type the name denotes, kept as the
    # notation writes it
    return [_declaration(head.group("name"), head.group("construct"), lines[0].strip())] + out


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
