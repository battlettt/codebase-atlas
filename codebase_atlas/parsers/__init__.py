"""Language parsers. Each returns a ModuleInfo for one source file."""
from .go_parser import parse_go
from .python_parser import parse_python
from .typescript_parser import parse_typescript

PARSERS = {
    "python": parse_python,
    "typescript": parse_typescript,
    "javascript": parse_typescript,
    "go": parse_go,
}


def parse_source(path, language, text):
    """Parse one file. Raises on unparseable input; callers count warnings."""
    return PARSERS[language](path, text)
