"""Find source files, docs, and manifests in a repository."""
import os
from dataclasses import dataclass, field

LANGUAGE_BY_EXT = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
}

DEFAULT_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", "vendor",
    "venv", ".venv", "env", ".env", "dist", "build", ".mypy_cache",
    ".pytest_cache", ".tox", ".idea", ".vscode", "site-packages",
    "coverage", ".next", "target",
}

MAX_FILE_BYTES = 1_000_000
MANIFEST_NAMES = {"go.mod", "package.json", "pyproject.toml"}


@dataclass
class ScanResult:
    root: str
    sources: list = field(default_factory=list)  # (relpath, language)
    docs: list = field(default_factory=list)  # markdown relpaths
    manifests: list = field(default_factory=list)  # go.mod etc relpaths
    skipped: list = field(default_factory=list)  # (relpath, reason)


def language_for(path):
    if path.endswith(".min.js"):
        return None
    return LANGUAGE_BY_EXT.get(os.path.splitext(path)[1].lower())


def scan(root, skip_dirs=None, extra_skip=()):
    """Walk `root`, pruning vendored and hidden directories."""
    skip = set(DEFAULT_SKIP_DIRS if skip_dirs is None else skip_dirs) | set(extra_skip)
    result = ScanResult(root=os.path.abspath(root))
    for dirpath, dirnames, filenames in os.walk(result.root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip and not d.startswith("."))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, result.root).replace(os.sep, "/")
            _classify(result, rel, full, name)
    return result


def _classify(result, rel, full, name):
    if name in MANIFEST_NAMES:
        result.manifests.append(rel)
    if name.lower().endswith(".md"):
        result.docs.append(rel)
        return
    language = language_for(name)
    if not language:
        return
    try:
        size = os.path.getsize(full)
    except OSError as error:
        result.skipped.append((rel, f"unreadable: {error}"))
        return
    if size > MAX_FILE_BYTES:
        result.skipped.append((rel, f"too large ({size} bytes)"))
        return
    result.sources.append((rel, language))


def read_text(full_path):
    """Return file text, or None when the file looks binary or unreadable."""
    try:
        with open(full_path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def find_readme(docs):
    """Pick the top-most README from a list of markdown paths."""
    readmes = [d for d in docs if os.path.basename(d).lower() == "readme.md"]
    return min(readmes, key=lambda d: (d.count("/"), d)) if readmes else None
