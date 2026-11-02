"""Change-impact analysis: who depends on a file or symbol, and what breaks."""
import posixpath
from collections import deque
from dataclasses import dataclass, field

from ..model import TYPE_KINDS
from ..resolver import python_dotted_name
from .roles import is_test_path


@dataclass
class Affected:
    path: str
    depth: int  # 1 = direct
    reasons: list = field(default_factory=list)  # human-readable, each with a line
    via: list = field(default_factory=list)  # chain from target for transitive hits
    confidence: str = "certain"  # certain, possible


@dataclass
class ImpactResult:
    target: str
    kind: str  # file or symbol
    definitions: list = field(default_factory=list)  # (path, Symbol or None)
    affected: list = field(default_factory=list)
    internal_uses: list = field(default_factory=list)  # (path, line) inside the defining file
    tests: list = field(default_factory=list)
    risk: str = "low"
    risk_reason: str = ""

    @property
    def direct(self):
        return [a for a in self.affected if a.depth == 1]

    @property
    def transitive(self):
        return [a for a in self.affected if a.depth > 1]


def resolve_target(atlas, target):
    """Return ('file', [paths]) or ('symbol', [(path, Symbol)]) or (None, [])."""
    clean = target.strip().lstrip("./").replace("\\", "/")
    if clean in atlas.modules:
        return "file", [clean]
    by_suffix = [p for p in atlas.modules if p.endswith("/" + clean)]
    if by_suffix:
        return "file", sorted(by_suffix)
    by_dotted = [p for p in atlas.modules
                 if atlas.modules[p].language == "python" and python_dotted_name(p).endswith(clean)
                 and (python_dotted_name(p) == clean or python_dotted_name(p).endswith("." + clean))]
    if by_dotted and "." in clean:
        return "file", sorted(by_dotted)
    symbols = []
    for path in sorted(atlas.modules):
        for symbol in atlas.modules[path].symbols:
            if clean in (symbol.name, symbol.qualified_name):
                symbols.append((path, symbol))
    if symbols:
        return "symbol", symbols
    return None, []


def analyze_impact(atlas, target):
    kind, hits = resolve_target(atlas, target)
    if kind is None:
        return None
    result = ImpactResult(target, kind)
    if kind == "file":
        result.definitions = [(path, None) for path in hits]
        direct = _file_dependents(atlas, hits)
    else:
        result.definitions = hits
        direct = _symbol_dependents(atlas, hits, result)
    result.affected = direct + _transitive(atlas, direct, {p for p, _ in result.definitions})
    result.tests = sorted({a.path for a in result.affected if is_test_path(a.path)})
    result.risk, result.risk_reason = _risk(result)
    return result


def _use_reason(use):
    if use.reason == "call":
        return f"calls {use.symbol}() at line {use.line}; breaks if its signature or return value changes"
    if use.reason == "shared type":
        return f"uses type {use.symbol} at line {use.line}; breaks if its fields or shape change"
    return f"references {use.symbol} at line {use.line}; breaks if it is renamed or removed"


def _file_dependents(atlas, paths):
    graph = atlas.graph
    found = {}
    for path in paths:
        for src in graph.dependents(path):
            edge = graph.edges[(src, path)]
            entry = found.setdefault(src, Affected(src, 1))
            for line in edge.import_lines:
                entry.reasons.append(f"imports {posixpath.basename(path)} at line {line}; breaks if it moves or is renamed")
            for use in sorted(edge.uses, key=lambda u: u.line):
                entry.reasons.append(_use_reason(use))
    return [found[p] for p in sorted(found)]


def _symbol_dependents(atlas, definitions, result):
    found = {}
    for path, symbol in definitions:
        if symbol.parent:
            _method_matches(atlas, path, symbol, found)
            continue
        for use in sorted(atlas.graph.all_uses(), key=lambda u: (u.src, u.line)):
            if use.dst == path and use.symbol == symbol.name:
                found.setdefault(use.src, Affected(use.src, 1)).reasons.append(_use_reason(use))
        for ref in atlas.modules[path].refs:
            if ref.name.split(".")[0] == symbol.name and not (symbol.line <= ref.line <= symbol.end_line):
                result.internal_uses.append((path, ref.line))
    return [found[p] for p in sorted(found)]


def _method_matches(atlas, path, symbol, found):
    """Methods are called on objects, so match `.name(` calls by name only."""
    for src in sorted(atlas.modules):
        for ref in atlas.modules[src].refs:
            parts = ref.name.split(".")
            if ref.is_call and len(parts) > 1 and parts[-1] == symbol.name and src != path:
                entry = found.setdefault(src, Affected(src, 1, confidence="possible"))
                entry.reasons.append(
                    f"calls .{symbol.name}() at line {ref.line} (matched by method name only)")


def _transitive(atlas, direct, origin):
    graph = atlas.graph
    seen = set(origin) | {a.path for a in direct}
    queue = deque((a.path, [a.path]) for a in direct)
    found = []
    while queue:
        path, chain = queue.popleft()
        for src in graph.dependents(path):
            if src in seen:
                continue
            seen.add(src)
            via = chain + [src]
            found.append(Affected(src, len(via), [f"depends on {posixpath.basename(path)}, which is affected"], via))
            queue.append((src, via))
    return found


def _risk(result):
    non_test = [a for a in result.affected if not is_test_path(a.path)]
    direct = [a for a in result.direct if not is_test_path(a.path)]
    tested = "covered by tests: " + ", ".join(result.tests) if result.tests \
        else "no test depends on it, so breakage would go unnoticed"
    if len(non_test) >= 5 or len(direct) >= 3:
        level = "high"
    elif non_test:
        level = "medium"
    else:
        level = "low"
    if level != "high" and not result.tests and non_test:
        level = {"low": "medium", "medium": "high"}[level]
    is_type = any(s and s.kind in TYPE_KINDS for _, s in result.definitions)
    shape = "; type changes ripple to every user" if is_type else ""
    return level, f"{len(direct)} direct and {len(non_test) - len(direct)} transitive non-test dependent(s); {tested}{shape}"
