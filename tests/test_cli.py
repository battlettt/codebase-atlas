"""End-to-end CLI runs on the sample repo and on this repository itself."""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import ROOT, SAMPLE, main_for, run_cli  # noqa: E402


def test_map_text_has_every_section():
    code, out, _ = run_cli("map", SAMPLE)
    assert code == 0
    for heading in ("Architecture (by directory)", "Dependency graph", "Data flow", "Start here: reading order"):
        assert heading in out
    assert "14 modules (go 4, python 6, typescript 4)" in out
    assert "main.py -> inventory/report.py -> inventory/store.py -> inventory/models.py" in out


def test_map_json_and_module_view():
    code, out, _ = run_cli("map", SAMPLE, "--json")
    data = json.loads(out)
    assert code == 0 and len(data["modules"]) == 14 and data["reading_order"][0]["target"] == "README.md"
    code, out, _ = run_cli("map", SAMPLE, "--module", "inventory/store.py")
    assert code == 0 and "load_items" in out and "TODO at line 10" in out
    code, _, err = run_cli("map", SAMPLE, "--module", "nope.py")
    assert code == 2 and "no module" in err


def test_json_outputs_parse():
    for argv in (["issues", SAMPLE, "--json"], ["impact", SAMPLE, "Item", "--json"],
                 ["ask", SAMPLE, "Where is load_items used?", "--json"]):
        code, out, _ = run_cli(*argv)
        assert code == 0, argv
        json.loads(out)


def test_missing_repo_is_an_error():
    code, _, err = run_cli("map", os.path.join(SAMPLE, "does-not-exist"))
    assert code == 2 and "not a directory" in err


def test_self_analysis_completes_for_every_command():
    code, out, err = run_cli("map", ROOT)
    assert code == 0 and "codebase_atlas/cli.py" in out
    assert "python" in out and "typescript" in out and "go" in out
    code, out, _ = run_cli("issues", ROOT)
    assert code == 0 and "Good first issues" in out
    code, out, _ = run_cli("impact", ROOT, "codebase_atlas/model.py")
    assert code == 0 and "codebase_atlas/graph.py" in out
    with tempfile.TemporaryDirectory() as tmp:
        snap = os.path.join(tmp, "self.json")
        assert run_cli("snapshot", ROOT, "-o", snap)[0] == 0
        code, out, _ = run_cli("drift", ROOT, "--against", snap)
        assert code == 0 and out.startswith("No drift")
        assert run_cli("html", ROOT, "-o", os.path.join(tmp, "self.html"))[0] == 0


def test_self_analysis_finds_cli_entry_point():
    code, out, _ = run_cli("map", ROOT, "--module", "codebase_atlas/cli.py")
    assert code == 0 and "entry point" in out and "console script" in out


def test_module_entry_point_runs_as_subprocess():
    proc = subprocess.run([sys.executable, "-m", "codebase_atlas", "issues", SAMPLE, "--limit", "2"],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "Resolve TODO" in proc.stdout
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "bin", "atlas"), "--version"],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0 and "codebase-atlas" in proc.stdout


if __name__ == "__main__":
    main_for(globals())
