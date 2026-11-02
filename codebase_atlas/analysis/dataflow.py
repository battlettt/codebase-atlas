"""How data moves: cross-module calls, shared types, file I/O, call chains."""
from collections import defaultdict
from dataclasses import dataclass, field

from .roles import is_test_path


@dataclass
class DataFlow:
    calls: list = field(default_factory=list)  # (src, dst, [(symbol, line)])
    shared_types: list = field(default_factory=list)  # (def_path, symbol, line, [users])
    io: list = field(default_factory=list)  # (path, mode, line, call)
    chains: list = field(default_factory=list)  # [path, path, ...]


def data_flow(atlas, max_chains=10):
    graph = atlas.graph
    flow = DataFlow()
    type_users = defaultdict(set)
    for edge in graph.sorted_edges():
        calls = sorted({(u.symbol, u.line) for u in edge.uses if u.reason == "call"}, key=lambda c: c[1])
        if calls:
            flow.calls.append((edge.src, edge.dst, calls))
        for use in edge.uses:
            if use.reason == "shared type":
                type_users[(edge.dst, use.symbol)].add(edge.src)
    for (path, name), users in sorted(type_users.items()):
        symbol = atlas.modules[path].symbol_named(name)
        flow.shared_types.append((path, name, symbol.line if symbol else 1, sorted(users)))
    for path in sorted(atlas.modules):
        for item in atlas.modules[path].file_io:
            flow.io.append((path, item.mode, item.line, item.call))
    flow.chains = call_chains(atlas, max_chains)
    return flow


def _call_targets(graph, path):
    return [d for d in graph.dependencies(path)
            if any(u.reason == "call" for u in graph.edges[(path, d)].uses) and not is_test_path(d)]


def call_chains(atlas, limit=10, max_depth=8):
    """Longest call paths starting at each entry point (cycle-safe)."""
    graph = atlas.graph
    chains = []

    def walk(path, trail):
        nexts = [n for n in _call_targets(graph, path) if n not in trail]
        if not nexts or len(trail) >= max_depth:
            if len(trail) > 1:
                chains.append(list(trail))
            return
        for nxt in nexts:
            walk(nxt, trail + [nxt])

    for entry in atlas.entry_points():
        if not is_test_path(entry):
            walk(entry, [entry])
    chains = [c for c in chains if not any(_is_prefix(c, o) for o in chains if o is not c)]
    chains.sort(key=lambda c: (-len(c), c))
    return chains[:limit]


def _is_prefix(short, long):
    return len(short) < len(long) and long[: len(short)] == short
