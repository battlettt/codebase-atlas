"""Helpers shared by the language parsers."""
import bisect
import hashlib
import re

from ..model import FileIO, ModuleInfo, Ref, Todo

TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b[:\s-]*(.*)")
IDENT_CHAIN_RE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)(\s*\()?")


def new_module(path, language, text):
    return ModuleInfo(
        path=path,
        language=language,
        lines=len(text.splitlines()),
        sha1=hashlib.sha1(text.encode("utf-8", "replace")).hexdigest(),
    )


class LineIndex:
    """Map character offsets to 1-based line numbers."""

    def __init__(self, text):
        self.starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line_of(self, offset):
        return bisect.bisect_right(self.starts, offset)

    def offset_of(self, line):
        return self.starts[line - 1]


def _blank(segment):
    return "".join(ch if ch == "\n" else " " for ch in segment)


def _string_end(text, start, quote):
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            return i + 1
        if ch == "\n" and quote != "`":
            return i
        i += 1
    return len(text)


def strip_c_like(text):
    """Split C-like source into three same-length views.

    Returns (code, code_with_strings, comments): `code` has comments and
    string contents blanked, `code_with_strings` keeps strings, and
    `comments` keeps only comment text. Newlines are preserved everywhere
    so line numbers stay valid.
    """
    code, with_strings, comments = [], [], []
    i, n = 0, len(text)
    while i < n:
        ch, nxt = text[i], text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt in "/*":
            if nxt == "/":
                end = text.find("\n", i)
                end = n if end == -1 else end
            else:
                end = text.find("*/", i + 2)
                end = n if end == -1 else end + 2
            segment = text[i:end]
            code.append(_blank(segment))
            with_strings.append(_blank(segment))
            comments.append(segment)
        elif ch in "\"'`":
            end = _string_end(text, i, ch)
            segment = text[i:end]
            code.append(_blank(segment))
            with_strings.append(segment)
            comments.append(_blank(segment))
        else:
            end = i + 1
            code.append(ch)
            with_strings.append(ch)
            comments.append(_blank(ch))
        i = end
    return "".join(code), "".join(with_strings), "".join(comments)


def find_todos(comment_text):
    todos = []
    for lineno, line in enumerate(comment_text.splitlines(), 1):
        match = TODO_RE.search(line)
        if match:
            text = match.group(2).strip().rstrip("*/").strip()
            todos.append(Todo(lineno, match.group(1), text))
    return todos


def extract_refs(code, keywords, skip_lines=()):
    """Collect dotted identifiers (and whether they are called) per line."""
    refs = []
    skip = set(skip_lines)
    for lineno, line in enumerate(code.splitlines(), 1):
        if lineno in skip:
            continue
        for match in IDENT_CHAIN_RE.finditer(line):
            name = match.group(1)
            if name.split(".")[0] in keywords:
                continue
            refs.append(Ref(name, lineno, bool(match.group(2))))
    return refs


def leading_comment(lines, line_no):
    """Return the comment block directly above 1-based `line_no`."""
    collected = []
    index = line_no - 2
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped.startswith(("//", "/*", "*", "#")) or stripped.startswith("#!"):
            break
        collected.append(stripped)
        index -= 1
    return clean_comment("\n".join(reversed(collected)))


def clean_comment(raw):
    out = []
    for line in raw.splitlines():
        line = line.strip()
        for prefix in ("/**", "/*", "//", "#", "*"):
            if line.startswith(prefix):
                line = line[len(prefix):]
                break
        line = line.replace("*/", "").strip()
        if line:
            out.append(line)
    return " ".join(out)


def block_end_line(code, start, index):
    """Line where the declaration starting at offset `start` ends.

    Matches the first `{ ... }` block; a declaration with no block ends at
    the first `;` or newline outside parentheses.
    """
    depth = paren = 0
    opened = False
    for i in range(start, len(code)):
        ch = code[i]
        if ch in "([":
            paren += 1
        elif ch in ")]":
            paren -= 1
        elif ch == "{":
            depth += 1
            opened = True
        elif ch == "}":
            depth -= 1
            if opened and depth == 0:
                return index.line_of(i)
        elif not opened and paren <= 0 and ch in ";\n" and i > start:
            if ch == "\n" and code[start:i].rstrip().endswith(("=", "=>", ",", "|", "&")):
                continue
            return index.line_of(i)
    return index.line_of(len(code) - 1) if code else 1


def file_io_from_refs(refs, lines, table, mode_hook=None):
    """Match call refs against a {call_suffix: mode} table."""
    found = []
    for ref in refs:
        if not ref.is_call:
            continue
        for pattern, mode in table.items():
            if ref.name == pattern or ref.name.endswith("." + pattern):
                snippet = lines[ref.line - 1].strip() if ref.line <= len(lines) else ""
                if mode_hook:
                    mode = mode_hook(ref, snippet, mode)
                found.append(FileIO(ref.line, mode, ref.name, snippet[:160]))
                break
    return found


def complexity_of(code_segment):
    """Rough cyclomatic complexity for C-like code."""
    return 1 + len(re.findall(r"\b(?:if|for|while|case|catch|select)\b|&&|\|\||\?\?", code_segment))
