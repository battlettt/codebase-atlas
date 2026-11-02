"""Regex-based parser for TypeScript and JavaScript."""
import os
import re

from ..model import Import, Symbol
from .common import (
    LineIndex, block_end_line, complexity_of, extract_refs, file_io_from_refs,
    find_todos, leading_comment, new_module, strip_c_like,
)

KEYWORDS = {
    "abstract", "as", "async", "await", "break", "case", "catch", "class", "const",
    "constructor", "continue", "debugger", "declare", "default", "delete", "do",
    "else", "enum", "export", "extends", "false", "finally", "for", "from",
    "function", "get", "if", "implements", "import", "in", "instanceof",
    "interface", "is", "keyof", "let", "module", "namespace", "new", "null",
    "of", "private", "protected", "public", "readonly", "require", "return",
    "set", "static", "super", "switch", "this", "throw", "true", "try", "type",
    "typeof", "undefined", "var", "void", "while", "with", "yield", "string",
    "number", "boolean", "any", "unknown", "never", "object", "symbol",
    "override", "satisfies", "infer",
}

IMPORT_FROM_RE = re.compile(r"\bimport\s+(?:type\s+)?([\w$*{}\s,]+?)\s+from\s*(['\"])([^'\"\n]+)\2")
SIDE_EFFECT_RE = re.compile(r"^[ \t]*import\s*(['\"])([^'\"\n]+)\1", re.M)
EXPORT_FROM_RE = re.compile(
    r"\bexport\s+(?:type\s+)?(\*(?:\s+as\s+[\w$]+)?|\{[^}]*\})\s*from\s*(['\"])([^'\"\n]+)\2")
REQUIRE_RE = re.compile(
    r"(?:\b(?:const|let|var)\s+([\w$]+|\{[^}]*\})\s*=\s*)?\brequire\(\s*(['\"])([^'\"\n]+)\2\s*\)")
DYNAMIC_IMPORT_RE = re.compile(r"\bimport\(\s*(['\"])([^'\"\n]+)\1\s*\)")
EXPORT_LIST_RE = re.compile(r"^export\s*\{([^}]*)\}\s*;?\s*$", re.M)
EXPORT_DEFAULT_NAME_RE = re.compile(r"^export\s+default\s+([A-Za-z_$][\w$]*)\s*;?\s*$", re.M)
CJS_EXPORTS_RE = re.compile(r"\bmodule\.exports\s*=\s*\{([^}]*)\}")
CJS_EXPORT_ONE_RE = re.compile(r"\b(?:module\.)?exports\.([\w$]+)\s*=")

_PREFIX = r"^(export\s+)?(default\s+)?(?:declare\s+)?"
DEF_PATTERNS = [
    ("function", re.compile(_PREFIX + r"(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)")),
    ("class", re.compile(_PREFIX + r"(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")),
    ("interface", re.compile(_PREFIX + r"interface\s+([A-Za-z_$][\w$]*)")),
    ("type", re.compile(_PREFIX + r"type\s+([A-Za-z_$][\w$]*)\s*(?:<[^=]*>)?\s*=")),
    ("enum", re.compile(_PREFIX + r"(?:const\s+)?enum\s+([A-Za-z_$][\w$]*)")),
    ("function", re.compile(
        _PREFIX + r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?"
        r"(?:function\b|(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::\s*[^=]+?)?=>)")),
    ("const", re.compile(_PREFIX + r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)")),
]
METHOD_RE = re.compile(
    r"^\s+((?:(?:public|private|protected|static|async|override|get|set|readonly)\s+)*)"
    r"\*?([A-Za-z_$][\w$]*)\s*(?:<[^>()]*>)?\s*\(")

IO_CALLS = {
    "readFileSync": "read", "readFile": "read", "createReadStream": "read",
    "readdirSync": "read", "readdir": "read", "localStorage.getItem": "read",
    "writeFileSync": "write", "writeFile": "write", "appendFileSync": "write",
    "appendFile": "write", "createWriteStream": "write", "mkdirSync": "write",
    "unlinkSync": "write", "localStorage.setItem": "write",
    "fetch": "network", "axios.get": "network", "axios.post": "network",
    "http.request": "network", "https.request": "network",
}


def parse_typescript(path, text):
    language = "javascript" if path.endswith((".js", ".jsx", ".mjs", ".cjs")) else "typescript"
    module = new_module(path, language, text)
    lines = text.splitlines()
    code, with_strings, comments = strip_c_like(text)
    index = LineIndex(text)
    module.imports, import_lines = _imports(with_strings, index)
    module.symbols = _symbols(code, lines, index)
    module.default_export = _apply_export_lists(code, module.symbols)
    module.refs = extract_refs(code, KEYWORDS, import_lines)
    module.todos = find_todos(comments)
    module.file_io = file_io_from_refs(module.refs, lines, IO_CALLS)
    module.doc = _module_doc(lines)
    return module


def _module_doc(lines):
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#!"):
            continue
        if stripped.startswith(("//", "/*")):
            end = number
            while end < len(lines) and lines[end - 1].strip() and not lines[end - 1].strip().endswith("*/") \
                    and lines[end].strip().startswith(("//", "*")):
                end += 1
            return leading_comment(lines, end + 1)
        return ""
    return ""


def _span_lines(index, match):
    return range(index.line_of(match.start()), index.line_of(match.end() - 1) + 1)


def _imports(text, index):
    found, covered = [], set()
    for match in IMPORT_FROM_RE.finditer(text):
        names, alias = parse_clause(match.group(1))
        found.append(Import(match.group(3), index.line_of(match.start()), names=names, alias=alias))
        covered.update(_span_lines(index, match))
    for match in EXPORT_FROM_RE.finditer(text):
        clause = match.group(1)
        if clause.startswith("*"):
            alias_match = re.search(r"as\s+([\w$]+)", clause)
            names, alias = ([], alias_match.group(1)) if alias_match else ([("*", "*")], "")
        else:
            names, alias = parse_clause(clause)
        found.append(Import(match.group(3), index.line_of(match.start()), names=names, alias=alias))
        covered.update(_span_lines(index, match))
    for match in SIDE_EFFECT_RE.finditer(text):
        found.append(Import(match.group(2), index.line_of(match.start())))
        covered.update(_span_lines(index, match))
    for match in REQUIRE_RE.finditer(text):
        binding = match.group(1) or ""
        names, alias = parse_clause(binding) if binding.startswith("{") else ([], binding)
        found.append(Import(match.group(3), index.line_of(match.start()), names=names, alias=alias))
        covered.update(_span_lines(index, match))
    for match in DYNAMIC_IMPORT_RE.finditer(text):
        found.append(Import(match.group(2), index.line_of(match.start())))
    return sorted(found, key=lambda imp: imp.line), covered


def parse_clause(clause):
    """Parse `def, { a as b, c }` or `* as ns` into (names, namespace alias)."""
    names, alias = [], ""
    clause = clause.strip()
    brace = re.search(r"\{([^}]*)\}", clause)
    if brace:
        for part in brace.group(1).split(","):
            part = re.sub(r"^type\s+", "", part.strip())
            if not part:
                continue
            original, _, local = part.partition(" as ")
            names.append((original.strip(), (local or original).strip()))
        clause = clause[:brace.start()] + clause[brace.end():]
    star = re.search(r"\*\s*as\s+([\w$]+)", clause)
    if star:
        alias = star.group(1)
        clause = clause[:star.start()] + clause[star.end():]
    default = clause.replace(",", " ").split()
    if default:
        names.append(("default", default[0]))
    return names, alias


def _symbols(code, lines, index):
    symbols = []
    code_lines = code.splitlines()
    for number, line in enumerate(code_lines, 1):
        if not line or line[0].isspace():
            continue
        for kind, pattern in DEF_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            start = index.offset_of(number)
            end = block_end_line(code, start, index)
            body = "\n".join(code_lines[number - 1:end])
            symbol = Symbol(
                name=match.group(3), kind=kind, line=number, end_line=end,
                exported=bool(match.group(1)), doc=leading_comment(lines, number)[:500],
                signature=lines[number - 1].strip(), complexity=complexity_of(body),
            )
            if match.group(2):
                symbol.signature = "default " + symbol.signature
            symbols.append(symbol)
            if kind == "class":
                symbols.extend(_methods(symbol, code_lines, lines))
            break
    return symbols


def _methods(cls, code_lines, lines):
    methods = []
    depth = 0
    for number in range(cls.line, cls.end_line + 1):
        line = code_lines[number - 1]
        if depth == 1:
            match = METHOD_RE.match(line)
            if match and match.group(2) not in KEYWORDS - {"constructor", "get", "set"}:
                modifiers = match.group(1)
                methods.append(Symbol(
                    name=match.group(2), kind="method", line=number, end_line=number,
                    exported=cls.exported and "private" not in modifiers and not match.group(2).startswith("#"),
                    doc=leading_comment(lines, number)[:500], parent=cls.name,
                    signature=lines[number - 1].strip(),
                ))
        depth += line.count("{") - line.count("}")
    for method, following in zip(methods, methods[1:] + [None]):
        method.end_line = (following.line - 1) if following else max(method.line, cls.end_line - 1)
    return methods


def _apply_export_lists(code, symbols):
    by_name = {s.name: s for s in symbols if not s.parent}
    exported = set()
    for match in EXPORT_LIST_RE.finditer(code):
        exported.update(part.strip().split(" as ")[0].strip() for part in match.group(1).split(","))
    for match in CJS_EXPORTS_RE.finditer(code):
        exported.update(part.split(":")[0].strip() for part in match.group(1).split(","))
    exported.update(CJS_EXPORT_ONE_RE.findall(code))
    for name in exported:
        if name in by_name:
            by_name[name].exported = True
    default = ""
    match = EXPORT_DEFAULT_NAME_RE.search(code)
    if match:
        default = match.group(1)
    for symbol in symbols:
        if symbol.signature.startswith("default "):
            default = symbol.name
    if default in by_name:
        by_name[default].exported = True
    return default


def is_index_file(path):
    return os.path.splitext(os.path.basename(path))[0] == "index"
