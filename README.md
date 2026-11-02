# Codebase Atlas

Point Codebase Atlas at a repository to get an onboarding map: the architecture,
how data flows, the dependency graph, a start-here reading order, Q&A grounded
in the code (with file:line citations), change-impact analysis, good first
issues, and drift detection as the code changes.

It works with **Python, TypeScript/JavaScript, and Go**, runs **fully offline**,
and uses **only the Python 3.11+ standard library**. It does not need a language
model.

```
python -m codebase_atlas map path/to/repo       # or: bin/atlas map path/to/repo
```

## Install / run

There is nothing to install. From a checkout:

| Way to run | Command |
|---|---|
| Module | `python -m codebase_atlas <command> ...` |
| Script | `bin/atlas <command> ...` |
| Installed | `pip install .` provides an `atlas` console script (optional) |

## Commands

| Command | What it does |
|---|---|
| `atlas map <repo>` | Architecture map as text: modules by directory with roles and summaries, dependency edges with reasons, data flow, reading order. `--json` prints JSON. `--module <path>` shows one module in detail. |
| `atlas ask <repo> "<question>"` | Grounded Q&A. Every answer cites `path:line`. If the code does not support an answer, it prints `Not supported by this codebase.` and stops (exit code 3). |
| `atlas impact <repo> <file-or-symbol>` | Reverse dependencies: direct dependents with line-level reasons, transitive dependents with the chain between them, tests that cover the target, and a risk level. Accepts a path, a path suffix (`store.py`), a Python module (`inventory.store`), a symbol (`load_items`), or a method (`Item.total_value`). |
| `atlas issues <repo>` | Ranked good first issues, each with its score broken down into reasons. `--limit N`, `--json`. |
| `atlas snapshot <repo> -o map.json` | Writes the map as deterministic JSON (no timestamps, no absolute paths). |
| `atlas drift <repo> --against map.json` | Lists added, removed, and changed modules, dependencies, and symbols. `--exit-code` exits 1 when anything drifted (useful in CI). `--json`. |
| `atlas html <repo> -o map.html` | One self-contained interactive HTML file that works offline. |

Options shared by every command: `--exclude DIR` (repeatable) skips more
directories, and `--verbose` lists files that were skipped.
`node_modules`, `vendor`, `.git`, `__pycache__`, virtualenvs, `dist`/`build`,
and hidden directories are skipped by default.

**CLI changes from the original spec** (all additions, nothing renamed):
`map --module/--json`, `--json` on the other commands, `drift --exit-code`,
`--exclude`, `--verbose`, and exit code 3 when `ask` refuses or `impact` finds
no target.

## Examples (real output from `examples/sample-repo`)

```
$ atlas ask examples/sample-repo "Where is load_items used?" --limit 3
Q: Where is load_items used?

Answer (retrieved from code; 3 cited location(s), no language model):
  - `load_items` is a function defined at inventory/store.py:8-13: "Read items from a JSON file and return a list of Item objects.". Used at inventory/report.py:7 (call).

Evidence:
  [1] inventory/store.py:8  def load_items(path):
       matched: item, load, load_items
  [2] inventory/report.py:2  from inventory.store import load_items, low_stock
       matched: item, load, load_items
  [3] inventory/report.py:7  items = load_items(path)
       matched: item, load, load_items

$ atlas ask examples/sample-repo "How does the payment gateway process refunds?"
Not supported by this codebase. (no code mentions: payment, gateway, refund)
```

```
$ atlas impact examples/sample-repo load_items
Impact of changing load_items (symbol)
======================================
Defined at inventory/store.py:8 (function load_items)
Risk: HIGH - 1 direct and 1 transitive non-test dependent(s); no test depends on it, so breakage would go unnoticed

Direct dependents (1):
  inventory/report.py
      - calls load_items() at line 7; breaks if its signature or return value changes
Transitive dependents (1):
  main.py  (via inventory/report.py -> main.py)
```

```
$ atlas issues examples/sample-repo --limit 2
Good first issues (2)
=====================
 1. [73] Resolve TODO: validate that every record has a sku before building items
      at inventory/store.py:10
      +50 the TODO comment already describes the task
      +5 inside load_items(), which is simple (complexity 3)
      +8 loosely coupled (3 internal links)
      +10 small file (24 lines) to read end to end
 2. [68] Resolve FIXME: discounts are hard-coded; read them from configuration instead.
      ...
```

```
$ atlas snapshot repo -o before.json
$ # ... add a function `restock` to inventory/store.py ...
$ atlas drift repo --against before.json
Drift since snapshot
====================
Changed modules (1):
  inventory/store.py: 24 -> 28 lines
Added symbols (1):
  inventory/store.py: function restock
```

## What each feature does

- **Architecture map.** Every source file is a module. Each one gets a role
  (entry point, core logic, foundation, shared utility, data model, package
  interface, configuration, top-level consumer, isolated, or test) and a
  reason for that role, based on structure (fan-in, fan-out, kinds of symbols,
  file name).
- **Dependency graph.** Edges between modules carry reasons: `import`, `call`,
  `shared type` (a class, interface, struct, type, or enum defined in one
  module and used in another), and `reference` (a constant or function passed
  around without being called). Each reason is backed by exact lines. Python
  re-exports (`from .core import X` in `__init__.py`) and TypeScript barrels
  (`export * from`) are followed to the module that defines the symbol. Files
  in the same Go package link to each other without imports.
- **Data flow.** Call chains from each entry point, cross-module calls (data
  passed as arguments and return values), shared data structures and who uses
  them, and file, network, and process I/O sites
  (`open`, `json.load`, `readFileSync`, `os.ReadFile`, `fetch`, ...).
- **Reading order.** README first, then entry points, then every other module
  in dependency order: a module never comes before its dependencies unless it
  is an entry point. Ties go to the most-used modules first, and tests come
  last. Dependency cycles are broken at the module with the fewest unmet
  dependencies, and that step is labelled as part of a cycle.
- **Module summaries.** Built from the docstring or leading comment, the role,
  size, counts of functions and types, exported names, and the modules on
  either side. No model is involved.
- **Grounded Q&A.** Questions are split into terms (identifiers broken at
  snake_case and camelCase boundaries, with light stemming). Those terms are
  matched against an index of symbol names, every source line (comments and
  docstrings included), Markdown docs, and file paths, ranked by IDF. Before
  answering, at least half of the question's terms must appear in the code
  **and** at least half must appear together in one file. Otherwise the tool
  refuses. Answers list facts about any symbol the question names (its
  definition range, its docstring, and where it is used), then the evidence
  lines. Each piece of evidence is cited at a line that contains the matched
  terms. For path matches, the terms are in the file name, and the output says so.
- **Impact.** Reverse lookup over graph edges and line-level uses, then a
  breadth-first search for transitive dependents. Method calls (`obj.method()`)
  can't be resolved without types, so matches by method name are marked
  `[possible]`. Risk goes up with the number of non-test dependents, and goes
  up again when no test depends on the target.
- **Good first issues.** Candidates are TODO/FIXME/XXX/HACK comments, public
  symbols with no documentation, and the smallest simple function in a module
  that no test imports. Isolated modules and small files score higher; highly
  connected and large files score lower. Each issue's reasons add up to its score.
- **Drift.** A snapshot stores each module's language, role, line count, SHA-1,
  and symbol set (`kind name`), plus every edge with its reasons. `drift`
  compares the current tree against a snapshot.

## Design decisions

1. **Retrieval first, model second.** Every feature works with no language
   model at all. The one optional hook is `--llm-command "<cmd>"` on `ask` and
   `map`. It runs your command (no shell), sends it a JSON context on stdin
   (the question with its retrieved evidence, or the module's details), and
   prints the command's stdout under the label
   `[LLM-enriched via `cmd`; not verified against the code]`. The hook is off
   by default. It never runs for a refused question. If it fails, you get a
   warning and the grounded output is unchanged.
2. **Grounded or silent.** The tool only reports what it can point to.
   Answers cite `path:line`. Unsupported questions get a one-line refusal with
   no citations. `impact` says when a target doesn't exist instead of guessing,
   and matches that rest on method names alone are labelled `[possible]`.
3. **Offline HTML.** `atlas html` writes one file with inline CSS, inline
   JavaScript, and a hand-drawn SVG graph (no libraries). It has a layered
   layout (dependencies on the left), search, click-to-inspect details,
   highlighted edges, pan and zoom, and tabs for the reading order, data flow,
   and first issues. The embedded data is JSON with `<`, `>`, and `/` escaped,
   so code from the repo can't close the script tag, and the file contains no
   `http://` or `https://` strings. The page makes no network requests.
4. **Lightweight parsers.** Python uses the standard library `ast` module,
   which is exact and still dependency-free. TypeScript, JavaScript, and Go
   use regex parsers that run on a copy of the source with comments and
   strings blanked out, so line numbers stay exact and commented-out imports
   are ignored. Files that can't be parsed (syntax errors, binaries, files
   over 1 MB) are skipped and counted as warnings. They never crash a run.
5. **Separate layers.** `scanner` → `parsers/` → `resolver` + `graph` →
   `analysis/` (roles, reading order, summaries, data flow, impact, issues,
   drift) and `retrieval` → `report/` (text, HTML) → `cli`. Each layer has its
   own tests.

## Known limits

- TypeScript `paths`/`baseUrl` aliases and Node package `exports` maps are not
  resolved. Non-relative imports are listed as external packages.
- Calls are resolved through imported names, namespaces, and Go package
  qualifiers. Calls on objects (`obj.method()`) aren't typed, so `impact`
  marks them as possible.
- Go module paths come from `go.mod` files inside the repo. `replace`
  directives are ignored.
- The HTML map was checked by syntax-checking its script and running it
  against a stub DOM in Node. It has not been looked at in a real browser
  as part of this test suite.

## Tests

Tests use plain asserts and run with or without pytest:

```
python tests/run_tests.py          # runs every tests/test_*.py, prints pass/fail totals
python tests/test_drift.py         # any single file runs on its own
python -m pytest                   # also works if pytest is installed
```

The suite runs against `examples/sample-repo/`, a small shop project with
Python (`inventory/`), TypeScript (`web/`), and Go (`go/`) code. It has real
cross-module call chains, a TODO, and a FIXME. The suite also analyses this
repository itself. It covers parsing for each language, graph edges and
reasons, reading-order validity, Q&A citations against real lines, refusals,
impact, issue ranking, the snapshot/drift round trip, HTML offline safety
(including hostile repo content), the LLM hook, and messy input.
