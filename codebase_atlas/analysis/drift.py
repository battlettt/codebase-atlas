"""Snapshots of the map as JSON, and drift between two snapshots."""
from dataclasses import dataclass, field

SNAPSHOT_FORMAT = "codebase-atlas-snapshot"
SNAPSHOT_VERSION = 1


def symbol_key(symbol):
    return f"{symbol.kind} {symbol.qualified_name}"


def make_snapshot(atlas):
    """Deterministic JSON-ready dict (no timestamps, no absolute paths)."""
    modules = {}
    for path in sorted(atlas.modules):
        module = atlas.modules[path]
        modules[path] = {
            "language": module.language,
            "role": atlas.roles.get(path, ("", ""))[0],
            "lines": module.lines,
            "sha1": module.sha1,
            "symbols": sorted({symbol_key(s) for s in module.symbols}),
        }
    edges = [{"src": e.src, "dst": e.dst, "reasons": e.reason_list()} for e in atlas.graph.sorted_edges()]
    return {"format": SNAPSHOT_FORMAT, "version": SNAPSHOT_VERSION, "repo": atlas.name,
            "modules": modules, "edges": edges}


def validate_snapshot(data):
    if not isinstance(data, dict) or data.get("format") != SNAPSHOT_FORMAT:
        raise ValueError("not a Codebase Atlas snapshot (missing format marker)")
    if data.get("version") != SNAPSHOT_VERSION:
        raise ValueError(f"unsupported snapshot version {data.get('version')}")
    return data


@dataclass
class Drift:
    added_modules: list = field(default_factory=list)
    removed_modules: list = field(default_factory=list)
    changed_modules: list = field(default_factory=list)  # dicts
    added_edges: list = field(default_factory=list)  # (src, dst, reasons)
    removed_edges: list = field(default_factory=list)
    changed_edges: list = field(default_factory=list)  # (src, dst, old, new)
    added_symbols: list = field(default_factory=list)  # (path, key)
    removed_symbols: list = field(default_factory=list)

    @property
    def is_empty(self):
        return not any(getattr(self, name) for name in self.__dataclass_fields__)


def compare_snapshots(old, new):
    drift = Drift()
    old_modules, new_modules = old["modules"], new["modules"]
    drift.added_modules = sorted(set(new_modules) - set(old_modules))
    drift.removed_modules = sorted(set(old_modules) - set(new_modules))
    for path in sorted(set(old_modules) | set(new_modules)):
        before = set(old_modules.get(path, {}).get("symbols", []))
        after = set(new_modules.get(path, {}).get("symbols", []))
        drift.added_symbols += [(path, key) for key in sorted(after - before)]
        drift.removed_symbols += [(path, key) for key in sorted(before - after)]
        if path in old_modules and path in new_modules and old_modules[path]["sha1"] != new_modules[path]["sha1"]:
            drift.changed_modules.append({
                "path": path,
                "lines_before": old_modules[path]["lines"],
                "lines_after": new_modules[path]["lines"],
                "symbols_added": sorted(after - before),
                "symbols_removed": sorted(before - after),
                "role_before": old_modules[path].get("role", ""),
                "role_after": new_modules[path].get("role", ""),
            })
    _compare_edges(drift, old["edges"], new["edges"])
    return drift


def _compare_edges(drift, old_edges, new_edges):
    before = {(e["src"], e["dst"]): e["reasons"] for e in old_edges}
    after = {(e["src"], e["dst"]): e["reasons"] for e in new_edges}
    drift.added_edges = [(s, d, after[(s, d)]) for s, d in sorted(set(after) - set(before))]
    drift.removed_edges = [(s, d, before[(s, d)]) for s, d in sorted(set(before) - set(after))]
    drift.changed_edges = [(s, d, before[(s, d)], after[(s, d)])
                           for s, d in sorted(set(before) & set(after)) if before[(s, d)] != after[(s, d)]]
