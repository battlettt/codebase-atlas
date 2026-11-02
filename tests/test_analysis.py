"""Roles, module summaries, and data flow over the sample repo."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import main_for, sample_atlas  # noqa: E402

from codebase_atlas.analysis.dataflow import data_flow  # noqa: E402
from codebase_atlas.analysis.roles import is_test_path  # noqa: E402
from codebase_atlas.analysis.summaries import first_sentence, module_details, module_summary  # noqa: E402


def test_roles():
    roles = {p: r for p, (r, _) in sample_atlas().roles.items()}
    assert roles["main.py"] == "entry point"
    assert roles["web/src/index.ts"] == "entry point"
    assert roles["go/cmd/shipper/main.go"] == "entry point"
    assert roles["web/src/types.ts"] == "data model"
    assert roles["tests/test_store.py"] == "test"
    assert roles["go/internal/rates/rates_test.go"] == "test"
    assert roles["inventory/__init__.py"] == "package interface"


def test_is_test_path():
    assert is_test_path("tests/test_x.py") and is_test_path("pkg/x_test.go")
    assert is_test_path("src/a.spec.ts") and is_test_path("src/__tests__/a.js")
    assert not is_test_path("src/testing_utils.py") and not is_test_path("contest.py")


def test_module_summary_is_static_and_grounded():
    atlas = sample_atlas()
    summary = module_summary(atlas, "inventory/store.py")
    assert summary.startswith("Load and save inventory items from JSON files.")
    assert "load_items" in summary and "depends on models.py" in summary
    assert "used by report.py, test_store.py" in summary
    fallback = module_summary(atlas, "go/internal/rates/table.go")
    assert fallback.startswith("(no docstring) Defines LoadTable")


def test_module_details_structure():
    details = module_details(sample_atlas(), "web/src/cart.ts")
    assert details["role"] == "core logic"
    assert {d["path"] for d in details["dependencies"]} == {"web/src/api.ts", "web/src/types.ts"}
    assert details["todos"][0]["tag"] == "FIXME"
    assert any(s["name"] == "CartService.openTotal" for s in details["symbols"])


def test_first_sentence():
    assert first_sentence("One. Two.") == "One."
    assert first_sentence("") == ""
    assert first_sentence("word " * 100).endswith("...")


def test_data_flow_chains_shared_types_and_io():
    flow = data_flow(sample_atlas())
    assert ["main.py", "inventory/report.py", "inventory/store.py", "inventory/models.py"] in flow.chains
    assert ["web/src/index.ts", "web/src/cart.ts", "web/src/api.ts"] in flow.chains
    shared = {(p, n): users for p, n, _, users in flow.shared_types}
    assert shared[("web/src/types.ts", "Order")] == ["web/src/api.ts", "web/src/cart.ts"]
    assert ("inventory/store.py", "read", 11, "open") in flow.io
    assert ("go/internal/rates/table.go", "read", 11, "os.ReadFile") in flow.io
    calls = {(s, d): c for s, d, c in flow.calls}
    assert calls[("main.py", "inventory/report.py")] == [("build_report", 10)]


if __name__ == "__main__":
    main_for(globals())
