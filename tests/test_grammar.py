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
    _draft(name="name", type="UTF8String", size="1..64", source_quote="name UTF8String (SIZE(1..64)),"),
    _draft(name="state", type="INTEGER", value_domain="idle(0), busy(1)",
           source_quote="state INTEGER { idle(0), busy(1) },"),
    _draft(name="note", presence="optional", type="UTF8String", source_quote="note UTF8String OPTIONAL"),
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


@pytest.mark.parametrize("name", ["sample.md", "sample.html", "sample.docx", "sample.pdf"])
def test_fixture_declarations_are_harvested_from_every_format(name):
    """The blocks must survive each reader intact and in order, or block detection fails on them."""
    clause = next(c for c in ingest(str(FIX / name)) if c.id == "5.5")
    assert [d.name for d in harvest(clause)] == [n for members in FIXTURE_MEMBERS.values() for n in members]
