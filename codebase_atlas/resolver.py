"""Resolve import specifiers to repository modules, per language."""
import posixpath
import re
from dataclasses import dataclass, field

TS_EXTS = [".ts", ".tsx", ".mts", ".d.ts", ".js", ".jsx", ".mjs", ".cjs"]
GO_MODULE_RE = re.compile(r"^module\s+(\S+)", re.M)


@dataclass
class Binding:
    """A local name in the importer bound to modules in the repo.

    `symbol` is the imported symbol name, None for a namespace binding
    (`import x`, `* as x`, Go package), or "*" for wildcard imports.
    """
    local: str
    dsts: list
    symbol: object = None


@dataclass
class Resolution:
    dsts: list = field(default_factory=list)  # modules that get an import edge now
    bindings: list = field(default_factory=list)
    external: str = ""  # third-party or stdlib name when unresolved
    package_files: list = field(default_factory=list)  # Go: edge target decided later


def python_dotted_name(path):
    stem = path[:-3] if path.endswith(".py") else path
    parts = stem.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def parse_go_mod(text):
    match = GO_MODULE_RE.search(text)
    return match.group(1) if match else ""


class Resolver:
    def __init__(self, modules, go_modules=None):
        """`go_modules` maps a Go module path to its directory (from go.mod)."""
        self.modules = modules
        self.paths = set(modules)
        self.go_modules = go_modules or {}
        self.py_index = {}
        self.go_dirs = {}
        for path, module in modules.items():
            if module.language == "python":
                self.py_index.setdefault(python_dotted_name(path), []).append(path)
            elif module.language == "go":
                self.go_dirs.setdefault(posixpath.dirname(path), []).append(path)

    def resolve(self, module, imp):
        if module.language == "python":
            return self._resolve_python(module.path, imp)
        if module.language in ("typescript", "javascript"):
            return self._resolve_ts(module.path, imp)
        if module.language == "go":
            return self._resolve_go(imp)
        return Resolution()

    # Python -----------------------------------------------------------
    def python_module(self, dotted, importer=""):
        """Find the file for a dotted module name; None if not in the repo."""
        if not dotted:
            return None
        candidates = list(self.py_index.get(dotted, []))
        if not candidates:
            for name, paths in self.py_index.items():
                if name.endswith("." + dotted):
                    candidates.extend(p for p in paths if self._is_source_root_match(p, dotted))
        if not candidates:
            return None
        return max(candidates, key=lambda p: (_shared_prefix(p, importer), -len(p)))

    def _is_source_root_match(self, path, dotted):
        """Accept `src/pkg/mod.py` for `pkg.mod` only if `src` is not a package."""
        depth = dotted.count(".") + 1
        parts = python_dotted_name(path).split(".")
        root_parts = path.split("/")[: len(parts) - depth]
        root = "/".join(root_parts)
        return (root + "/__init__.py") not in self.paths

    def _relative_base(self, importer, imp):
        directory = posixpath.dirname(importer)
        for _ in range(imp.level - 1):
            directory = posixpath.dirname(directory)
        parts = [p for p in directory.split("/") if p]
        if imp.target:
            parts += imp.target.split(".")
        return parts

    def _python_path(self, parts):
        stem = "/".join(parts)
        for candidate in (stem + ".py", (stem + "/" if stem else "") + "__init__.py"):
            if candidate in self.paths:
                return candidate
        return None

    def _resolve_python(self, importer, imp):
        result = Resolution()
        if imp.level:
            parts = self._relative_base(importer, imp)
            find = lambda extra: self._python_path(parts + extra)  # noqa: E731
        else:
            find = lambda extra: self.python_module(".".join([imp.target] + extra), importer)  # noqa: E731
        if not imp.names:  # import a.b [as c]
            path = find([])
            if path:
                result.dsts.append(path)
                result.bindings.append(Binding(imp.alias, [path]))
            else:
                result.external = imp.target.split(".")[0]
            return result
        base = find([])
        for name, local in imp.names:
            sub = find([name]) if name != "*" else None
            if sub:
                result.dsts.append(sub)
                result.bindings.append(Binding(local, [sub]))
            elif base:
                result.bindings.append(Binding(local, [base], name))
        if base and (base not in result.dsts) and any(b.dsts == [base] for b in result.bindings):
            result.dsts.append(base)
        if not result.dsts and not imp.level:
            result.external = imp.target.split(".")[0]
        return result

    # TypeScript / JavaScript -----------------------------------------
    def ts_module(self, importer, spec):
        if not spec.startswith("."):
            return None
        base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
        stems = [base]
        root, ext = posixpath.splitext(base)
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            stems.append(root)
        for stem in stems:
            candidates = [stem] + [stem + e for e in TS_EXTS] + [stem + "/index" + e for e in TS_EXTS]
            for candidate in candidates:
                if candidate in self.paths:
                    return candidate
        return None

    def _resolve_ts(self, importer, imp):
        result = Resolution()
        path = self.ts_module(importer, imp.target)
        if not path:
            if not imp.target.startswith("."):
                parts = imp.target.split("/")
                result.external = "/".join(parts[:2]) if imp.target.startswith("@") else parts[0]
            return result
        result.dsts.append(path)
        default = self.modules[path].default_export or "default"
        for name, local in imp.names:
            symbol = default if name == "default" else name
            result.bindings.append(Binding(local, [path], symbol))
        if imp.alias:
            result.bindings.append(Binding(imp.alias, [path]))
        return result

    # Go ---------------------------------------------------------------
    def go_package_files(self, spec):
        for module_path, module_dir in self.go_modules.items():
            if spec == module_path or spec.startswith(module_path + "/"):
                rest = spec[len(module_path):].lstrip("/")
                directory = posixpath.normpath(posixpath.join(module_dir, rest)) if rest else module_dir
                directory = "" if directory == "." else directory
                return sorted(p for p in self.go_dirs.get(directory, []) if not p.endswith("_test.go"))
        return []

    def _resolve_go(self, imp):
        result = Resolution()
        files = self.go_package_files(imp.target)
        if not files:
            result.external = imp.target
            return result
        result.package_files = files
        if imp.alias == ".":
            result.bindings.append(Binding("*", files, "*"))
        elif imp.alias != "_":
            local = imp.alias or self.modules[files[0]].package or imp.target.rsplit("/", 1)[-1]
            result.bindings.append(Binding(local, files))
        return result


def _shared_prefix(a, b):
    count = 0
    for x, y in zip(a.split("/"), b.split("/")):
        if x != y:
            break
        count += 1
    return count
