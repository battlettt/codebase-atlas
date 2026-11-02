"""Python parser built on the standard library `ast` module."""
import ast
import io
import os
import re
import tokenize

from ..model import Import, Ref, Symbol, Todo
from .common import file_io_from_refs, new_module, TODO_RE

IO_CALLS = {
    "open": "read",
    "json.load": "read", "pickle.load": "read", "csv.reader": "read",
    "csv.DictReader": "read", "read_text": "read", "read_bytes": "read",
    "tomllib.load": "read", "sqlite3.connect": "read", "os.listdir": "read",
    "json.dump": "write", "pickle.dump": "write", "csv.writer": "write",
    "csv.DictWriter": "write", "write_text": "write", "write_bytes": "write",
    "shutil.copy": "write", "os.remove": "write", "os.makedirs": "write",
    "urlopen": "network", "requests.get": "network", "requests.post": "network",
    "socket.socket": "network", "subprocess.run": "process",
}
WRITE_MODE_RE = re.compile(r"""['"][rwxab+t]*[wxa][rwxab+t]*['"]""")
BRANCH_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.ExceptHandler,
    ast.With, ast.AsyncWith, ast.BoolOp, ast.IfExp, ast.comprehension,
)


def parse_python(path, text):
    tree = ast.parse(text, filename=path)
    lines = text.splitlines()
    module = new_module(path, "python", text)
    module.doc = ast.get_docstring(tree) or ""
    module.symbols = _symbols(tree, lines, _dunder_all(tree))
    module.imports = _imports(tree)
    collector = _RefCollector()
    collector.visit(tree)
    module.refs = collector.refs
    module.todos = _todos(text)
    module.file_io = file_io_from_refs(module.refs, lines, IO_CALLS, _open_mode)
    module.is_entry, module.entry_reason = _entry(path, tree)
    return module


def _dunder_all(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                return {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
    return None


def _is_public(name, exports):
    if exports is not None:
        return name in exports
    return not name.startswith("_")


def _complexity(node):
    return 1 + sum(isinstance(child, BRANCH_NODES) for child in ast.walk(node))


def _signature(lines, node):
    return lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""


def _def_symbol(node, lines, kind, exported, parent=""):
    return Symbol(
        name=node.name,
        kind=kind,
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        exported=exported,
        doc=(ast.get_docstring(node) or "")[:500],
        parent=parent,
        signature=_signature(lines, node),
        complexity=_complexity(node),
    )


def _symbols(tree, lines, exports):
    symbols = []
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in tree.body:
        if isinstance(node, functions):
            symbols.append(_def_symbol(node, lines, "function", _is_public(node.name, exports)))
        elif isinstance(node, ast.ClassDef):
            public = _is_public(node.name, exports)
            symbols.append(_def_symbol(node, lines, "class", public))
            for item in node.body:
                if isinstance(item, functions):
                    method_public = public and not item.name.startswith("_")
                    symbols.append(_def_symbol(item, lines, "method", method_public, node.name))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            symbols.extend(_constants(node, lines, exports))
    return symbols


def _constants(node, lines, exports):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    out = []
    for target in targets:
        if not isinstance(target, ast.Name) or target.id == "__all__":
            continue
        name = target.id
        if name.isupper() or (exports is not None and name in exports):
            out.append(Symbol(name, "const", node.lineno, node.end_lineno or node.lineno,
                              _is_public(name, exports), signature=_signature(lines, node)))
    return out


def _imports(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(Import(alias.name, node.lineno, alias=alias.asname or alias.name))
        elif isinstance(node, ast.ImportFrom):
            names = [(a.name, a.asname or a.name) for a in node.names]
            found.append(Import(node.module or "", node.lineno, names=names, level=node.level))
    return sorted(found, key=lambda imp: imp.line)


def dotted_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class _RefCollector(ast.NodeVisitor):
    """Record every dotted name that is loaded or called."""

    def __init__(self):
        self.refs = []

    def visit_Call(self, node):
        name = dotted_name(node.func)
        if name:
            self.refs.append(Ref(name, node.lineno, True))
        else:
            self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_Attribute(self, node):
        name = dotted_name(node)
        if name and isinstance(node.ctx, ast.Load):
            self.refs.append(Ref(name, node.lineno, False))
        elif not name:
            self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.refs.append(Ref(node.id, node.lineno, False))


def _todos(text):
    todos = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                match = TODO_RE.search(token.string)
                if match:
                    todos.append(Todo(token.start[0], match.group(1), match.group(2).strip()))
    except (tokenize.TokenError, SyntaxError):
        pass
    return todos


def _open_mode(ref, snippet, mode):
    if ref.name == "open" and WRITE_MODE_RE.search(snippet):
        return "write"
    return mode


def _is_main_guard(node):
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    values = [test.left] + list(test.comparators)
    has_name = any(isinstance(v, ast.Name) and v.id == "__name__" for v in values)
    has_main = any(isinstance(v, ast.Constant) and v.value == "__main__" for v in values)
    return has_name and has_main


def _entry(path, tree):
    if os.path.basename(path) == "__main__.py":
        return True, "package __main__ module (run with python -m)"
    for node in tree.body:
        if _is_main_guard(node):
            return True, f'has an `if __name__ == "__main__"` block at line {node.lineno}'
    return False, ""
