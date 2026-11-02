"""One self-contained, offline HTML map: inline CSS, inline JS, plain SVG."""
import html
import json
import posixpath

from ..analysis.summaries import module_details

NODE_WIDTH = 180
NODE_HEIGHT = 34
COLUMN_GAP = 250
ROW_GAP = 52
MARGIN = 30


def dependency_levels(graph):
    """Column per module: 0 for foundations, 1 + deepest dependency otherwise."""
    levels, visiting = {}, set()

    def level(path):
        if path in levels:
            return levels[path]
        if path in visiting:  # cycle: treat the back edge as absent
            return 0
        visiting.add(path)
        deps = [d for d in graph.dependencies(path) if d != path]
        value = 1 + max((level(d) for d in deps), default=-1)
        visiting.discard(path)
        levels[path] = value
        return value

    for node in graph.nodes:
        level(node)
    return levels


def layout(graph):
    """Deterministic layered layout: {path: (x, y)} plus canvas size."""
    levels = dependency_levels(graph)
    columns = {}
    for path in sorted(graph.nodes, key=lambda p: (posixpath.dirname(p), p)):
        columns.setdefault(levels[path], []).append(path)
    positions = {}
    for column, paths in columns.items():
        for row, path in enumerate(paths):
            positions[path] = (MARGIN + column * COLUMN_GAP, MARGIN + row * ROW_GAP)
    width = MARGIN * 2 + NODE_WIDTH + COLUMN_GAP * max(columns, default=0)
    height = MARGIN * 2 + NODE_HEIGHT + ROW_GAP * max((len(p) - 1 for p in columns.values()), default=0)
    return positions, width, height


def build_payload(atlas, steps, flow, issues):
    positions, width, height = layout(atlas.graph)
    modules = []
    for path in sorted(atlas.modules):
        details = module_details(atlas, path)
        details["x"], details["y"] = positions[path]
        modules.append(details)
    return {
        "name": atlas.name,
        "stats": {"modules": len(atlas.modules), "edges": len(atlas.graph.edges),
                  "languages": atlas.language_counts(), "warnings": len(atlas.warnings)},
        "size": {"width": width, "height": height, "node_width": NODE_WIDTH, "node_height": NODE_HEIGHT},
        "modules": modules,
        "edges": [{"src": e.src, "dst": e.dst, "reasons": e.reason_list()} for e in atlas.graph.sorted_edges()],
        "reading": [{"target": s.target, "kind": s.kind, "reason": s.reason} for s in steps],
        "flow": {
            "chains": flow.chains,
            "shared_types": [{"path": p, "name": n, "line": l, "users": u} for p, n, l, u in flow.shared_types],
            "io": [{"path": p, "mode": m, "line": l, "call": c} for p, m, l, c in flow.io],
        },
        "issues": [{"title": i.title, "path": i.path, "line": i.line, "score": i.score, "reasons": i.reasons}
                   for i in issues],
    }


def embed_json(data):
    """JSON safe inside <script>: escape <, >, and / (also hides '://' literals)."""
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("/", "\\/")


def render_html(atlas, steps, flow, issues):
    payload = build_payload(atlas, steps, flow, issues)
    return (TEMPLATE
            .replace("__TITLE__", html.escape(f"Codebase Atlas: {atlas.name}"))
            .replace("__DATA__", embed_json(payload)))


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.4 system-ui, -apple-system, Segoe UI, sans-serif; color: #1d2330; background: #f5f6f8; }
header { display: flex; gap: 16px; align-items: center; padding: 10px 16px; background: #1d2330; color: #fff; }
header h1 { font-size: 16px; margin: 0; white-space: nowrap; }
header .stats { color: #b8c0d0; font-size: 12px; flex: 1; }
#search { width: 280px; padding: 6px 10px; border-radius: 6px; border: 0; font-size: 14px; }
main { display: grid; grid-template-columns: 1fr 420px; height: calc(100vh - 52px); }
#graph-wrap { position: relative; overflow: hidden; background: #fff; border-right: 1px solid #d9dde5; }
#graph { width: 100%; height: 100%; cursor: grab; user-select: none; }
#graph.dragging { cursor: grabbing; }
.node rect { fill: #eef2fb; stroke: #8a97b5; stroke-width: 1.2; rx: 6; }
.node text { font-size: 12px; fill: #1d2330; pointer-events: none; }
.node { cursor: pointer; }
.node.python rect { fill: #e8f1fb; stroke: #3b76b0; }
.node.typescript rect, .node.javascript rect { fill: #fdf6e3; stroke: #b08a2e; }
.node.go rect { fill: #e6f6f4; stroke: #2b8a7e; }
.node.entry rect { stroke-width: 2.6; }
.node.test rect { stroke-dasharray: 4 3; }
.node.selected rect { stroke: #d6336c; stroke-width: 3; }
.node.dim, .edge.dim { opacity: 0.15; }
.node.match rect { stroke: #d6336c; stroke-width: 2.4; }
.edge { fill: none; stroke: #9aa5bd; stroke-width: 1.2; }
.edge.hot { stroke: #d6336c; stroke-width: 2.2; }
.legend { position: absolute; left: 10px; bottom: 10px; background: rgba(255,255,255,.92); padding: 6px 10px; border: 1px solid #d9dde5; border-radius: 6px; font-size: 12px; }
.legend span { display: inline-block; width: 10px; height: 10px; margin: 0 4px 0 10px; border: 1px solid #555; }
aside { overflow: auto; background: #fbfbfd; }
nav { display: flex; border-bottom: 1px solid #d9dde5; position: sticky; top: 0; background: #fbfbfd; }
nav button { flex: 1; padding: 10px 4px; border: 0; background: none; cursor: pointer; font-size: 13px; border-bottom: 2px solid transparent; }
nav button.active { border-bottom-color: #d6336c; font-weight: 600; }
.panel { display: none; padding: 12px 16px; }
.panel.active { display: block; }
h2 { font-size: 15px; margin: 4px 0 8px; word-break: break-all; }
h3 { font-size: 13px; margin: 14px 0 6px; color: #4a5368; text-transform: uppercase; letter-spacing: .04em; }
ul { margin: 0; padding-left: 18px; }
li { margin: 3px 0; }
.muted { color: #6b7488; }
.pill { display: inline-block; padding: 1px 7px; border-radius: 10px; background: #e3e7f0; font-size: 11px; margin-right: 4px; }
a.link { color: #2456b3; cursor: pointer; text-decoration: none; }
a.link:hover { text-decoration: underline; }
code { font: 12px ui-monospace, Menlo, Consolas, monospace; background: #eef0f4; padding: 0 3px; border-radius: 3px; }
#results { margin-top: 6px; }
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <div class="stats" id="stats"></div>
  <input id="search" type="search" placeholder="Search modules and symbols..." autocomplete="off">
</header>
<main>
  <div id="graph-wrap">
    <svg id="graph" role="img" aria-label="Module dependency graph"></svg>
    <div class="legend">Python<span style="background:#e8f1fb"></span>TS/JS<span style="background:#fdf6e3"></span>Go<span style="background:#e6f6f4"></span> thick border = entry point, dashed = test. Arrows point to dependencies. Drag to pan, wheel to zoom.</div>
  </div>
  <aside>
    <nav>
      <button data-tab="details" class="active">Details</button>
      <button data-tab="reading">Reading order</button>
      <button data-tab="flow">Data flow</button>
      <button data-tab="issues">First issues</button>
    </nav>
    <section class="panel active" id="panel-details"><p class="muted">Click a module in the graph, or search above.</p><div id="results"></div></section>
    <section class="panel" id="panel-reading"></section>
    <section class="panel" id="panel-flow"></section>
    <section class="panel" id="panel-issues"></section>
  </aside>
</main>
<script type="application/json" id="atlas-data">__DATA__</script>
<script>
(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("atlas-data").textContent);
  var byPath = {};
  data.modules.forEach(function (m) { byPath[m.path] = m; });
  var svg = document.getElementById("graph");
  var W = data.size.node_width, H = data.size.node_height;
  var view = { x: 0, y: 0, w: Math.max(data.size.width, 400), h: Math.max(data.size.height, 300) };
  var selected = null;

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function link(path, label) {
    var a = el("a", label || path, "link");
    a.addEventListener("click", function () { select(path); });
    return a;
  }

  document.getElementById("title").textContent = "Codebase Atlas: " + data.name;
  var langs = Object.keys(data.stats.languages).map(function (k) { return k + " " + data.stats.languages[k]; }).join(", ");
  document.getElementById("stats").textContent = data.stats.modules + " modules (" + langs + "), " +
    data.stats.edges + " dependencies, " + data.stats.warnings + " warning(s)";

  function drawGraph() {
    var parts = ['<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#9aa5bd"></path></marker></defs>'];
    data.edges.forEach(function (e, i) {
      var a = byPath[e.src], b = byPath[e.dst];
      var x1 = a.x, y1 = a.y + H / 2, x2 = b.x + W, y2 = b.y + H / 2;
      if (b.x >= a.x) { x1 = a.x + W; x2 = b.x; }
      var mid = (x1 + x2) / 2;
      parts.push('<path class="edge" data-i="' + i + '" marker-end="url(#arrow)" d="M' + x1 + ',' + y1 +
        ' C' + mid + ',' + y1 + ' ' + mid + ',' + y2 + ' ' + x2 + ',' + y2 + '"><title>' +
        esc(e.src + " -> " + e.dst + ": " + e.reasons.join(", ")) + '</title></path>');
    });
    data.modules.forEach(function (m) {
      var cls = "node " + m.language + (m.entry ? " entry" : "") + (m.role === "test" ? " test" : "");
      var label = m.name.length > 24 ? m.name.slice(0, 23) + "\\u2026" : m.name;
      parts.push('<g class="' + cls + '" data-path="' + esc(m.path) + '" transform="translate(' + m.x + ',' + m.y + ')">' +
        '<rect width="' + W + '" height="' + H + '"></rect><text x="10" y="21">' + esc(label) + '</text><title>' +
        esc(m.path + " [" + m.role + "]") + '</title></g>');
    });
    svg.innerHTML = parts.join("");
    svg.querySelectorAll(".node").forEach(function (g) {
      g.addEventListener("click", function (ev) { ev.stopPropagation(); select(g.getAttribute("data-path")); });
    });
    applyView();
  }

  function applyView() { svg.setAttribute("viewBox", view.x + " " + view.y + " " + view.w + " " + view.h); }

  function select(path) {
    selected = path;
    svg.querySelectorAll(".node").forEach(function (g) {
      g.classList.toggle("selected", g.getAttribute("data-path") === path);
    });
    svg.querySelectorAll(".edge").forEach(function (p) {
      var e = data.edges[+p.getAttribute("data-i")];
      p.classList.toggle("hot", e.src === path || e.dst === path);
    });
    showTab("details");
    renderDetails(byPath[path]);
  }

  function section(panel, title) { panel.appendChild(el("h3", title)); var ul = el("ul"); panel.appendChild(ul); return ul; }

  function renderDetails(m) {
    var panel = document.getElementById("panel-details");
    panel.innerHTML = "";
    if (!m) { panel.appendChild(el("p", "Module not found.", "muted")); return; }
    panel.appendChild(el("h2", m.path));
    var meta = el("div");
    [m.language, m.role, m.lines + " lines"].forEach(function (t) { meta.appendChild(el("span", t, "pill")); });
    panel.appendChild(meta);
    panel.appendChild(el("p", m.summary));
    panel.appendChild(el("p", "Role: " + m.role_reason, "muted"));
    var syms = section(panel, "Symbols (" + m.symbols.length + ")");
    m.symbols.forEach(function (s) {
      var li = el("li"); li.appendChild(el("code", s.name));
      li.appendChild(document.createTextNode(" " + s.kind + ", line " + s.line + (s.doc ? " - " + s.doc : "")));
      syms.appendChild(li);
    });
    [["dependencies", "Depends on"], ["dependents", "Used by"]].forEach(function (pair) {
      var ul = section(panel, pair[1] + " (" + m[pair[0]].length + ")");
      m[pair[0]].forEach(function (d) {
        var li = el("li"); li.appendChild(link(d.path));
        li.appendChild(document.createTextNode(" - " + d.reasons.join(", ") + (d.symbols.length ? " (" + d.symbols.join(", ") + ")" : "")));
        ul.appendChild(li);
      });
    });
    if (m.externals.length) { var ex = section(panel, "External packages"); ex.appendChild(el("li", m.externals.join(", "))); }
    if (m.todos.length) { var td = section(panel, "TODO / FIXME"); m.todos.forEach(function (t) { td.appendChild(el("li", "line " + t.line + ": " + t.tag + " " + t.text)); }); }
    if (m.file_io.length) { var io = section(panel, "File / network I/O"); m.file_io.forEach(function (f) { io.appendChild(el("li", "line " + f.line + ": " + f.mode + " via " + f.call + "()")); }); }
  }

  function renderReading() {
    var panel = document.getElementById("panel-reading");
    panel.appendChild(el("h2", "Start here"));
    var ol = el("ol");
    data.reading.forEach(function (s) {
      var li = el("li");
      li.appendChild(s.kind === "module" ? link(s.target) : el("strong", s.target));
      li.appendChild(el("div", s.reason, "muted"));
      ol.appendChild(li);
    });
    panel.appendChild(ol);
  }

  function renderFlow() {
    var panel = document.getElementById("panel-flow");
    var chains = section(panel, "Call chains from entry points");
    data.flow.chains.forEach(function (c) {
      var li = el("li");
      c.forEach(function (p, i) { if (i) li.appendChild(document.createTextNode(" \\u2192 ")); li.appendChild(link(p, p.split("/").pop())); });
      chains.appendChild(li);
    });
    var types = section(panel, "Shared data structures");
    data.flow.shared_types.forEach(function (t) {
      var li = el("li"); li.appendChild(el("code", t.name));
      li.appendChild(document.createTextNode(" (" + t.path + ":" + t.line + ") used by " + t.users.join(", ")));
      types.appendChild(li);
    });
    var io = section(panel, "File and network I/O");
    data.flow.io.forEach(function (f) { var li = el("li"); li.appendChild(link(f.path)); li.appendChild(document.createTextNode(":" + f.line + " " + f.mode + " via " + f.call + "()")); io.appendChild(li); });
  }

  function renderIssues() {
    var panel = document.getElementById("panel-issues");
    var ol = el("ol");
    data.issues.forEach(function (issue) {
      var li = el("li"); li.appendChild(el("strong", "[" + issue.score + "] " + issue.title));
      var where = el("div"); where.appendChild(link(issue.path, issue.path + ":" + issue.line)); li.appendChild(where);
      issue.reasons.forEach(function (r) { li.appendChild(el("div", r, "muted")); });
      ol.appendChild(li);
    });
    panel.appendChild(ol);
  }

  function showTab(name) {
    document.querySelectorAll("nav button").forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-tab") === name); });
    document.querySelectorAll(".panel").forEach(function (p) { p.classList.toggle("active", p.id === "panel-" + name); });
  }
  document.querySelectorAll("nav button").forEach(function (b) {
    b.addEventListener("click", function () { showTab(b.getAttribute("data-tab")); });
  });

  function matches(m, q) {
    if (m.path.toLowerCase().indexOf(q) !== -1) return true;
    return m.symbols.some(function (s) { return s.name.toLowerCase().indexOf(q) !== -1; });
  }
  var search = document.getElementById("search");
  search.addEventListener("input", function () {
    var q = search.value.trim().toLowerCase();
    var hits = q ? data.modules.filter(function (m) { return matches(m, q); }) : [];
    var hitSet = {}; hits.forEach(function (m) { hitSet[m.path] = true; });
    svg.querySelectorAll(".node").forEach(function (g) {
      var p = g.getAttribute("data-path");
      g.classList.toggle("dim", !!q && !hitSet[p]);
      g.classList.toggle("match", !!q && !!hitSet[p]);
    });
    svg.querySelectorAll(".edge").forEach(function (p) { p.classList.toggle("dim", !!q); });
    if (!selected) {
      var res = document.getElementById("results");
      if (res) {
        res.innerHTML = "";
        hits.slice(0, 30).forEach(function (m) { var d = el("div"); d.appendChild(link(m.path)); res.appendChild(d); });
      }
    }
  });
  search.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter") return;
    var q = search.value.trim().toLowerCase();
    var first = data.modules.filter(function (m) { return matches(m, q); })[0];
    if (first) select(first.path);
  });

  var drag = null;
  svg.addEventListener("mousedown", function (ev) { drag = { x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y }; svg.classList.add("dragging"); });
  window.addEventListener("mouseup", function () { drag = null; svg.classList.remove("dragging"); });
  window.addEventListener("mousemove", function (ev) {
    if (!drag) return;
    var scale = view.w / svg.clientWidth;
    view.x = drag.vx - (ev.clientX - drag.x) * scale;
    view.y = drag.vy - (ev.clientY - drag.y) * scale;
    applyView();
  });
  svg.addEventListener("wheel", function (ev) {
    ev.preventDefault();
    var factor = ev.deltaY > 0 ? 1.15 : 1 / 1.15;
    var rect = svg.getBoundingClientRect();
    var px = view.x + (ev.clientX - rect.left) / rect.width * view.w;
    var py = view.y + (ev.clientY - rect.top) / rect.height * view.h;
    view.w *= factor; view.h *= factor;
    view.x = px - (px - view.x) * factor; view.y = py - (py - view.y) * factor;
    applyView();
  }, { passive: false });

  drawGraph();
  renderReading();
  renderFlow();
  renderIssues();
})();
</script>
</body>
</html>
"""
