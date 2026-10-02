"""Parse a test-specification document set into structured test cases, for use as evaluation ground
truth. Expects each test case to be a block of labelled fields (Test case ID, Purpose, Test scenario,
Expected results, ...), which is how the ISO/IEC TS 18013-6 appendices are written.

Usage: parse_appendices.py <directory of PDFs> <output json>
"""
import collections, glob, json, re, sys

import pymupdf as fitz

FIELDS = ["Test case ID", "System under test", "Purpose", "Reference", "Technology", "Profile",
          "Preconditions", "Test scenario", "Expected results"]
HEADER_RE = re.compile(r"^(ISO/IEC TS 18013-6:2025\(E\)|© ISO 2025 – All rights reserved|\d{1,3})\s*$")
START_RE = re.compile(r"^(\d+(?:\.\d+)*)\s*(?:\n)?Test case (\S+)\s*$", re.M)
CLAUSE_RE = re.compile(r"ISO/IEC 18013-5:2021,\s*([A-Z]?\d+(?:\.\d+)*)")

def clean_pages(doc):
    out = []
    for p in doc:
        lines = [l.rstrip() for l in p.get_text().splitlines()]
        lines = [l for l in lines if not HEADER_RE.match(l.strip())]
        out.append("\n".join(lines))
    return "\n".join(out)

def parse(path, appendix):
    text = clean_pages(fitz.open(path))
    # split at "Test case ID" labels; the test case id follows on the next line
    chunks = re.split(r"\nTest case ID\s*\n", text)
    cases = []
    for ch in chunks[1:]:
        fields = {}
        cur = "Test case ID"; buf = []
        for line in ch.splitlines():
            s = line.strip()
            if s in FIELDS[1:]:
                fields[cur] = "\n".join(buf).strip(); cur = s; buf = []
            elif cur == "Expected results" and re.match(r"^\d+(\.\d+)+\s*$", s) or (cur == "Expected results" and s.startswith("Test case ") and "ID" not in s):
                break   # next numbered heading / next test case title
            else:
                buf.append(line)
        fields[cur] = "\n".join(buf).strip()
        tid = fields.get("Test case ID", "").split("\n")[0].strip()
        if not tid:
            continue
        refs = CLAUSE_RE.findall(fields.get("Reference", ""))
        cases.append({"id": tid, "appendix": appendix, "sut": fields.get("System under test", ""),
                      "purpose": " ".join(fields.get("Purpose", "").split()),
                      "reference": fields.get("Reference", ""), "clauses_18013_5": refs,
                      "technology": fields.get("Technology", ""), "profile": fields.get("Profile", ""),
                      "preconditions": fields.get("Preconditions", ""),
                      "scenario": fields.get("Test scenario", ""), "expected": fields.get("Expected results", "")})
    return cases

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out_path = sys.argv[1], sys.argv[2]
    allc = []
    for n, f in enumerate(sorted(glob.glob(f"{src}/*.pdf")), 1):
        cs = parse(f, n); allc.extend(cs)
        with_ref = sum(1 for c in cs if c["clauses_18013_5"])
        print(f"Appendix {n}: {len(cs)} test cases, {with_ref} reference an 18013-5 clause, ids unique={len({c['id'] for c in cs})==len(cs)}")
    json.dump(allc, open(out_path, "w"), indent=1, ensure_ascii=False)
    clauses = collections.Counter(c for tc in allc for c in tc["clauses_18013_5"])
    print("total", len(allc), "| distinct 18013-5 clauses referenced:", len(clauses))
    print("top clauses:", clauses.most_common(12))
    empt = [c["id"] for c in allc if not c["scenario"] or not c["expected"]]
    print("cases missing scenario/expected:", len(empt), empt[:5])
