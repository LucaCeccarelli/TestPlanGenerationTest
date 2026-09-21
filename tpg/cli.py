"""tpg generate <standard> [--out plan.json] [--format json|yaml] [--model M] [--clauses 5.1,5.2]"""
import argparse
import os
import sys

from tpg.emit import write_plan
from tpg.llm import LLMError, OllamaLLM, load_dotenv
from tpg.pipeline import run

DEFAULT_MODEL = "gemma4:31b"


def _err(msg: str) -> None:
    print(f"tpg: {msg}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tpg", description="Generate ISO 29119-3 test cases from a technical standard.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="generate a test plan from one standard")
    g.add_argument("standard", help="PDF, DOCX, Markdown, HTML or text file")
    g.add_argument("--out", default="plan.json")
    g.add_argument("--format", choices=["json", "yaml"], default="json")
    g.add_argument("--model", default=DEFAULT_MODEL)
    g.add_argument("--clauses", help="comma-separated clause ids to restrict the run, e.g. 5.1,5.2")
    g.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args(argv)

    load_dotenv()
    if not os.path.isfile(args.standard):
        _err(f"cannot read {args.standard}")
        return 1
    llm = OllamaLLM(model=args.model)
    try:
        llm.check()
    except LLMError as e:
        _err(str(e))
        return 1
    clause_ids = [c.strip() for c in args.clauses.split(",") if c.strip()] if args.clauses else None
    try:
        plan = run(args.standard, llm, args.model, clause_ids=clause_ids, attempts=args.attempts,
                   log=lambda s: print(s, file=sys.stderr))
    except ValueError as e:
        _err(str(e))
        return 1
    write_plan(plan, args.out, args.format)
    _err(f"wrote {args.out}: {len(plan.requirements)} requirements, {len(plan.test_cases)} test cases, {len(plan.gaps)} gaps")
    return 2 if plan.gaps else 0


if __name__ == "__main__":
    sys.exit(main())
