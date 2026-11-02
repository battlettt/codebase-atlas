"""Start-here reading order: README, entry points, then dependencies first."""
import heapq
import posixpath
from dataclasses import dataclass

from .roles import is_test_path


@dataclass
class Step:
    target: str
    kind: str  # doc or module
    reason: str


def short_list(paths, limit=3):
    names = [posixpath.basename(p) for p in paths]
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f" and {len(names) - limit} more"


def reading_order(atlas):
    steps = []
    if atlas.readme:
        steps.append(Step(atlas.readme, "doc", "Project overview: read this before any code."))
    entries = sorted(atlas.entry_points(), key=lambda p: (is_test_path(p), p))
    for path in entries:
        steps.append(Step(path, "module", f"Entry point: {atlas.modules[path].entry_reason}."))
    for path, in_cycle in _dependency_order(atlas, set(entries)):
        steps.append(Step(path, "module", _reason(atlas, path, in_cycle)))
    return steps


def _dependency_order(atlas, done):
    """Kahn's algorithm with a priority: non-tests first, then high fan-in."""
    graph = atlas.graph
    remaining = [p for p in graph.nodes if p not in done]
    pending = {p: {d for d in graph.dependencies(p) if d not in done and d != p} for p in remaining}
    key = lambda p: (is_test_path(p), -graph.fan_in(p), p)  # noqa: E731
    heap = [key(p) for p in remaining if not pending[p]]
    heapq.heapify(heap)
    placed, order = set(done), []
    while len(order) < len(remaining):
        stuck = _cycle_breaker(heap, remaining, placed, pending, key)
        in_cycle = stuck is not None
        path = stuck if in_cycle else heapq.heappop(heap)[-1]
        if path in placed:
            continue
        placed.add(path)
        order.append((path, in_cycle))
        for dependent in graph.dependents(path):
            if dependent in pending and dependent not in placed:
                pending[dependent].discard(path)
                if not pending[dependent]:
                    heapq.heappush(heap, key(dependent))
    return order


def _cycle_breaker(heap, remaining, placed, pending, key):
    """Pick a module to release when only a cycle blocks progress.

    Cycles among non-test modules are broken before tests are read, so a
    newcomer still sees all production code first.
    """
    blocked = [p for p in remaining if p not in placed and pending[p]]
    production = [p for p in blocked if not is_test_path(p) and not any(is_test_path(d) for d in pending[p])]
    heap_has_production = any(not k[0] for k in heap)
    if production and not heap_has_production:
        return min(production, key=lambda p: (len(pending[p]), key(p)))
    if not heap and blocked:
        return min(blocked, key=lambda p: (len(pending[p]), key(p)))
    return None


def _reason(atlas, path, in_cycle):
    graph = atlas.graph
    deps = graph.dependencies(path)
    users = graph.dependents(path)
    role = atlas.roles.get(path, ("module", ""))[0]
    used = f"used by {len(users)} module(s)" if users else "nothing imports it"
    if in_cycle:
        return f"Part of a dependency cycle (depends on {short_list(deps)}); {used}."
    if is_test_path(path):
        return f"Test: exercises {short_list(deps)}." if deps else "Test with no internal imports."
    if not deps:
        return f"Foundation ({role}): no internal dependencies; {used}."
    return f"Builds on {short_list(deps)} (read above); {used}."
