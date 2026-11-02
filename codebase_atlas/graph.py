"""Module dependency graph with per-edge reasons and evidence lines."""
import posixpath
from collections import defaultdict
from dataclasses import dataclass, field

from .model import TYPE_KINDS

REASON_ORDER = ["import", "call", "shared type", "reference"]


@dataclass
class Use:
    src: str
    dst: str
    symbol: str
    line: int
    reason: str  # call, shared type, reference


@dataclass
class Edge:
    src: str
    dst: str
    reasons: set = field(default_factory=set)
    import_lines: list = field(default_factory=list)
    uses: list = field(default_factory=list)

    def reason_list(self):
        return sorted(self.reasons, key=lambda r: REASON_ORDER.index(r) if r in REASON_ORDER else 99)


class Graph:
    def __init__(self, nodes):
        self.nodes = sorted(nodes)
        self.edges = {}
        self.externals = defaultdict(set)
        self._out = defaultdict(set)
        self._in = defaultdict(set)

    def edge(self, src, dst):
        key = (src, dst)
        if key not in self.edges:
            self.edges[key] = Edge(src, dst)
            self._out[src].add(dst)
            self._in[dst].add(src)
        return self.edges[key]

    def add_import(self, src, dst, line):
        if src == dst:
            return
        edge = self.edge(src, dst)
        edge.reasons.add("import")
        if line not in edge.import_lines:
            edge.import_lines.append(line)

    def add_use(self, use):
        if use.src == use.dst:
            return
        edge = self.edge(use.src, use.dst)
        if use not in edge.uses:
            edge.uses.append(use)
            edge.reasons.add(use.reason)

    def dependencies(self, path):
        return sorted(self._out.get(path, ()))

    def dependents(self, path):
        return sorted(self._in.get(path, ()))

    def fan_in(self, path):
        return len(self._in.get(path, ()))

    def fan_out(self, path):
        return len(self._out.get(path, ()))

    def all_uses(self):
        for edge in self.edges.values():
            yield from edge.uses

    def sorted_edges(self):
        return [self.edges[k] for k in sorted(self.edges)]


def use_reason(symbol, is_call):
    if symbol.kind in TYPE_KINDS:
        return "shared type"
    return "call" if is_call else "reference"


def build_graph(modules, resolver):
    graph = Graph(modules)
    bindings, go_imports = {}, []
    for path, module in modules.items():
        bindings[path] = []
        for imp in module.imports:
            result = resolver.resolve(module, imp)
            for dst in result.dsts:
                graph.add_import(path, dst, imp.line)
            bindings[path].extend(result.bindings)
            if result.package_files:
                go_imports.append((path, result.package_files, imp.line))
            if result.external:
                graph.externals[path].add(result.external)
    for path, module in modules.items():
        _add_uses(graph, module, bindings, modules)
    _add_go_package_uses(graph, modules)
    _add_go_import_edges(graph, go_imports)
    return graph


def _binding_tables(module_bindings):
    names, namespaces, wildcards = {}, {}, []
    for binding in module_bindings:
        if binding.symbol == "*":
            wildcards.append(binding.dsts)
        elif binding.symbol is None:
            namespaces[binding.local] = binding.dsts
        else:
            names[binding.local] = (binding.dsts, binding.symbol)
    return names, namespaces, wildcards


def find_definition(dsts, symbol, bindings, modules, depth=0):
    """Locate `symbol` in `dsts`, following re-exports a few levels deep."""
    for dst in dsts:
        found = modules[dst].symbol_named(symbol)
        if found:
            return dst, found
    if depth >= 3:
        return None
    for dst in dsts:
        names, _, wildcards = _binding_tables(bindings.get(dst, []))
        if symbol in names:
            inner_dsts, inner_symbol = names[symbol]
            hit = find_definition(inner_dsts, inner_symbol, bindings, modules, depth + 1)
            if hit:
                return hit
        for wild in wildcards:
            hit = find_definition(wild, symbol, bindings, modules, depth + 1)
            if hit:
                return hit
    return None


def _ref_targets(ref, names, namespaces, wildcards):
    """Candidate (modules, symbol) pairs a reference may point at."""
    parts = ref.name.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        alias = ".".join(parts[:cut])
        if alias in namespaces:
            return [(namespaces[alias], parts[cut])]
    if parts[0] in names:
        return [names[parts[0]]]
    return [(dsts, parts[0]) for dsts in wildcards]


def _add_uses(graph, module, bindings, modules):
    names, namespaces, wildcards = _binding_tables(bindings[module.path])
    if not (names or namespaces or wildcards):
        return
    for ref in module.refs:
        for dsts, name in _ref_targets(ref, names, namespaces, wildcards):
            hit = find_definition(dsts, name, bindings, modules)
            if hit:
                dst, symbol = hit
                graph.add_use(Use(module.path, dst, symbol.name, ref.line, use_reason(symbol, ref.is_call)))
                break


def _add_go_package_uses(graph, modules):
    """Files in one Go package share a namespace without imports."""
    packages = defaultdict(dict)
    for path, module in modules.items():
        if module.language == "go":
            for symbol in module.top_level_symbols():
                packages[posixpath.dirname(path)].setdefault(symbol.name, (path, symbol))
    for path, module in modules.items():
        if module.language != "go":
            continue
        table = packages[posixpath.dirname(path)]
        for ref in module.refs:
            head = ref.name.split(".")[0]
            if head in table and table[head][0] != path and module.symbol_named(head) is None:
                dst, symbol = table[head]
                graph.add_use(Use(path, dst, symbol.name, ref.line, use_reason(symbol, ref.is_call)))


def _add_go_import_edges(graph, go_imports):
    """Point Go package imports at the files whose symbols are used."""
    for src, files, line in go_imports:
        used = {dst for dst in graph.dependencies(src) if dst in files}
        for dst in sorted(used or files):
            graph.add_import(src, dst, line)
