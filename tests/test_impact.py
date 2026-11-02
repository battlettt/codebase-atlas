"""Change-impact analysis: reverse dependencies, reasons, transitive reach, risk."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import SAMPLE, main_for, run_cli, sample_atlas  # noqa: E402

from codebase_atlas.analysis.impact import analyze_impact, resolve_target  # noqa: E402


def _by_path(result):
    return {a.path: a for a in result.affected}


def test_file_impact_lists_known_dependents():
    result = analyze_impact(sample_atlas(), "inventory/models.py")
    affected = _by_path(result)
    assert {a.path for a in result.direct} == {"inventory/__init__.py", "inventory/store.py", "tests/test_store.py"}
    assert affected["inventory/report.py"].depth == 2
    assert affected["main.py"].via == ["inventory/store.py", "inventory/report.py", "main.py"]
    store_reasons = " | ".join(affected["inventory/store.py"].reasons)
    assert "imports models.py at line 5" in store_reasons
    assert "calls make_item() at line 13" in store_reasons
    assert result.tests == ["tests/test_store.py"]


def test_symbol_impact_with_line_level_reasons():
    result = analyze_impact(sample_atlas(), "load_items")
    assert result.kind == "symbol"
    assert [(p, s.line) for p, s in result.definitions] == [("inventory/store.py", 8)]
    direct = _by_path(result)["inventory/report.py"]
    assert direct.depth == 1 and direct.reasons[0].startswith("calls load_items() at line 7")
    assert "main.py" in {a.path for a in result.transitive}
    assert result.risk == "high" and "no test" in result.risk_reason


def test_type_impact_across_typescript():
    result = analyze_impact(sample_atlas(), "Order")
    assert {a.path for a in result.direct} == {"web/src/api.ts", "web/src/cart.ts"}
    assert "web/src/index.ts" in {a.path for a in result.transitive}
    assert "type changes ripple" in result.risk_reason


def test_go_symbol_impact():
    result = analyze_impact(sample_atlas(), "Quote")
    assert {a.path for a in result.direct} == {"go/cmd/shipper/main.go", "go/internal/rates/rates_test.go"}
    assert result.tests == ["go/internal/rates/rates_test.go"]


def test_method_impact_is_marked_possible():
    result = analyze_impact(sample_atlas(), "Item.total_value")
    report = _by_path(result)["inventory/report.py"]
    assert report.confidence == "possible" and "matched by method name only" in report.reasons[0]


def test_target_resolution_forms():
    atlas = sample_atlas()
    assert resolve_target(atlas, "./inventory/store.py") == ("file", ["inventory/store.py"])
    assert resolve_target(atlas, "store.py") == ("file", ["inventory/store.py"])
    assert resolve_target(atlas, "inventory.store") == ("file", ["inventory/store.py"])
    assert resolve_target(atlas, "does_not_exist") == (None, [])
    assert analyze_impact(atlas, "does_not_exist") is None


def test_leaf_module_has_low_risk():
    result = analyze_impact(sample_atlas(), "main.py")
    assert result.affected == [] and result.risk == "low"


def test_cli_impact_output_and_unknown_target():
    code, out, _ = run_cli("impact", SAMPLE, "inventory/store.py")
    assert code == 0 and "inventory/report.py" in out and "Risk:" in out
    code, out, _ = run_cli("impact", SAMPLE, "nope_not_here")
    assert code == 3 and "No file, module, or symbol" in out


if __name__ == "__main__":
    main_for(globals())
