"""The grammar stage: four notation handlers, no LLM. Fixture data only; nothing here is a real standard."""
from pathlib import Path

import pytest

from tpg.extract import norm
from tpg.grammar import HANDLERS, harvest
from tpg.ingest import ingest
from tpg.model import check_object
from tpg.models import Clause

FIX = Path(__file__).parent / "fixtures"


def _draft(**kw) -> dict:
    """An expected draft: the model's defaults with the stated fields overridden."""
    base = {"kind": "field", "direction": "internal", "presence": "mandatory", "condition": None, "type": None,
            "value_domain": None, "size": None, "relations": [], "applies_when": []}
    return {**base, **kw}


def _run(notation: str, text: str) -> list[dict]:
    detect, parse = HANDLERS[notation]
    return [d.model_dump() for block in detect(text) for d in parse(block)]


CDDL = """record = {
  label: tstr .size (1..32),
  ? count: uint,
  mode: "fast" / "slow",
}"""
CDDL_EXPECTED = [
    _draft(name="label", type="tstr", size="1..32", relations=["member of record"],
           source_quote="label: tstr .size (1..32),"),
    _draft(name="count", presence="optional", type="uint", relations=["member of record"],
           source_quote="? count: uint,"),
    _draft(name="mode", value_domain='"fast" / "slow"', relations=["member of record"],
           source_quote='mode: "fast" / "slow",'),
]

ABNF = '''token = prefix 1*8ALPHA [ suffix ]
prefix = "x" / "y"
suffix = "-a" / "-b"'''
ABNF_EXPECTED = [
    _draft(name="token", kind="structure", presence="unspecified", type="prefix 1*8ALPHA [ suffix ]", size="1*8",
           source_quote="token = prefix 1*8ALPHA [ suffix ]"),
    _draft(name="prefix", kind="structure", type='"x" / "y"', value_domain='"x" / "y"',
           source_quote='prefix = "x" / "y"'),
    _draft(name="suffix", kind="structure", presence="optional", type='"-a" / "-b"', value_domain='"-a" / "-b"',
           source_quote='suffix = "-a" / "-b"'),
]

JSON_SCHEMA = """{
  "type": "object",
  "required": ["key"],
  "properties": {
    "key": {"type": "string", "minLength": 4, "maxLength": 16},
    "flag": {"type": "string", "enum": ["on", "off"]}
  }
}"""
JSON_SCHEMA_EXPECTED = [
    _draft(name="key", type="string", size="minLength 4, maxLength 16",
           source_quote='"key": {"type": "string", "minLength": 4, "maxLength": 16},'),
    _draft(name="flag", presence="optional", type="string", value_domain="on / off",
           source_quote='"flag": {"type": "string", "enum": ["on", "off"]}'),
]

ASN1 = """Entry ::= SEQUENCE {
  name UTF8String (SIZE(1..64)),
  state INTEGER { idle(0), busy(1) },
  note UTF8String OPTIONAL
}"""
ASN1_EXPECTED = [
    _draft(name="name", type="UTF8String", size="1..64", relations=["member of Entry"],
           source_quote="name UTF8String (SIZE(1..64)),"),
    _draft(name="state", type="INTEGER", value_domain="idle(0), busy(1)", relations=["member of Entry"],
           source_quote="state INTEGER { idle(0), busy(1) },"),
    _draft(name="note", presence="optional", type="UTF8String", relations=["member of Entry"],
           source_quote="note UTF8String OPTIONAL"),
]

WELL_FORMED = [("cddl", CDDL, CDDL_EXPECTED), ("abnf", ABNF, ABNF_EXPECTED),
               ("json_schema", JSON_SCHEMA, JSON_SCHEMA_EXPECTED), ("asn1", ASN1, ASN1_EXPECTED)]


@pytest.mark.parametrize("notation,text,expected", WELL_FORMED, ids=[c[0] for c in WELL_FORMED])
def test_handler_reads_presence_size_and_value_list(notation, text, expected):
    assert _run(notation, text) == expected


MALFORMED = [
    ("cddl", "record = {\n  label: tstr"),                     # the declaration is never closed
    ("cddl", "record = {\n  nothing that is a member line\n}"),
    ("abnf", 'token = "unterminated'),                         # not an element list
    ("abnf", "The device = behaves oddly."),                   # prose that happens to carry an equals sign
    ("json_schema", '{"properties": {"key": }}'),              # balanced braces, not JSON
    ("json_schema", '{"type": "object"}'),                     # JSON, but declares no properties
    ("asn1", "Entry ::= SEQUENCE {\n  name UTF8String"),       # the declaration is never closed
    ("asn1", "Entry ::= SEQUENCE {\n  0 not-a-field\n}"),
]


@pytest.mark.parametrize("notation,text", MALFORMED, ids=[f"{n}-{i}" for i, (n, _) in enumerate(MALFORMED)])
def test_malformed_block_yields_nothing_and_raises_nothing(notation, text):
    assert _run(notation, text) == []


NESTED = [
    ("cddl", "outer = {\n  inner: {\n    a: int,\n  },\n  b: tstr,\n}", ["b"]),
    ("asn1", "Nest ::= SEQUENCE {\n  one SEQUENCE {\n    deep INTEGER\n  },\n  two BOOLEAN\n}", ["two"]),
]


@pytest.mark.parametrize("notation,text,expected", NESTED, ids=[c[0] for c in NESTED])
def test_a_nested_group_yields_no_member_of_the_enclosing_declaration(notation, text, expected):
    """A nested member belongs to the nested group; attributing it to the enclosing rule would be false."""
    assert [d["name"] for d in _run(notation, text)] == expected


def test_other_notations_do_not_fire_on_a_block():
    """Each block is read by its own handler only; a handler that cannot parse a block yields nothing."""
    for notation, text, _ in WELL_FORMED:
        for other, _, _ in WELL_FORMED:
            if other != notation:
                assert _run(other, text) == [], f"{other} fired on the {notation} block"


def test_harvest_without_a_formal_block_returns_nothing():
    assert harvest(Clause(id="1", title="Scope", text="This document describes the sample device.")) == []


def test_harvest_deduplicates_by_name_and_quote():
    clause = Clause(id="9", title="Twice", text=CDDL + "\n" + CDDL)
    assert [d.name for d in harvest(clause)] == ["label", "count", "mode"]


FIXTURE_MEMBERS = {
    "cddl": ["label", "count", "mode"],
    "abnf": ["token", "prefix", "suffix"],
    "json_schema": ["key", "flag"],
    "asn1": ["name", "state", "note"],
}


@pytest.fixture(scope="module")
def clause_55() -> Clause:
    return next(c for c in ingest(str(FIX / "sample.md")) if c.id == "5.5")


def test_harvest_reads_all_four_notations_of_the_fixture_clause(clause_55):
    names = [d.name for d in harvest(clause_55)]
    assert names == [n for members in FIXTURE_MEMBERS.values() for n in members]


@pytest.mark.parametrize("notation", list(FIXTURE_MEMBERS))
def test_fixture_clause_member_inventory_per_notation(notation, clause_55):
    assert [d.name for d in _run_drafts(notation, clause_55.text)] == FIXTURE_MEMBERS[notation]


def _run_drafts(notation: str, text: str):
    detect, parse = HANDLERS[notation]
    return [d for block in detect(text) for d in parse(block)]


def test_every_quote_is_a_verbatim_line_of_the_clause(clause_55):
    drafts = harvest(clause_55)
    assert drafts
    for n, d in enumerate(drafts, 1):
        assert check_object(clause_55, n, d) is None
        assert norm(d.source_quote) in {norm(line) for line in clause_55.text.splitlines()}


def _fixture_dumps(name: str) -> list[dict]:
    clause = next(c for c in ingest(str(FIX / name)) if c.id == "5.5")
    return [{**d.model_dump(), "source_quote": norm(d.source_quote)} for d in harvest(clause)]


@pytest.mark.parametrize("name", ["sample.html", "sample.docx", "sample.pdf"])
def test_fixture_declarations_are_harvested_from_every_format(name):
    """Every attribute, not only the names, must survive each reader, or a handler read the layout."""
    assert _fixture_dumps(name) == _fixture_dumps("sample.md")


CLOSING_LINE = [
    ("asn1", "Pair ::= SEQUENCE {\n  one INTEGER,\n  two BOOLEAN }", ["one", "two"]),
    ("cddl", "pair = {\n  one: int,\n  two: tstr }", ["one", "two"]),
]


@pytest.mark.parametrize("notation,text,expected", CLOSING_LINE, ids=[c[0] for c in CLOSING_LINE])
def test_a_member_sharing_its_line_with_the_closing_bracket_is_read(notation, text, expected):
    """A declaration may close on its last member's line; that member is still a member."""
    assert [d["name"] for d in _run(notation, text)] == expected


def test_a_member_sharing_its_line_with_the_closing_bracket_keeps_its_type():
    assert _run("asn1", CLOSING_LINE[0][1])[1] == _draft(name="two", type="BOOLEAN",
                                                         relations=["member of Pair"], source_quote="two BOOLEAN")


ABNF_REJECTED = [
    "DeviceType = [",                      # a rule head of another notation: the element list does not close
    "Group = a )",                         # a closer with no opener
    "Repeat = *",                          # a repetition of nothing: no complete element
    "x = the device is ready",             # prose: no operator, no literal, no numeric, no declared word
]


@pytest.mark.parametrize("text", ABNF_REJECTED, ids=[t.split(" =")[0] for t in ABNF_REJECTED])
def test_abnf_rejects_an_element_list_that_is_not_one(text):
    assert _run("abnf", text) == []


def test_abnf_accepts_a_bare_reference_to_a_rule_declared_in_the_same_clause():
    assert [d["name"] for d in _run("abnf", "alias = target\ntarget = %x41")] == ["alias", "target"]


CDDL_COMMENT = """record = {
  label: tstr,            ; the label as issued
  ? count: uint .size 2,  ; how many
}"""


def test_a_cddl_comment_does_not_reach_the_type():
    got = _run("cddl", CDDL_COMMENT)
    assert [(d["name"], d["type"], d["size"]) for d in got] == [("label", "tstr", None), ("count", "uint", "2")]
    assert got[0]["source_quote"] == "label: tstr,            ; the label as issued"


def test_a_semicolon_inside_a_cddl_literal_is_not_a_comment():
    assert _run("cddl", 'r = {\n  mode: "a;b",\n}')[0]["value_domain"] == '"a;b"'


def test_a_positional_cddl_array_yields_the_structure_itself():
    """Positional members have no names to emit, so the declaration is kept as one structure object."""
    assert _run("cddl", "pair = [\n  tstr,\n  int,\n]") == [
        _draft(name="pair", kind="structure", presence="unspecified", source_quote="pair = [")]


def test_an_occurrence_marker_without_a_number_is_written_as_text():
    """A bare marker is no limit to test; a boundary item built on it would read as nonsense."""
    got = _run("cddl", "r = {\n  * extra: tstr,\n  + more: int,\n  2*8 some: uint,\n}")
    assert [d["size"] for d in got] == ["any number of occurrences", "one or more occurrences", "2*8"]


def test_only_the_bracket_that_closes_the_declaration_is_stripped_from_a_member():
    """The member's own constraint ends in a bracket too; cutting that one would break its type."""
    got = _run("asn1", "One ::= SEQUENCE {\n  name UTF8String (SIZE(1..64)) }")
    assert got == [_draft(name="name", type="UTF8String", size="1..64", relations=["member of One"],
                          source_quote="name UTF8String (SIZE(1..64))")]


def test_an_asn1_member_records_the_type_it_belongs_to():
    """Two structures of one clause may declare the same member name; the merge tells them apart by
    the declaration the handler names here."""
    text = "One ::= SEQUENCE {\n  item INTEGER\n}\nTwo ::= SEQUENCE {\n  item BOOLEAN\n}"
    assert [(d["name"], d["type"], d["relations"]) for d in _run("asn1", text)] == [
        ("item", "INTEGER", ["member of One"]), ("item", "BOOLEAN", ["member of Two"])]


# --- constraint harvesting per notation: value domains and sizes ---------------------------------

CDDL_VALUE_CONTROLS = [
    ("uint .lt 10", "less than 10"),
    ("uint .le 9", "at most 9"),
    ("uint .gt 3", "greater than 3"),
    ("uint .ge 1", "at least 1"),
    ("uint .eq 5", "equal to 5"),
    ("uint .ne 0", "not equal to 0"),
    ('tstr .regexp "[0-9]+"', 'matching "[0-9]+"'),
    ("uint .bits flags", "bits set within flags"),
]


@pytest.mark.parametrize("type_text,expected", CDDL_VALUE_CONTROLS, ids=[t.split()[1] for t, _ in CDDL_VALUE_CONTROLS])
def test_a_cddl_value_control_operator_becomes_the_value_domain(type_text, expected):
    """RFC 8610 section 3.8.2 and 3.8.3: these operators bound the value, not the encoded length."""
    got = _run("cddl", "r = {\n  item: %s,\n}" % type_text)
    assert [(d["value_domain"], d["size"], d["type"]) for d in got] == [(expected, None, type_text.split()[0])]


def test_a_cddl_size_control_is_a_size_and_not_a_value_domain():
    """RFC 8610 section 3.8.1: `.size` bounds the encoded length, so it states no domain of values."""
    got = _run("cddl", "r = {\n  item: bstr .size (4..8),\n}")
    assert [(d["value_domain"], d["size"]) for d in got] == [(None, "4..8")]


def test_a_bare_cddl_range_is_both_a_value_domain_and_a_size():
    """RFC 8610 section 2.2.2: a range is a range of values, so it is a domain to violate and a pair
    of bounds to probe at the same time."""
    got = _run("cddl", "r = {\n  item: 1..32,\n}")
    assert [(d["value_domain"], d["size"], d["type"]) for d in got] == [("1..32", "1..32", None)]


def test_a_bounded_occurrence_inside_a_cddl_type_becomes_a_size():
    got = _run("cddl", "r = {\n  item: [2*4 tstr],\n}")
    assert [(d["size"], d["type"]) for d in got] == [("2*4", "[2*4 tstr]")]


def test_a_cddl_group_choice_marker_does_not_reach_the_type():
    """RFC 8610 section 2.2.2: `//` separates the branches of a group choice; it is not part of a type."""
    got = _run("cddl", "r = {\n  one: tstr, //\n  two: uint\n}")
    assert [(d["name"], d["type"]) for d in got] == [("one", "tstr"), ("two", "uint")]


CDDL_SINGLE = """Outer = {
  "inner" : Inner
}
Inner = tstr
Bounded = bstr .size 32
Tagged = #6.24(bstr .cbor Inner)"""


def test_a_single_line_cddl_rule_declares_a_named_type():
    """RFC 8610 section 3.1: a rule whose right-hand side is a bare type assigns that type to the
    name. It declares the name, so it yields one object; nothing states whether it must appear."""
    assert _run("cddl", CDDL_SINGLE)[1:] == [
        _draft(name="Inner", kind="structure", presence="unspecified", type="tstr",
               source_quote="Inner = tstr"),
        _draft(name="Bounded", kind="structure", presence="unspecified", type="bstr", size="32",
               source_quote="Bounded = bstr .size 32"),
        _draft(name="Tagged", kind="structure", presence="unspecified", type="#6.24(bstr .cbor Inner)",
               source_quote="Tagged = #6.24(bstr .cbor Inner)"),
    ]


CDDL_NOT_A_RULE = [
    "The device = ready",                    # two bare words: prose, not a type
    "Note that quality = reliability.",      # a sentence
    "Outer = {",                             # a block head, read as a block
    'Mode = "fast" / "slow"',                # an alternation, which the ABNF handler reads
]


@pytest.mark.parametrize("line", CDDL_NOT_A_RULE, ids=[l.split(" =")[0][:12] for l in CDDL_NOT_A_RULE])
def test_a_line_that_is_not_a_cddl_type_assignment_yields_no_object(line):
    assert [d["name"] for d in _run("cddl", CDDL_SINGLE + "\n" + line)] == ["inner", "Inner", "Bounded", "Tagged"]


def test_a_single_line_cddl_rule_needs_the_notation_in_evidence():
    """A bare `name = type` line is a shape a sentence can take too, so it is only read where the
    text independently shows CDDL: at least one bracketed declaration."""
    assert _run("cddl", "Inner = tstr\nBounded = bstr .size 32") == []


def test_a_type_keyed_cddl_entry_yields_no_field():
    """RFC 8610 section 3.5.1: the key before `=>` is a type, so it names no field of the map."""
    assert [d["name"] for d in _run("cddl", "r = {\n  * tstr => any,\n  \"named\" => uint,\n}")] == ["named"]


def test_a_map_of_only_type_keyed_entries_yields_the_structure_itself():
    """The entries name no field, but the declaration still declares the map, so it is not lost."""
    assert _run("cddl", "Index = {\n  + tstr => any\n}") == [
        _draft(name="Index", kind="structure", presence="unspecified", source_quote="Index = {")]


def test_abnf_numeric_value_alternatives_are_a_value_domain():
    """RFC 5234 section 2.3: a numeric terminal is a value, so an alternation of them is a domain."""
    got = _run("abnf", "flag = %x41 / %x42\nalso = %d13.10")
    assert [(d["name"], d["value_domain"]) for d in got] == [("flag", "%x41 / %x42"), ("also", "%d13.10")]


def test_an_abnf_value_range_is_a_value_domain_and_a_size():
    """RFC 5234 section 3.4: a value range alternative states which values are allowed and its two
    endpoints are the bounds to probe."""
    got = _run("abnf", "digit = %x30-39")
    assert [(d["value_domain"], d["size"]) for d in got] == [("%x30-39", "%x30-39")]


def test_an_abnf_specific_repetition_is_a_size():
    """RFC 5234 section 3.7: `<n>element` is exactly n occurrences, which is a count to probe."""
    assert [d["size"] for d in _run("abnf", "year = 4DIGIT\nmix = 1*8ALPHA\nver = \"1.0\"")] == ["4", "1*8", None]


JSON_BOUNDS = """{
  "$id": "https://example.invalid/schema",
  "properties": {
    "amount": {"type": "integer", "minimum": 1, "maximum": 99, "multipleOf": 3},
    "ratio": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
    "bag": {"type": "object", "minProperties": 1, "maxProperties": 4}
  }
}"""


def test_json_schema_numeric_bounds_are_a_value_domain():
    got = {d["name"]: d["value_domain"] for d in _run("json_schema", JSON_BOUNDS)}
    assert got == {"amount": "minimum 1, maximum 99, multipleOf 3",
                   "ratio": "exclusiveMinimum 0, exclusiveMaximum 1", "bag": None}


def test_json_schema_counts_are_a_size():
    got = {d["name"]: d["size"] for d in _run("json_schema", JSON_BOUNDS)}
    assert got == {"amount": "minimum 1, maximum 99", "ratio": None, "bag": "minProperties 1, maxProperties 4"}


def test_json_schema_keys_the_merge_on_the_schema_id():
    """A schema has no declaration name in the notation except `$id`, which identifies the schema."""
    assert [d["relations"] for d in _run("json_schema", JSON_BOUNDS)] == \
        [["member of https://example.invalid/schema"]] * 3


ASN1_CONSTRAINED = """Spec ::= SEQUENCE {
  alpha PrintableString (FROM ("0".."9")),
  shape PrintableString (PATTERN "[0-9]{4}"),
  count INTEGER (1..100)
}"""


def test_asn1_value_constraints_become_the_value_domain():
    """X.680 clause 51: a permitted-alphabet, a pattern and a value range each bound the value; only
    the range is also a pair of bounds to probe, and SIZE is a length, never a value."""
    got = [(d["name"], d["type"], d["value_domain"], d["size"]) for d in _run("asn1", ASN1_CONSTRAINED)]
    assert got == [("alpha", "PrintableString", 'FROM ("0".."9")', None),
                   ("shape", "PrintableString", 'PATTERN "[0-9]{4}"', None),
                   ("count", "INTEGER", "1..100", "1..100")]


MIXED = '''Rec = {
  age: 1..120,
  score: uint .lt 100,
  hex: bstr .size (4..8),
}
Cap = uint .ge 1
digit = %x30-39
{
  "properties": {"amount": {"type": "integer", "minimum": 1, "maximum": 99}}
}
Spec ::= SEQUENCE {
  count INTEGER (1..100)
}'''


def test_every_notation_can_state_a_value_domain_and_a_numeric_size():
    """The two preconditions the derivation ladder gates its `value_invalid` and `boundary_outside`
    items on: a `value_domain`, and a `size` carrying a digit. Each notation must be able to supply
    both out of its own constraint syntax, or those two rungs can never fire."""
    drafts = harvest(Clause(id="x", title="Declarations", text=MIXED))
    assert {d.name for d in drafts if d.value_domain} == {"age", "score", "Cap", "digit", "amount", "count"}
    assert {d.name for d in drafts if d.size and any(c.isdigit() for c in d.size)} == \
        {"age", "hex", "digit", "amount", "count"}
