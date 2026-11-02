"""Dependency graph edges, reasons, resolution, and re-export following."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import build_atlas, main_for, sample_atlas, temp_repo  # noqa: E402


def _reasons(atlas, src, dst):
    edge = atlas.graph.edges.get((src, dst))
    assert edge is not None, f"missing edge {src} -> {dst}"
    return set(edge.reasons)


def test_python_edges_with_reasons():
    atlas = sample_atlas()
    assert _reasons(atlas, "main.py", "inventory/report.py") == {"import", "call"}
    assert _reasons(atlas, "inventory/report.py", "inventory/store.py") == {"import", "call"}
    assert _reasons(atlas, "inventory/store.py", "inventory/models.py") == {"import", "call", "shared type"}
    assert _reasons(atlas, "tests/test_store.py", "inventory/models.py") == {"import", "shared type"}


def test_typescript_edges_with_reasons():
    atlas = sample_atlas()
    assert _reasons(atlas, "web/src/index.ts", "web/src/cart.ts") == {"import", "call", "shared type"}
    assert _reasons(atlas, "web/src/cart.ts", "web/src/api.ts") == {"import", "call"}
    assert _reasons(atlas, "web/src/api.ts", "web/src/types.ts") == {"import", "shared type"}


def test_go_edges_package_import_and_same_package_calls():
    atlas = sample_atlas()
    assert _reasons(atlas, "go/cmd/shipper/main.go", "go/internal/rates/rates.go") == {"import", "call"}
    assert _reasons(atlas, "go/cmd/shipper/main.go", "go/internal/rates/table.go") == {"import", "call"}
    assert _reasons(atlas, "go/internal/rates/rates.go", "go/internal/rates/table.go") == {"call"}


def test_use_evidence_lines_are_exact():
    atlas = sample_atlas()
    edge = atlas.graph.edges[("inventory/report.py", "inventory/store.py")]
    assert edge.import_lines == [2]
    assert {(u.symbol, u.line, u.reason) for u in edge.uses} == {
        ("load_items", 7, "call"), ("low_stock", 10, "call")}


def test_no_edges_to_external_packages():
    atlas = sample_atlas()
    for edge in atlas.graph.edges.values():
        assert edge.dst in atlas.modules and edge.src in atlas.modules
    assert "json" in atlas.graph.externals["inventory/store.py"]
    assert "fs" in atlas.graph.externals["web/src/api.ts"]
    assert "strconv" in atlas.graph.externals["go/cmd/shipper/main.go"]


def test_python_reexport_is_followed_to_the_defining_module():
    files = {
        "pkg/__init__.py": "from .core import Engine\n",
        "pkg/core.py": "class Engine:\n    pass\n",
        "app.py": "from pkg import Engine\n\ndef run():\n    return Engine()\n",
    }
    with temp_repo(files) as root:
        atlas = build_atlas(root)
        assert _reasons(atlas, "app.py", "pkg/core.py") == {"shared type"}
        assert "import" in _reasons(atlas, "app.py", "pkg/__init__.py")


def test_typescript_barrel_export_star():
    files = {
        "src/lib/math.ts": "export function sum(a: number, b: number) { return a + b; }\n",
        "src/lib/index.ts": "export * from './math';\n",
        "src/main.ts": "import { sum } from './lib';\nconsole.log(sum(1, 2));\n",
        "src/esm.ts": "import { sum } from './lib/math.js';\nsum(3, 4);\n",
    }
    with temp_repo(files) as root:
        atlas = build_atlas(root)
        assert _reasons(atlas, "src/main.ts", "src/lib/index.ts") == {"import"}
        assert _reasons(atlas, "src/main.ts", "src/lib/math.ts") == {"call"}
        assert _reasons(atlas, "src/esm.ts", "src/lib/math.ts") == {"import", "call"}


def test_stdlib_name_does_not_bind_to_nested_package_module():
    files = {
        "tool/__init__.py": "",
        "tool/report/__init__.py": "",
        "tool/report/html.py": "def page():\n    return 1\n",
        "tool/cli.py": "import html\n\ndef go():\n    return html.escape('x')\n",
    }
    with temp_repo(files) as root:
        atlas = build_atlas(root)
        assert atlas.graph.dependencies("tool/cli.py") == []
        assert "html" in atlas.graph.externals["tool/cli.py"]


def test_src_layout_resolves_through_source_root():
    files = {
        "src/shop/__init__.py": "",
        "src/shop/money.py": "def cents(x):\n    return int(x * 100)\n",
        "tests/test_money.py": "from shop.money import cents\n\ndef test_it():\n    assert cents(1) == 100\n",
    }
    with temp_repo(files) as root:
        atlas = build_atlas(root)
        assert _reasons(atlas, "tests/test_money.py", "src/shop/money.py") == {"import", "call"}


def test_namespace_and_module_attribute_calls():
    files = {
        "util/helpers.py": "def slug(text):\n    return text.lower()\n",
        "util/__init__.py": "",
        "a.py": "import util.helpers\n\nutil.helpers.slug('X')\n",
        "b.py": "from util import helpers as h\n\nh.slug('Y')\n",
    }
    with temp_repo(files) as root:
        atlas = build_atlas(root)
        assert _reasons(atlas, "a.py", "util/helpers.py") == {"import", "call"}
        assert _reasons(atlas, "b.py", "util/helpers.py") == {"import", "call"}


if __name__ == "__main__":
    main_for(globals())
