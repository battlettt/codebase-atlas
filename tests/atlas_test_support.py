"""Shared helpers for the plain-assert test suite (works with or without pytest)."""
import io
import os
import shutil
import sys
import tempfile
import traceback
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "examples", "sample-repo")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from codebase_atlas.atlas import build_atlas  # noqa: E402
from codebase_atlas.cli import main as cli_main  # noqa: E402

_CACHE = {}


def sample_atlas():
    """Build the sample repo atlas once per process (treat as read-only)."""
    if "sample" not in _CACHE:
        _CACHE["sample"] = build_atlas(SAMPLE)
    return _CACHE["sample"]


def self_atlas():
    if "self" not in _CACHE:
        _CACHE["self"] = build_atlas(ROOT)
    return _CACHE["self"]


@contextmanager
def temp_repo(files=None, copy_sample=False):
    """Yield a temp directory containing `files` ({relpath: text or bytes})."""
    base = tempfile.mkdtemp(prefix="atlas-test-")
    root = os.path.join(base, "repo")
    try:
        if copy_sample:
            shutil.copytree(SAMPLE, root)
        else:
            os.makedirs(root)
        for rel, content in (files or {}).items():
            write_file(root, rel, content)
        yield root
    finally:
        shutil.rmtree(base, ignore_errors=True)


def write_file(root, rel, content):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(path, mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as handle:
        handle.write(content)


def run_cli(*argv):
    """Run the CLI in-process; return (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = cli_main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def run_module_tests(namespace):
    """Run every `test_*` function in a module namespace; return (passed, failed)."""
    passed = failed = 0
    for name in sorted(namespace):
        func = namespace[name]
        if not (name.startswith("test_") and callable(func)):
            continue
        try:
            func()
            passed += 1
        except Exception:  # noqa: BLE001 - report every failure, keep going
            failed += 1
            print(f"FAIL {namespace.get('__name__', '?')}.{name}")
            traceback.print_exc()
    return passed, failed


def main_for(namespace):
    passed, failed = run_module_tests(namespace)
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
