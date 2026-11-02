"""Scanner: file discovery, skipped directories, and messy-input resilience."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import build_atlas, main_for, temp_repo  # noqa: E402

from codebase_atlas.scanner import language_for, scan  # noqa: E402


def test_language_detection():
    assert language_for("a/b.py") == "python"
    assert language_for("x.tsx") == "typescript"
    assert language_for("x.mjs") == "javascript"
    assert language_for("main.go") == "go"
    assert language_for("app.min.js") is None
    assert language_for("README.md") is None


def test_skips_vendored_and_hidden_directories():
    files = {
        "src/app.py": "x = 1\n",
        "node_modules/lib/index.js": "module.exports = {}\n",
        "vendor/github.com/x/y.go": "package y\n",
        "__pycache__/app.cpython-312.py": "x = 1\n",
        ".git/hooks/pre-commit.py": "x = 1\n",
        ".hidden/tool.py": "x = 1\n",
        "build/out.js": "var a = 1;\n",
    }
    with temp_repo(files) as root:
        result = scan(root)
        assert [path for path, _ in result.sources] == ["src/app.py"], result.sources


def test_extra_exclude():
    with temp_repo({"a/x.py": "", "generated/y.py": ""}) as root:
        result = scan(root, extra_skip=["generated"])
        assert [p for p, _ in result.sources] == ["a/x.py"]


def test_unparseable_and_binary_files_become_warnings_not_crashes():
    files = {
        "good.py": '"""Fine."""\ndef ok():\n    return 1\n',
        "broken.py": "def broken(:\n    pass\n",
        "binary.py": b"\x00\x01\x02binary\x00",
        "weird.ts": "export function f( { unterminated `template\n",
        "empty.go": "",
        "py2.py": "print 'hello'\n",
    }
    with temp_repo(files) as root:
        atlas = build_atlas(root)
        assert "good.py" in atlas.modules
        assert "broken.py" not in atlas.modules
        assert "binary.py" not in atlas.modules
        assert "py2.py" not in atlas.modules
        assert len(atlas.warnings) == 3, atlas.warnings
        assert any("broken.py" in w and "could not parse" in w for w in atlas.warnings)
        assert any("binary.py" in w for w in atlas.warnings)
        # Regex parsers degrade gracefully rather than failing.
        assert "weird.ts" in atlas.modules and "empty.go" in atlas.modules


def test_empty_repository():
    with temp_repo({}) as root:
        atlas = build_atlas(root)
        assert atlas.modules == {} and atlas.warnings == []


if __name__ == "__main__":
    main_for(globals())
