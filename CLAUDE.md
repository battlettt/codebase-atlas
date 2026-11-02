# CLAUDE.md - Codebase Atlas

## What this is
Codebase onboarding intelligence: point it at a repo and get an
architecture map, data flow, dependency graph, a start-here reading
order, Q&A grounded in the actual code with file and line citations,
change-impact analysis (if I change X, what breaks?), a good-first-issue
finder for newcomers, and drift detection as the code changes.

## Principles
- Grounded or silent: every answer cites files and lines, or the tool
  says it cannot answer from the code. No invented architecture.
- Multi-language: Python, TypeScript, and Go at minimum.
- Retrieval over code first, language model second. The map must be
  useful even with no model available.
- CLI plus an interactive HTML map. The map must work offline.

## Build, test, run
- Run: `python -m codebase_atlas` (see README for commands)
- Tests: plain asserts, runnable with or without pytest:
  `python -m pytest`
- Keep parsing, retrieval, analysis, and reporting separate so each
  can be tested alone.

## Conventions
- Small functions, clear names, minimal abstraction.
- Every feature ships with tests and a README section.
- Test against real small repos, not toy examples only.

## Layout and notes
- Layers: `scanner` -> `parsers/` -> `resolver` + `graph` -> `analysis/`
  and `retrieval` -> `report/` (text, html) -> `cli`. Stdlib only.
- Test runner without pytest: `python tests/run_tests.py`; fixture repo is
  `examples/sample-repo/` (tests assert exact lines there, so edit with care).
- Q&A evidence must cite a line containing the matched terms; keep the
  refusal string `NOT_SUPPORTED` in `retrieval.py` stable.
