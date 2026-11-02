"""Classify each module's architectural role from structure alone."""
import posixpath

from ..model import TYPE_KINDS

TEST_DIRS = {"tests", "test", "__tests__", "spec", "testdata"}
TEST_SUFFIXES = (
    "_test.py", "_test.go", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx",
    ".test.js", ".spec.js", ".test.jsx", ".spec.jsx",
)
CONFIG_WORDS = ("config", "settings", "constants", "conf")


def is_test_path(path):
    name = posixpath.basename(path)
    if name.startswith("test_") or name == "conftest.py" or name.endswith(TEST_SUFFIXES):
        return True
    return any(part in TEST_DIRS for part in path.split("/")[:-1])


def classify(module, fan_in, fan_out):
    """Return (role, reason) for one module."""
    path = module.path
    name = posixpath.splitext(posixpath.basename(path))[0].lower()
    top = module.top_level_symbols()
    if is_test_path(path):
        return "test", "test file (by name or tests/ directory)"
    if module.is_entry:
        return "entry point", module.entry_reason
    if name == "__init__":
        return "package interface", f"package __init__ re-exporting {fan_out} internal module(s)"
    if any(word in name for word in CONFIG_WORDS):
        return "configuration", f"file name '{name}' suggests configuration"
    if top and all(s.kind in TYPE_KINDS or s.kind == "const" for s in top) \
            and any(s.kind in TYPE_KINDS for s in top):
        types = ", ".join(s.name for s in top if s.kind in TYPE_KINDS)
        return "data model", f"defines only types and constants: {types}"
    if fan_in == 0 and fan_out == 0:
        return "isolated", "no internal imports and nothing imports it"
    if fan_in >= 3 and fan_out <= 1:
        return "shared utility", f"used by {fan_in} modules, depends on {fan_out}"
    if fan_out == 0:
        return "foundation", f"depends on no internal modules; used by {fan_in}"
    if fan_in == 0:
        return "top-level consumer", f"nothing imports it; depends on {fan_out} module(s)"
    return "core logic", f"used by {fan_in} module(s), depends on {fan_out}"


def assign_roles(atlas):
    for path, module in atlas.modules.items():
        atlas.roles[path] = classify(module, atlas.graph.fan_in(path), atlas.graph.fan_out(path))
    return atlas.roles
