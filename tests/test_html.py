"""Interactive HTML map: self-contained, offline, no remote references."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import SAMPLE, build_atlas, main_for, run_cli, sample_atlas, temp_repo  # noqa: E402

from codebase_atlas.analysis.dataflow import data_flow  # noqa: E402
from codebase_atlas.analysis.issues import find_issues  # noqa: E402
from codebase_atlas.analysis.reading_order import reading_order  # noqa: E402
from codebase_atlas.report.html import dependency_levels, layout, render_html  # noqa: E402

REMOTE_RE = re.compile(r"""(?:src|href)\s*=\s*["']?(?:https?:|//)|url\(\s*["']?(?:https?:|//)""", re.I)


def _render(atlas):
    return render_html(atlas, reading_order(atlas), data_flow(atlas), find_issues(atlas))


def _embedded(document):
    match = re.search(r'<script type="application/json" id="atlas-data">(.*?)</script>', document, re.S)
    assert match
    return json.loads(match.group(1))


def assert_offline(document):
    assert "http://" not in document and "https://" not in document
    assert not REMOTE_RE.search(document)
    assert not re.search(r"<(link|img|iframe)\b", document, re.I)
    assert not re.search(r"<script[^>]*\bsrc=", document, re.I)
    assert "@import" not in document and "url(http" not in document


def test_html_is_self_contained_and_offline():
    document = _render(sample_atlas())
    assert document.startswith("<!DOCTYPE html>")
    assert_offline(document)
    assert "<svg" in document and "<style>" in document and "<script>" in document


def test_html_embeds_every_module_edge_and_reading_step():
    atlas = sample_atlas()
    data = _embedded(_render(atlas))
    assert sorted(m["path"] for m in data["modules"]) == sorted(atlas.modules)
    assert len(data["edges"]) == len(atlas.graph.edges)
    assert data["reading"][0]["target"] == "README.md"
    cart = [m for m in data["modules"] if m["path"] == "web/src/cart.ts"][0]
    assert cart["summary"] and cart["dependencies"] and cart["todos"]
    assert data["flow"]["chains"] and data["issues"]


def test_hostile_repo_content_cannot_break_out_or_add_urls():
    files = {"evil.py": '"""</script><script>alert(1)</script> see https://evil.example/x.js"""\n'
                        'URL = "http://tracker.example/pixel.png"\n'}
    with temp_repo(files) as root:
        document = _render(build_atlas(root))
        assert_offline(document)
        assert document.count("<script") == 2 and document.count("</script>") == 2
        data = _embedded(document)
        assert "https://evil.example/x.js" in data["modules"][0]["doc"]  # preserved as data


def test_layout_puts_dependencies_left_of_dependents():
    atlas = sample_atlas()
    levels = dependency_levels(atlas.graph)
    positions, width, height = layout(atlas.graph)
    for (src, dst), _ in atlas.graph.edges.items():
        if levels[src] > levels[dst]:
            assert positions[dst][0] < positions[src][0]
    assert levels["web/src/types.ts"] == 0 and levels["web/src/index.ts"] == 3
    assert all(0 <= x < width and 0 <= y < height for x, y in positions.values())


def test_inline_javascript_parses_when_node_is_available():
    node = shutil.which("node")
    if not node:
        print("  (node not installed; skipping JS syntax check)")
        return
    script = re.findall(r"<script>(.*?)</script>", _render(sample_atlas()), re.S)[0]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(script)
    try:
        proc = subprocess.run([node, "--check", handle.name], capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
    finally:
        os.unlink(handle.name)


def test_cli_html_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "map.html")
        code, out, _ = run_cli("html", SAMPLE, "-o", target)
        assert code == 0 and "works offline" in out
        with open(target, encoding="utf-8") as handle:
            assert_offline(handle.read())


if __name__ == "__main__":
    main_for(globals())
