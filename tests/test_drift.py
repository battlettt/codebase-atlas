"""Snapshot / drift round trip: identical tree is clean, a change reports exactly that change."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import build_atlas, main_for, run_cli, temp_repo, write_file  # noqa: E402

from codebase_atlas.analysis.drift import compare_snapshots, make_snapshot, validate_snapshot  # noqa: E402


def _append(root, rel, text):
    with open(os.path.join(root, rel), "a", encoding="utf-8") as handle:
        handle.write(text)


def test_snapshot_is_deterministic_and_portable():
    with temp_repo(copy_sample=True) as root:
        first = make_snapshot(build_atlas(root))
        second = make_snapshot(build_atlas(root))
        assert first == second
        text = json.dumps(first)
        assert root not in text, "snapshots must not embed absolute paths"
        validate_snapshot(json.loads(text))


def test_identical_tree_reports_no_drift():
    with temp_repo(copy_sample=True) as root:
        snapshot = make_snapshot(build_atlas(root))
        assert compare_snapshots(snapshot, make_snapshot(build_atlas(root))).is_empty


def test_added_function_reports_exactly_that_change():
    with temp_repo(copy_sample=True) as root:
        before = make_snapshot(build_atlas(root))
        _append(root, "inventory/store.py", '\n\ndef restock(item, amount):\n    """Add stock."""\n    item.quantity += amount\n')
        drift = compare_snapshots(before, make_snapshot(build_atlas(root)))
        assert [c["path"] for c in drift.changed_modules] == ["inventory/store.py"]
        assert drift.changed_modules[0]["symbols_added"] == ["function restock"]
        assert drift.added_symbols == [("inventory/store.py", "function restock")]
        assert drift.removed_symbols == [] and drift.added_modules == [] and drift.removed_modules == []
        assert drift.added_edges == [] and drift.removed_edges == [] and drift.changed_edges == []


def test_added_and_removed_modules_and_dependencies():
    with temp_repo(copy_sample=True) as root:
        before = make_snapshot(build_atlas(root))
        os.remove(os.path.join(root, "web/src/index.ts"))
        write_file(root, "inventory/audit.py",
                   '"""Audit."""\nfrom inventory.store import low_stock\n\n\ndef audit(items):\n    return low_stock(items)\n')
        drift = compare_snapshots(before, make_snapshot(build_atlas(root)))
        assert drift.added_modules == ["inventory/audit.py"]
        assert drift.removed_modules == ["web/src/index.ts"]
        assert ("inventory/audit.py", "inventory/store.py", ["import", "call"]) in drift.added_edges
        assert ("web/src/index.ts", "web/src/cart.ts", ["import", "call", "shared type"]) in drift.removed_edges
        assert ("inventory/audit.py", "function audit") in drift.added_symbols


def test_changed_dependency_reasons():
    with temp_repo(copy_sample=True) as root:
        before = make_snapshot(build_atlas(root))
        _append(root, "main.py", "\n\ndef pick():\n    return report.build_report\n")
        drift = compare_snapshots(before, make_snapshot(build_atlas(root)))
        assert drift.changed_edges == [("main.py", "inventory/report.py", ["import", "call"],
                                        ["import", "call", "reference"])]


def test_validate_rejects_foreign_json():
    for bad in ({}, {"format": "other"}, {"format": "codebase-atlas-snapshot", "version": 99}, []):
        try:
            validate_snapshot(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_cli_snapshot_drift_round_trip():
    with temp_repo(copy_sample=True) as root:
        snap = os.path.join(os.path.dirname(root), "snap.json")
        code, out, _ = run_cli("snapshot", root, "-o", snap)
        assert code == 0 and os.path.exists(snap)
        code, out, _ = run_cli("drift", root, "--against", snap, "--exit-code")
        assert code == 0 and out.startswith("No drift")
        _append(root, "web/src/api.ts", "\nexport function countOrders(orders: Order[]): number { return orders.length; }\n")
        code, out, _ = run_cli("drift", root, "--against", snap, "--exit-code")
        assert code == 1
        assert "web/src/api.ts" in out and "function countOrders" in out
        code, out, _ = run_cli("drift", root, "--against", snap, "--json")
        data = json.loads(out)
        assert data["added_symbols"] == [["web/src/api.ts", "function countOrders"]]
        code, _, err = run_cli("drift", root, "--against", os.path.join(root, "README.md"))
        assert code == 2 and "cannot read snapshot" in err


if __name__ == "__main__":
    main_for(globals())
