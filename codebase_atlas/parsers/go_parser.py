"""Regex-based parser for Go."""
import re

from ..model import Import, Symbol
from .common import (
    LineIndex, block_end_line, complexity_of, extract_refs, file_io_from_refs,
    find_todos, leading_comment, new_module, strip_c_like,
)

KEYWORDS = {
    "break", "case", "chan", "const", "continue", "default", "defer", "else",
    "fallthrough", "for", "func", "go", "goto", "if", "import", "interface",
    "map", "package", "range", "return", "select", "struct", "switch", "type",
    "var", "nil", "true", "false", "iota", "string", "int", "int64", "int32",
    "float64", "float32", "bool", "byte", "rune", "error", "any", "uint",
    "uint64", "uint32", "uint8", "make", "len", "cap", "append", "new",
    "panic", "recover", "copy", "delete", "close",
}

PACKAGE_RE = re.compile(r"^package\s+(\w+)", re.M)
IMPORT_SINGLE_RE = re.compile(r"^import\s+(?:([\w.]+)\s+)?\"([^\"]+)\"", re.M)
IMPORT_BLOCK_RE = re.compile(r"^import\s*\((.*?)\)", re.M | re.S)
IMPORT_LINE_RE = re.compile(r"^\s*(?:([\w.]+)\s+)?\"([^\"]+)\"")
FUNC_RE = re.compile(r"^func\s+([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*\(")
METHOD_RE = re.compile(
    r"^func\s*\(\s*(?:\w+\s+)?\*?\s*([A-Za-z_]\w*)(?:\[[^\]]*\])?\s*\)\s*([A-Za-z_]\w*)\s*\(")
TYPE_RE = re.compile(r"^type\s+([A-Za-z_]\w*)(?:\[[^\]]*\])?\s+(struct|interface)?")
VALUE_RE = re.compile(r"^(const|var)\s+([A-Za-z_]\w*)")
GROUP_START_RE = re.compile(r"^(type|const|var)\s*\(\s*$")
GROUP_ITEM_RE = re.compile(r"^\s+([A-Za-z_]\w*)\b(?:\s+(struct|interface)\b)?")

IO_CALLS = {
    "os.Open": "read", "os.ReadFile": "read", "ioutil.ReadFile": "read",
    "os.ReadDir": "read", "ioutil.ReadAll": "read", "io.ReadAll": "read",
    "os.Create": "write", "os.WriteFile": "write", "ioutil.WriteFile": "write",
    "os.OpenFile": "write", "os.Remove": "write", "os.MkdirAll": "write",
    "http.Get": "network", "http.Post": "network", "net.Dial": "network",
    "http.ListenAndServe": "network", "sql.Open": "network",
}


def parse_go(path, text):
    module = new_module(path, "go", text)
    lines = text.splitlines()
    code, with_strings, comments = strip_c_like(text)
    index = LineIndex(text)
    package = PACKAGE_RE.search(code)
    module.package = package.group(1) if package else ""
    if package:
        module.doc = leading_comment(lines, index.line_of(package.start()))
    module.imports, import_lines = _imports(with_strings, index)
    module.symbols = _symbols(code, lines, index)
    module.refs = extract_refs(code, KEYWORDS, import_lines)
    module.todos = find_todos(comments)
    module.file_io = file_io_from_refs(module.refs, lines, IO_CALLS)
    if module.package == "main" and module.symbol_named("main"):
        module.is_entry = True
        module.entry_reason = "Go `package main` with `func main()`"
    return module


def _imports(text, index):
    found, covered = [], set()
    for match in IMPORT_SINGLE_RE.finditer(text):
        line = index.line_of(match.start())
        found.append(Import(match.group(2), line, alias=match.group(1) or ""))
        covered.add(line)
    for block in IMPORT_BLOCK_RE.finditer(text):
        first = index.line_of(block.start())
        for offset, raw in enumerate(text[block.start():block.end()].splitlines()):
            covered.add(first + offset)
            match = IMPORT_LINE_RE.match(raw)
            if match:
                found.append(Import(match.group(2), first + offset, alias=match.group(1) or ""))
    return sorted(found, key=lambda imp: imp.line), covered


def _exported(name):
    return name[:1].isupper()


def _make(kind, name, number, code, lines, index, parent=""):
    end = block_end_line(code, index.offset_of(number), index)
    body = "\n".join(code.splitlines()[number - 1:end])
    return Symbol(
        name=name, kind=kind, line=number, end_line=end, exported=_exported(name),
        doc=leading_comment(lines, number)[:500], parent=parent,
        signature=lines[number - 1].strip(), complexity=complexity_of(body),
    )


def _symbols(code, lines, index):
    symbols = []
    group = None
    for number, line in enumerate(code.splitlines(), 1):
        if group:
            if line.startswith(")"):
                group = None
                continue
            item = GROUP_ITEM_RE.match(line)
            if item and line.startswith(("\t", "    ")) and not line.startswith(("\t\t", "        ")):
                kind = item.group(2) if group == "type" else group
                kind = (kind or "type") if group == "type" else "const"
                symbols.append(_make(kind, item.group(1), number, code, lines, index))
            continue
        symbol = _top_level(line, number, code, lines, index)
        if symbol:
            symbols.append(symbol)
            continue
        start = GROUP_START_RE.match(line)
        if start:
            group = start.group(1)
    return symbols


def _top_level(line, number, code, lines, index):
    match = METHOD_RE.match(line)
    if match:
        return _make("method", match.group(2), number, code, lines, index, parent=match.group(1))
    match = FUNC_RE.match(line)
    if match:
        return _make("function", match.group(1), number, code, lines, index)
    match = TYPE_RE.match(line)
    if match and not GROUP_START_RE.match(line):
        return _make(match.group(2) or "type", match.group(1), number, code, lines, index)
    match = VALUE_RE.match(line)
    if match and not GROUP_START_RE.match(line):
        return _make("const", match.group(2), number, code, lines, index)
    return None
