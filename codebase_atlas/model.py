"""Plain data records shared by the parsing, graph, and analysis layers."""
from dataclasses import dataclass, field

TYPE_KINDS = {"class", "interface", "type", "struct", "enum"}


@dataclass
class Symbol:
    name: str
    kind: str  # function, method, class, interface, type, struct, enum, const
    line: int
    end_line: int
    exported: bool = True
    doc: str = ""
    parent: str = ""  # enclosing class or receiver type, for methods
    signature: str = ""
    complexity: int = 1

    @property
    def length(self):
        return self.end_line - self.line + 1

    @property
    def qualified_name(self):
        return f"{self.parent}.{self.name}" if self.parent else self.name


@dataclass
class Import:
    target: str  # module specifier as written in the source
    line: int
    names: list = field(default_factory=list)  # (imported_name, local_name)
    alias: str = ""  # namespace binding: `import x as y`, `* as y`, Go package
    level: int = 0  # Python relative import level


@dataclass
class Ref:
    name: str  # dotted identifier, e.g. "report.build_report"
    line: int
    is_call: bool


@dataclass
class Todo:
    line: int
    tag: str
    text: str


@dataclass
class FileIO:
    line: int
    mode: str  # read, write, network
    call: str
    snippet: str


@dataclass
class ModuleInfo:
    path: str  # repo-relative, forward slashes
    language: str
    lines: int
    sha1: str
    doc: str = ""
    package: str = ""  # Go package name
    default_export: str = ""  # TypeScript default export name
    symbols: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    refs: list = field(default_factory=list)
    todos: list = field(default_factory=list)
    file_io: list = field(default_factory=list)
    is_entry: bool = False
    entry_reason: str = ""

    def top_level_symbols(self):
        return [s for s in self.symbols if not s.parent]

    def symbol_named(self, name):
        for symbol in self.symbols:
            if symbol.name == name and not symbol.parent:
                return symbol
        return None
