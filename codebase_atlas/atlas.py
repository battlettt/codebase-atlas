"""Build the full in-memory atlas for a repository (scan, parse, graph, roles)."""
import json
import os
import posixpath
import tomllib
from dataclasses import dataclass, field

from .graph import build_graph
from .parsers import parse_source
from .resolver import Resolver, parse_go_mod
from .scanner import find_readme, read_text, scan

ENTRY_FILE_NAMES = {
    "main.py", "cli.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "index.ts", "main.ts", "cli.ts", "server.ts", "app.ts",
    "index.js", "main.js", "cli.js", "server.js", "app.js",
}


@dataclass
class Atlas:
    root: str
    modules: dict
    sources: dict  # path -> list of source lines
    docs: dict  # markdown path -> list of lines
    graph: object
    readme: str = ""
    warnings: list = field(default_factory=list)
    roles: dict = field(default_factory=dict)  # path -> (role, reason)

    @property
    def name(self):
        return os.path.basename(self.root.rstrip("/")) or self.root

    def entry_points(self):
        return sorted(p for p, m in self.modules.items() if m.is_entry)

    def language_counts(self):
        counts = {}
        for module in self.modules.values():
            counts[module.language] = counts.get(module.language, 0) + 1
        return dict(sorted(counts.items()))


def build_atlas(root, exclude=()):
    """Scan and analyse `root`. Unparseable files become warnings, never crashes."""
    from .analysis.roles import assign_roles

    result = scan(root, extra_skip=exclude)
    warnings = [f"{path}: skipped ({reason})" for path, reason in result.skipped]
    modules, sources = {}, {}
    for rel, language in result.sources:
        text = read_text(os.path.join(result.root, rel))
        if text is None:
            warnings.append(f"{rel}: skipped (binary or unreadable)")
            continue
        try:
            module = parse_source(rel, language, text)
        except (SyntaxError, ValueError, RecursionError, IndexError) as error:
            warnings.append(f"{rel}: skipped (could not parse: {type(error).__name__}: {error})")
            continue
        modules[rel] = module
        sources[rel] = text.splitlines()
    docs = _read_docs(result.root, result.docs)
    resolver = Resolver(modules, _go_modules(result.root, result.manifests))
    graph = build_graph(modules, resolver)
    _mark_manifest_entries(result.root, result.manifests, modules, resolver, warnings)
    atlas = Atlas(result.root, modules, sources, docs, graph, find_readme(result.docs) or "", warnings)
    _mark_conventional_entries(atlas)
    assign_roles(atlas)
    return atlas


def _read_docs(root, doc_paths):
    docs = {}
    for rel in doc_paths:
        text = read_text(os.path.join(root, rel))
        if text is not None:
            docs[rel] = text.splitlines()
    return docs


def _go_modules(root, manifests):
    found = {}
    for rel in manifests:
        if posixpath.basename(rel) == "go.mod":
            text = read_text(os.path.join(root, rel)) or ""
            module_path = parse_go_mod(text)
            if module_path:
                directory = posixpath.dirname(rel)
                found[module_path] = directory
    return found


def _mark(module, reason):
    if not module.is_entry:
        module.is_entry = True
        module.entry_reason = reason


def _mark_manifest_entries(root, manifests, modules, resolver, warnings):
    for rel in manifests:
        name = posixpath.basename(rel)
        try:
            if name == "package.json":
                _package_json_entries(root, rel, modules)
            elif name == "pyproject.toml":
                _pyproject_entries(root, rel, modules, resolver)
        except (ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError) as error:
            warnings.append(f"{rel}: could not read manifest ({error})")


def _package_json_entries(root, rel, modules):
    data = json.loads(read_text(os.path.join(root, rel)) or "{}")
    directory = posixpath.dirname(rel)
    targets = []
    for key in ("main", "module", "types"):
        if isinstance(data.get(key), str):
            targets.append((key, data[key]))
    binaries = data.get("bin")
    if isinstance(binaries, str):
        targets.append(("bin", binaries))
    elif isinstance(binaries, dict):
        targets.extend(("bin", v) for v in binaries.values() if isinstance(v, str))
    for key, target in targets:
        path = posixpath.normpath(posixpath.join(directory, target))
        if path in modules:
            _mark(modules[path], f'listed as "{key}" in {rel}')


def _pyproject_entries(root, rel, modules, resolver):
    data = tomllib.loads(read_text(os.path.join(root, rel)) or "")
    scripts = data.get("project", {}).get("scripts", {})
    for command, target in scripts.items():
        dotted = target.split(":")[0]
        path = resolver.python_module(dotted, rel)
        if path:
            _mark(modules[path], f'provides the `{command}` console script in {rel}')


def _mark_conventional_entries(atlas):
    from .analysis.roles import is_test_path

    for path, module in atlas.modules.items():
        if module.is_entry or is_test_path(path):
            continue
        if posixpath.basename(path) in ENTRY_FILE_NAMES and atlas.graph.fan_in(path) == 0:
            _mark(module, "conventional entry file name and nothing imports it")
