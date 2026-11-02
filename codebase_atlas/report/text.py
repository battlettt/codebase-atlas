"""Plain-text renderings for the terminal."""
import posixpath
from collections import defaultdict

from ..analysis.summaries import module_summary
from ..retrieval import NOT_SUPPORTED


def _header(title):
    return [title, "=" * len(title)]


def format_overview(atlas):
    counts = ", ".join(f"{lang} {n}" for lang, n in atlas.language_counts().items())
    total = sum(m.lines for m in atlas.modules.values())
    lines = _header(f"Codebase Atlas: {atlas.name}")
    lines.append(f"{len(atlas.modules)} modules ({counts or 'none'}), {total} lines, "
                 f"{len(atlas.graph.edges)} internal dependencies, {len(atlas.warnings)} warning(s)")
    return lines


def format_architecture(atlas):
    lines = ["", *_header("Architecture (by directory)")]
    groups = defaultdict(list)
    for path in sorted(atlas.modules):
        groups[posixpath.dirname(path) or "."].append(path)
    for directory in sorted(groups):
        lines.append(f"{directory}/")
        for path in groups[directory]:
            lines.append(f"  {posixpath.basename(path)}")
            lines.append(f"      {module_summary(atlas, path)}")
    return lines


def format_dependencies(atlas):
    lines = ["", *_header("Dependency graph (src -> dst: reasons)")]
    if not atlas.graph.edges:
        lines.append("  (no internal dependencies found)")
    for edge in atlas.graph.sorted_edges():
        symbols = sorted({u.symbol for u in edge.uses})
        detail = f"  via {', '.join(symbols[:6])}" if symbols else ""
        lines.append(f"  {edge.src} -> {edge.dst}: {', '.join(edge.reason_list())}{detail}")
    externals = sorted({name for names in atlas.graph.externals.values() for name in names})
    if externals:
        lines.append(f"  external packages: {', '.join(externals)}")
    return lines


def format_data_flow(flow):
    lines = ["", *_header("Data flow")]
    if flow.chains:
        lines.append("Call chains from entry points:")
        lines += [f"  {' -> '.join(chain)}" for chain in flow.chains]
    if flow.calls:
        lines.append("Cross-module calls (data passed as arguments and return values):")
        for src, dst, calls in flow.calls:
            shown = ", ".join(f"{name}() @{src}:{line}" for name, line in calls[:4])
            lines.append(f"  {src} -> {dst}: {shown}")
    if flow.shared_types:
        lines.append("Shared data structures:")
        for path, name, line, users in flow.shared_types:
            lines.append(f"  {name} ({path}:{line}) used by {', '.join(users)}")
    if flow.io:
        lines.append("File and network I/O:")
        for path, mode, line, call in flow.io:
            lines.append(f"  {path}:{line} {mode} via {call}()")
    if len(lines) == 3:
        lines.append("  (no cross-module data flow detected)")
    return lines


def format_reading_order(steps):
    lines = ["", *_header("Start here: reading order")]
    for number, step in enumerate(steps, 1):
        lines.append(f"  {number:2}. {step.target}")
        lines.append(f"      {step.reason}")
    return lines


def format_warnings(atlas, verbose=False):
    if not atlas.warnings:
        return []
    lines = ["", f"Warnings: {len(atlas.warnings)} file(s) skipped or partially read"]
    if verbose:
        lines += [f"  {w}" for w in atlas.warnings]
    else:
        lines.append("  (use --verbose to list them)")
    return lines


def format_map(atlas, flow, steps, verbose=False):
    lines = format_overview(atlas)
    lines += format_architecture(atlas)
    lines += format_dependencies(atlas)
    lines += format_data_flow(flow)
    lines += format_reading_order(steps)
    lines += format_warnings(atlas, verbose)
    return "\n".join(lines)


def format_module(details):
    lines = _header(details["path"])
    lines.append(f"Role: {details['role']} ({details['role_reason']})")
    lines.append(f"Summary: {details['summary']}")
    lines.append("Symbols:")
    lines += [f"  {s['kind']:9} {s['name']}  line {s['line']}-{s['end_line']}"
              + (f"  - {s['doc']}" if s["doc"] else "") for s in details["symbols"]] or ["  (none)"]
    for key, label in (("dependencies", "Depends on"), ("dependents", "Used by")):
        lines.append(f"{label}:")
        lines += [f"  {d['path']} ({', '.join(d['reasons'])})" for d in details[key]] or ["  (none)"]
    if details["externals"]:
        lines.append(f"External: {', '.join(details['externals'])}")
    for todo in details["todos"]:
        lines.append(f"{todo['tag']} at line {todo['line']}: {todo['text']}")
    for item in details["file_io"]:
        lines.append(f"I/O at line {item['line']}: {item['mode']} via {item['call']}()")
    return "\n".join(lines)


def format_answer(answer):
    if not answer.supported:
        detail = f" ({answer.reason})" if answer.reason else ""
        return f"{NOT_SUPPORTED}{detail}"
    lines = [f"Q: {answer.question}", "",
             f"Answer (retrieved from code; {len(answer.evidence)} cited location(s), no language model):"]
    for text, _ in answer.facts:
        lines.append(f"  - {text}")
    lines.append("")
    lines.append("Evidence:")
    for number, item in enumerate(answer.evidence, 1):
        lines.append(f"  [{number}] {item.path}:{item.line}  {item.snippet}")
        where = " (in file path)" if item.kind == "path" else ""
        lines.append(f"       matched{where}: {', '.join(item.matched)}")
    return "\n".join(lines)


def format_impact(result):
    lines = _header(f"Impact of changing {result.target} ({result.kind})")
    for path, symbol in result.definitions:
        if symbol:
            lines.append(f"Defined at {path}:{symbol.line} ({symbol.kind} {symbol.qualified_name})")
        else:
            lines.append(f"File: {path}")
    if result.internal_uses:
        refs = ", ".join(f"{p}:{line}" for p, line in result.internal_uses[:8])
        lines.append(f"Also used inside its own file at: {refs}")
    lines.append(f"Risk: {result.risk.upper()} - {result.risk_reason}")
    lines.append("")
    lines.append(f"Direct dependents ({len(result.direct)}):")
    for item in result.direct:
        tag = " [possible]" if item.confidence == "possible" else ""
        lines.append(f"  {item.path}{tag}")
        lines += [f"      - {reason}" for reason in item.reasons]
    if not result.direct:
        lines.append("  (none: nothing in this repo depends on it)")
    if result.transitive:
        lines.append(f"Transitive dependents ({len(result.transitive)}):")
        for item in result.transitive:
            lines.append(f"  {item.path}  (via {' -> '.join(item.via)})")
    return "\n".join(lines)


def format_issues(issues):
    lines = _header(f"Good first issues ({len(issues)})")
    if not issues:
        lines.append("  No candidates found.")
    for number, issue in enumerate(issues, 1):
        lines.append(f"{number:2}. [{issue.score}] {issue.title}")
        lines.append(f"      at {issue.path}:{issue.line}")
        lines += [f"      {reason}" for reason in issue.reasons]
    return "\n".join(lines)


def format_drift(drift):
    if drift.is_empty:
        return "No drift: the code map matches the snapshot."
    lines = _header("Drift since snapshot")
    for label, items in (("Added modules", drift.added_modules), ("Removed modules", drift.removed_modules)):
        if items:
            lines.append(f"{label} ({len(items)}):")
            lines += [f"  {p}" for p in items]
    if drift.changed_modules:
        lines.append(f"Changed modules ({len(drift.changed_modules)}):")
        for change in drift.changed_modules:
            lines.append(f"  {change['path']}: {change['lines_before']} -> {change['lines_after']} lines")
            if change["role_before"] != change["role_after"]:
                lines.append(f"      role: {change['role_before']} -> {change['role_after']}")
    for label, items in (("Added dependencies", drift.added_edges), ("Removed dependencies", drift.removed_edges)):
        if items:
            lines.append(f"{label} ({len(items)}):")
            lines += [f"  {s} -> {d} ({', '.join(r)})" for s, d, r in items]
    if drift.changed_edges:
        lines.append(f"Changed dependencies ({len(drift.changed_edges)}):")
        lines += [f"  {s} -> {d}: {', '.join(o)} => {', '.join(n)}" for s, d, o, n in drift.changed_edges]
    for label, items in (("Added symbols", drift.added_symbols), ("Removed symbols", drift.removed_symbols)):
        if items:
            lines.append(f"{label} ({len(items)}):")
            lines += [f"  {p}: {key}" for p, key in items]
    return "\n".join(lines)
