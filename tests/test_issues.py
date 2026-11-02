"""Good-first-issue ranking with printed reasoning."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import SAMPLE, build_atlas, main_for, run_cli, sample_atlas, temp_repo  # noqa: E402

from codebase_atlas.analysis.issues import find_issues  # noqa: E402
from codebase_atlas.analysis.roles import is_test_path  # noqa: E402


def test_todo_and_fixme_rank_at_the_top():
    issues = find_issues(sample_atlas())
    top = [(i.kind, i.path, i.line) for i in issues[:2]]
    assert top == [("todo", "inventory/store.py", 10), ("todo", "web/src/cart.ts", 14)]


def test_ranking_is_sorted_and_every_issue_has_reasons():
    issues = find_issues(sample_atlas(), limit=50)
    scores = [i.score for i in issues]
    assert scores == sorted(scores, reverse=True)
    for issue in issues:
        assert issue.reasons and all(r[0] in "+-" for r in issue.reasons)
        assert sum(int(r.split()[0]) for r in issue.reasons) == issue.score


def test_expected_candidates_present_and_tests_excluded():
    issues = find_issues(sample_atlas(), limit=50)
    titles = {(i.kind, i.path) for i in issues}
    assert ("docstring", "inventory/models.py") in titles  # make_item has no docstring
    assert ("unit-test", "web/src/api.ts") in titles  # nothing tests api.ts
    assert ("unit-test", "inventory/store.py") not in titles  # tests/test_store.py covers it
    assert not any(is_test_path(i.path) for i in issues)


def test_isolation_beats_coupling():
    hub_users = "".join(f"from hub import h{i}\n" for i in range(9))
    files = {
        "lonely.py": "def solo():\n    # TODO: add caching\n    return 1\n",
        "hub.py": "".join(f"def h{i}():\n    return {i}\n" for i in range(9)) + "# TODO: split this module\n",
    }
    files.update({f"user{i}.py": hub_users + f"h{i}()\n" for i in range(9)})
    with temp_repo(files) as root:
        issues = [i for i in find_issues(build_atlas(root), limit=100) if i.kind == "todo"]
        assert [i.path for i in issues] == ["lonely.py", "hub.py"]
        assert any("highly connected" in r for r in issues[1].reasons)


def test_cli_issues_prints_reasoning():
    code, out, _ = run_cli("issues", SAMPLE, "--limit", "3")
    assert code == 0 and " 1. [" in out and " 3. [" in out and " 4. [" not in out
    assert "Resolve TODO" in out and "+50" in out and "inventory/store.py:10" in out


if __name__ == "__main__":
    main_for(globals())
