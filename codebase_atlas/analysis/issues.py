"""Good-first-issue finder: small, isolated, well-scoped tasks for newcomers."""
from dataclasses import dataclass, field

from .roles import is_test_path


@dataclass
class Issue:
    title: str
    kind: str  # todo, docstring, tests, unit-test
    path: str
    line: int
    score: int
    reasons: list = field(default_factory=list)


def find_issues(atlas, limit=15):
    tested = _tested_modules(atlas)
    issues = []
    for path in sorted(atlas.modules):
        module = atlas.modules[path]
        if is_test_path(path):
            continue
        issues.extend(_todo_issues(module))
        issues.extend(_docstring_issues(module))
        if path not in tested and not module.is_entry:
            issues.extend(_test_issues(module))
    for issue in issues:
        _apply_modifiers(atlas, issue)
    issues.sort(key=lambda i: (-i.score, i.path, i.line))
    return issues[:limit]


def _tested_modules(atlas):
    tested = set()
    for path in atlas.modules:
        if is_test_path(path):
            tested.update(atlas.graph.dependencies(path))
    return tested


def _enclosing(module, line):
    best = None
    for symbol in module.symbols:
        if symbol.line <= line <= symbol.end_line and (best is None or symbol.length < best.length):
            best = symbol
    return best


def _todo_issues(module):
    out = []
    for todo in module.todos:
        issue = Issue(f"Resolve {todo.tag}: {todo.text or '(no description)'}", "todo",
                      module.path, todo.line, 50,
                      [f"+50 the {todo.tag} comment already describes the task"])
        symbol = _enclosing(module, todo.line)
        if symbol and symbol.complexity <= 3:
            issue.score += 5
            issue.reasons.append(f"+5 inside {symbol.qualified_name}(), which is simple (complexity {symbol.complexity})")
        out.append(issue)
    return out


def _docstring_issues(module):
    out = []
    for symbol in module.symbols:
        if not symbol.exported or symbol.doc or symbol.kind not in ("function", "class", "method", "interface", "struct"):
            continue
        if symbol.name.startswith("__") or symbol.name in ("constructor", "main"):
            continue
        out.append(Issue(f"Add a docstring/comment to {symbol.kind} {symbol.qualified_name}", "docstring",
                         module.path, symbol.line, 30,
                         [f"+30 public {symbol.kind} with no documentation; reading it is enough to start"]))
    return out


def _test_issues(module):
    candidates = [s for s in module.top_level_symbols()
                  if s.kind == "function" and s.exported and s.length <= 15 and s.complexity <= 3]
    if not candidates:
        return []
    smallest = min(candidates, key=lambda s: (s.length, s.complexity, s.line))
    issue = Issue(f"Write a first unit test for {smallest.name}()", "unit-test", module.path, smallest.line, 25,
                  ["+25 no test file imports this module"])
    if smallest.length <= 5:
        issue.score += 5
        issue.reasons.append(f"+5 {smallest.name}() is tiny ({smallest.length} lines, complexity {smallest.complexity})")
    else:
        issue.reasons.append(f"+0 {smallest.name}() is {smallest.length} lines, complexity {smallest.complexity}")
    return [issue]


def _apply_modifiers(atlas, issue):
    graph = atlas.graph
    module = atlas.modules[issue.path]
    links = graph.fan_in(issue.path) + graph.fan_out(issue.path)
    if links <= 1:
        issue.score += 15
        issue.reasons.append(f"+15 isolated module ({links} internal link(s)): little can break")
    elif links <= 3:
        issue.score += 8
        issue.reasons.append(f"+8 loosely coupled ({links} internal links)")
    elif links >= 8:
        issue.score -= 10
        issue.reasons.append(f"-10 highly connected ({links} internal links): changes ripple")
    if module.lines <= 80:
        issue.score += 10
        issue.reasons.append(f"+10 small file ({module.lines} lines) to read end to end")
    elif module.lines > 400:
        issue.score -= 10
        issue.reasons.append(f"-10 large file ({module.lines} lines)")
