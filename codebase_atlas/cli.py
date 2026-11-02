"""Command line interface: `atlas <command> <repo> ...`."""
import argparse
import json
import os
import sys
from dataclasses import asdict

from . import __version__
from .analysis.dataflow import data_flow
from .analysis.drift import compare_snapshots, make_snapshot, validate_snapshot
from .analysis.impact import analyze_impact
from .analysis.issues import find_issues
from .analysis.reading_order import reading_order
from .analysis.summaries import module_details
from .atlas import build_atlas
from .llm import llm_label, module_payload, question_payload, run_llm
from .report import text
from .report.html import render_html
from .retrieval import ask


def _add_repo(parser):
    parser.add_argument("repo", help="path to the repository to analyse")
    parser.add_argument("--exclude", action="append", default=[], metavar="DIR",
                        help="extra directory name to skip (repeatable)")
    parser.add_argument("--verbose", action="store_true", help="list skipped files")


def build_parser():
    parser = argparse.ArgumentParser(prog="atlas", description="Codebase onboarding intelligence (offline, no model required).")
    parser.add_argument("--version", action="version", version=f"codebase-atlas {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("map", help="print the architecture map")
    _add_repo(p)
    p.add_argument("--module", help="show details for one module path")
    p.add_argument("--json", action="store_true", help="print the map as JSON")
    p.add_argument("--llm-command", help="optional: enrich module summaries via an external command")

    p = sub.add_parser("ask", help="grounded Q&A with file:line citations")
    _add_repo(p)
    p.add_argument("question")
    p.add_argument("--limit", type=int, default=8, help="max evidence locations")
    p.add_argument("--json", action="store_true")
    p.add_argument("--llm-command", help="optional: pass question + evidence to an external command")

    p = sub.add_parser("impact", help="what depends on a file or symbol")
    _add_repo(p)
    p.add_argument("target", help="file path, module name, or symbol name")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("issues", help="ranked good-first-issues")
    _add_repo(p)
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("snapshot", help="write the map as JSON for drift detection")
    _add_repo(p)
    p.add_argument("-o", "--output", required=True, help="output JSON path ('-' for stdout)")

    p = sub.add_parser("drift", help="compare the repo against a snapshot")
    _add_repo(p)
    p.add_argument("--against", required=True, help="snapshot JSON from `atlas snapshot`")
    p.add_argument("--json", action="store_true")
    p.add_argument("--exit-code", action="store_true", help="exit with status 1 when drift is found")

    p = sub.add_parser("html", help="write the interactive offline HTML map")
    _add_repo(p)
    p.add_argument("-o", "--output", required=True, help="output HTML path")
    return parser


def _emit_json(data, out):
    out.write(json.dumps(data, indent=2, default=list) + "\n")



def cmd_map(args, atlas, out, err):
    if args.module:
        path = args.module.strip().lstrip("./")
        if path not in atlas.modules:
            err.write(f"atlas: no module {args.module!r} in this repo\n")
            return 2
        details = module_details(atlas, path)
        if args.json:
            _emit_json(details, out)
            return 0
        out.write(text.format_module(details) + "\n")
        _enrich_modules(args, atlas, [path], out, err)
        return 0
    steps = reading_order(atlas)
    flow = data_flow(atlas)
    if args.json:
        _emit_json({
            "repo": atlas.name,
            "modules": [module_details(atlas, p) for p in sorted(atlas.modules)],
            "edges": [{"src": e.src, "dst": e.dst, "reasons": e.reason_list(),
                       "import_lines": e.import_lines, "uses": [asdict(u) for u in e.uses]}
                      for e in atlas.graph.sorted_edges()],
            "reading_order": [asdict(s) for s in steps],
            "data_flow": asdict(flow),
            "warnings": atlas.warnings,
        }, out)
        return 0
    out.write(text.format_map(atlas, flow, steps, args.verbose) + "\n")
    _enrich_modules(args, atlas, sorted(atlas.modules), out, err)
    return 0


def _enrich_modules(args, atlas, paths, out, err):
    if not args.llm_command:
        return
    out.write("\n" + llm_label(args.llm_command) + "\n")
    for path in paths:
        enriched, error = run_llm(args.llm_command, module_payload(module_details(atlas, path)))
        if error:
            err.write(f"atlas: {error}\n")
            return
        out.write(f"  {path}: {enriched}\n")


def cmd_ask(args, atlas, out, err):
    answer = ask(atlas, args.question, args.limit)
    if args.json:
        _emit_json(asdict(answer), out)
        return 0 if answer.supported else 3
    out.write(text.format_answer(answer) + "\n")
    if answer.supported and args.llm_command:
        enriched, error = run_llm(args.llm_command, question_payload(answer))
        if error:
            err.write(f"atlas: {error}\n")
        else:
            out.write("\n" + llm_label(args.llm_command) + "\n" + enriched + "\n")
    return 0 if answer.supported else 3


def cmd_impact(args, atlas, out, err):
    result = analyze_impact(atlas, args.target)
    if result is None:
        out.write(f"No file, module, or symbol named {args.target!r} in this codebase.\n")
        return 3
    if args.json:
        data = asdict(result)
        data["definitions"] = [{"path": p, "symbol": s.qualified_name if s else None,
                                "line": s.line if s else None} for p, s in result.definitions]
        _emit_json(data, out)
        return 0
    out.write(text.format_impact(result) + "\n")
    return 0


def cmd_issues(args, atlas, out, err):
    issues = find_issues(atlas, args.limit)
    if args.json:
        _emit_json([asdict(i) for i in issues], out)
        return 0
    out.write(text.format_issues(issues) + "\n")
    return 0


def cmd_snapshot(args, atlas, out, err):
    snapshot = json.dumps(make_snapshot(atlas), indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        out.write(snapshot)
        return 0
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(snapshot)
    out.write(f"Wrote snapshot of {len(atlas.modules)} modules to {args.output}\n")
    return 0


def cmd_drift(args, atlas, out, err):
    try:
        with open(args.against, encoding="utf-8") as handle:
            old = validate_snapshot(json.load(handle))
    except (OSError, ValueError) as error:
        err.write(f"atlas: cannot read snapshot {args.against}: {error}\n")
        return 2
    drift = compare_snapshots(old, make_snapshot(atlas))
    if args.json:
        _emit_json(asdict(drift), out)
    else:
        out.write(text.format_drift(drift) + "\n")
    return 1 if (args.exit_code and not drift.is_empty) else 0


def cmd_html(args, atlas, out, err):
    document = render_html(atlas, reading_order(atlas), data_flow(atlas), find_issues(atlas, 25))
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(document)
    out.write(f"Wrote interactive map of {len(atlas.modules)} modules to {args.output} (works offline)\n")
    return 0


COMMANDS = {"map": cmd_map, "ask": cmd_ask, "impact": cmd_impact, "issues": cmd_issues,
            "snapshot": cmd_snapshot, "drift": cmd_drift, "html": cmd_html}


def main(argv=None, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.repo):
        err.write(f"atlas: {args.repo} is not a directory\n")
        return 2
    atlas = build_atlas(args.repo, exclude=args.exclude)
    if atlas.warnings:
        err.write(f"atlas: {len(atlas.warnings)} file(s) skipped or unparseable\n")
        if args.verbose:
            for warning in atlas.warnings:
                err.write(f"  {warning}\n")
    return COMMANDS[args.command](args, atlas, out, err)
