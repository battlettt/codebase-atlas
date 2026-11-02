"""Start-here reading order: README, entry points, dependencies before dependents."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import build_atlas, main_for, sample_atlas, self_atlas, temp_repo  # noqa: E402

from codebase_atlas.analysis.reading_order import reading_order  # noqa: E402


def assert_valid_order(atlas, steps):
    """No module appears before its dependencies unless it is an entry point
    or the step explicitly says it is part of a dependency cycle."""
    modules = [s for s in steps if s.kind == "module"]
    paths = [s.target for s in modules]
    assert sorted(paths) == sorted(atlas.modules), "every module exactly once"
    position = {p: i for i, p in enumerate(paths)}
    for step in modules:
        if atlas.modules[step.target].is_entry or "cycle" in step.reason:
            continue
        for dep in atlas.graph.dependencies(step.target):
            dep_step = modules[position[dep]]
            if "cycle" in dep_step.reason:
                continue
            assert position[dep] < position[step.target], f"{dep} must precede {step.target}"


def test_readme_first_then_entry_points():
    atlas = sample_atlas()
    steps = reading_order(atlas)
    assert steps[0].target == "README.md" and steps[0].kind == "doc"
    entries = [s.target for s in steps[1:4]]
    assert sorted(entries) == ["go/cmd/shipper/main.go", "main.py", "web/src/index.ts"]
    assert all(s.reason.startswith("Entry point") for s in steps[1:4])


def test_sample_order_is_valid_and_every_step_has_a_reason():
    atlas = sample_atlas()
    steps = reading_order(atlas)
    assert_valid_order(atlas, steps)
    assert all(s.reason and len(s.reason.splitlines()) == 1 for s in steps)


def test_known_sequence_in_sample():
    paths = [s.target for s in reading_order(sample_atlas())]
    assert paths.index("inventory/models.py") < paths.index("inventory/store.py") < paths.index("inventory/report.py")
    assert paths.index("web/src/types.ts") < paths.index("web/src/api.ts") < paths.index("web/src/cart.ts")


def test_tests_come_after_production_code():
    atlas = sample_atlas()
    paths = [s.target for s in reading_order(atlas) if s.kind == "module"]
    first_test = min(paths.index(p) for p in paths if atlas.roles[p][0] == "test")
    assert all(atlas.roles[p][0] == "test" for p in paths[first_test:])


def test_self_analysis_order_is_valid():
    atlas = self_atlas()
    assert_valid_order(atlas, reading_order(atlas))


def test_cycles_do_not_hang_and_are_labelled():
    files = {
        "a.py": "from b import g\n\ndef f():\n    return g()\n",
        "b.py": "from a import f\n\ndef g():\n    return f()\n",
        "c.py": "from a import f\n\nf()\n",
    }
    with temp_repo(files) as root:
        atlas = build_atlas(root)
        steps = reading_order(atlas)
        assert_valid_order(atlas, steps)
        assert any("cycle" in s.reason for s in steps)
        assert [s.target for s in steps][-1] == "c.py"


if __name__ == "__main__":
    main_for(globals())
