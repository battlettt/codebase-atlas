"""Static module summaries from docstrings, symbols, size, and edges."""
import posixpath

from ..model import TYPE_KINDS
from .reading_order import short_list


def first_sentence(text, limit=160):
    text = " ".join(text.split())
    if not text:
        return ""
    for end in (". ", ".\n"):
        index = text.find(end)
        if index != -1:
            text = text[: index + 1]
            break
    return text if len(text) <= limit else text[: limit - 3] + "..."


def symbol_counts(module):
    top = module.top_level_symbols()
    functions = sum(s.kind == "function" for s in top)
    types = sum(s.kind in TYPE_KINDS for s in top)
    return functions, types


def exported_names(module, limit=None):
    names = [s.name for s in module.top_level_symbols() if s.exported]
    return names if limit is None else names[:limit]


def module_summary(atlas, path):
    """One line: purpose, role, shape, and connections."""
    module = atlas.modules[path]
    graph = atlas.graph
    role = atlas.roles.get(path, ("module", ""))[0]
    purpose = first_sentence(module.doc) or _fallback_purpose(module)
    functions, types = symbol_counts(module)
    parts = [purpose, f"[{role}]", f"{module.lines} lines, {functions} function(s), {types} type(s)"]
    exports = exported_names(module)
    if exports:
        more = f" (+{len(exports) - 5})" if len(exports) > 5 else ""
        parts.append("exports " + ", ".join(exports[:5]) + more)
    deps, users = graph.dependencies(path), graph.dependents(path)
    if deps:
        parts.append("depends on " + short_list(deps))
    if users:
        parts.append("used by " + short_list(users))
    return parts[0] + " " + "; ".join(parts[1:])


def _fallback_purpose(module):
    top = module.top_level_symbols()
    if not top:
        return "(no docstring; no top-level definitions)"
    names = ", ".join(s.name for s in top[:3])
    return f"(no docstring) Defines {names}{'...' if len(top) > 3 else ''}."


def module_details(atlas, path):
    """Structured details used by the text map, JSON, and HTML views."""
    module = atlas.modules[path]
    graph = atlas.graph
    role, role_reason = atlas.roles.get(path, ("module", ""))
    return {
        "path": path,
        "name": posixpath.basename(path),
        "language": module.language,
        "role": role,
        "role_reason": role_reason,
        "summary": module_summary(atlas, path),
        "doc": first_sentence(module.doc, 400),
        "lines": module.lines,
        "entry": module.is_entry,
        "entry_reason": module.entry_reason,
        "symbols": [
            {"name": s.qualified_name, "kind": s.kind, "line": s.line, "end_line": s.end_line,
             "exported": s.exported, "doc": first_sentence(s.doc)}
            for s in module.symbols
        ],
        "dependencies": [_edge_info(graph.edges[(path, d)], d) for d in graph.dependencies(path)],
        "dependents": [_edge_info(graph.edges[(s, path)], s) for s in graph.dependents(path)],
        "externals": sorted(graph.externals.get(path, ())),
        "todos": [{"line": t.line, "tag": t.tag, "text": t.text} for t in module.todos],
        "file_io": [{"line": f.line, "mode": f.mode, "call": f.call} for f in module.file_io],
    }


def _edge_info(edge, other):
    return {"path": other, "reasons": edge.reason_list(),
            "symbols": sorted({u.symbol for u in edge.uses})}
