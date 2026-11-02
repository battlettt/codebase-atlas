"""Per-language parsing: imports, exports, definitions, docs, TODOs, I/O."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import SAMPLE, main_for  # noqa: E402

from codebase_atlas.parsers import parse_source  # noqa: E402
from codebase_atlas.parsers.common import strip_c_like  # noqa: E402


def _sample(rel, language):
    with open(os.path.join(SAMPLE, rel), encoding="utf-8") as handle:
        return parse_source(rel, language, handle.read())


def _symbols(module):
    return {(s.kind, s.qualified_name) for s in module.symbols}


PY_SOURCE = '''"""Module doc. Second sentence."""
import os
import a.b.c as abc
from . import sibling
from ..pkg import thing as other
from x import *

LIMIT = 10
__all__ = ["public", "Thing", "LIMIT"]


def public(path):
    """Write a file."""
    with open(path, "w") as handle:  # TODO: handle errors
        handle.write("x")


def _private():
    pass


class Thing:
    def method(self):
        if True:
            return 1


if __name__ == "__main__":
    public("out")
'''


def test_python_imports():
    module = parse_source("pkg/mod.py", "python", PY_SOURCE)
    imports = [(i.target, i.level, i.alias, i.names) for i in module.imports]
    assert ("os", 0, "os", []) in imports
    assert ("a.b.c", 0, "abc", []) in imports
    assert ("", 1, "", [("sibling", "sibling")]) in imports
    assert ("pkg", 2, "", [("thing", "other")]) in imports
    assert ("x", 0, "", [("*", "*")]) in imports


def test_python_definitions_docs_and_exports():
    module = parse_source("pkg/mod.py", "python", PY_SOURCE)
    assert module.doc.startswith("Module doc.")
    assert _symbols(module) >= {("function", "public"), ("function", "_private"),
                                ("class", "Thing"), ("method", "Thing.method"), ("const", "LIMIT")}
    public = module.symbol_named("public")
    assert public.exported and public.doc == "Write a file." and public.line == 12
    assert not module.symbol_named("_private").exported
    method = [s for s in module.symbols if s.name == "method"][0]
    assert method.complexity == 2 and method.parent == "Thing"


def test_python_entry_todo_and_file_io():
    module = parse_source("pkg/mod.py", "python", PY_SOURCE)
    assert module.is_entry and "__main__" in module.entry_reason
    assert [(t.line, t.tag, t.text) for t in module.todos] == [(14, "TODO", "handle errors")]
    assert [(f.line, f.mode, f.call) for f in module.file_io] == [(14, "write", "open")]


def test_python_sample_refs_capture_cross_module_calls():
    module = _sample("inventory/report.py", "python")
    calls = {(r.name, r.line) for r in module.refs if r.is_call}
    assert ("load_items", 7) in calls and ("low_stock", 10) in calls


TS_SOURCE = '''/** Cart module. */
import Default, { a, b as c } from "./one";
import * as ns from '../two';
import type { T } from "./types";
import {
  multi,
  line,
} from "./multi";
import "./side-effect";
const fs = require("fs");
export * from "./barrel";
export { x as y } from "./reexport";
// import fake from "./commented-out";
const url = "// not a comment";

export interface Shape { kind: string }
export type Id = string | number;
export enum Color { Red, Green }
export const add = (x: number, y: number): number => x + y;
export async function load(path: string) {
  if (path) { return 1; }
  return 2;
}
function helper() {}
export default class Widget {
  private secret(): void {}
  render(): string {
    return "x";
  }
}
// FIXME: remove helper
export { helper };
'''


def test_typescript_imports_all_forms():
    module = parse_source("src/cart.ts", "typescript", TS_SOURCE)
    by_target = {i.target: i for i in module.imports}
    assert by_target["./one"].names == [("a", "a"), ("b", "c"), ("default", "Default")]
    assert by_target["../two"].alias == "ns"
    assert by_target["./types"].names == [("T", "T")]
    assert by_target["./multi"].names == [("multi", "multi"), ("line", "line")]
    assert by_target["./multi"].line == 5
    assert "./side-effect" in by_target and "fs" in by_target
    assert by_target["./barrel"].names == [("*", "*")]
    assert by_target["./reexport"].names == [("x", "y")]
    assert "./commented-out" not in by_target


def test_typescript_definitions_and_exports():
    module = parse_source("src/cart.ts", "typescript", TS_SOURCE)
    assert _symbols(module) >= {
        ("interface", "Shape"), ("type", "Id"), ("enum", "Color"), ("function", "add"),
        ("function", "load"), ("function", "helper"), ("class", "Widget"),
        ("method", "Widget.secret"), ("method", "Widget.render"), ("const", "url"),
    }
    load = module.symbol_named("load")
    assert load.exported and load.line == 20 and load.end_line == 23 and load.complexity == 2
    assert module.symbol_named("helper").exported  # via `export { helper }`
    assert not module.symbol_named("url").exported
    secret = [s for s in module.symbols if s.name == "secret"][0]
    assert not secret.exported
    assert module.default_export == "Widget"
    assert module.doc == "Cart module."
    assert [(t.tag, t.text) for t in module.todos] == [("FIXME", "remove helper")]


def test_typescript_sample_file_io_and_docs():
    module = _sample("web/src/api.ts", "typescript")
    assert [(f.line, f.mode) for f in module.file_io] == [(7, "read")]
    assert module.symbol_named("loadOrders").doc == "Read all orders from a JSON file on disk."


GO_SOURCE = '''// Package server runs the HTTP API.
package main

import "fmt"
import (
	str "strings"
	"example.com/app/internal/store"
)

// Config holds settings.
type Config struct {
	Port int
}

type Handler interface {
	Serve() error
}

type (
	ID   string
	Pair struct{ A, B int }
)

const (
	MaxUsers = 10
	minUsers = 1
)

var Version = "1.0"

// Start boots the server.
func (c *Config) Start() error {
	for i := 0; i < 3; i++ {
		fmt.Println(str.ToUpper("x"), store.Open())
	}
	return nil
}

func main() {
	// TODO: read flags
}
'''


def test_go_imports():
    module = parse_source("cmd/server/main.go", "go", GO_SOURCE)
    imports = [(i.target, i.alias, i.line) for i in module.imports]
    assert imports == [("fmt", "", 4), ("strings", "str", 6), ("example.com/app/internal/store", "", 7)]


def test_go_definitions_methods_groups_and_entry():
    module = parse_source("cmd/server/main.go", "go", GO_SOURCE)
    assert module.package == "main" and module.doc == "Package server runs the HTTP API."
    assert _symbols(module) >= {
        ("struct", "Config"), ("interface", "Handler"), ("type", "ID"), ("struct", "Pair"),
        ("const", "MaxUsers"), ("const", "minUsers"), ("const", "Version"),
        ("method", "Config.Start"), ("function", "main"),
    }
    start = [s for s in module.symbols if s.name == "Start"][0]
    assert start.doc == "Start boots the server." and start.end_line == 37 and start.complexity == 2
    assert not module.symbol_named("minUsers").exported and module.symbol_named("MaxUsers").exported
    assert module.is_entry
    assert [(t.line, t.text) for t in module.todos] == [(40, "read flags")]
    calls = {r.name for r in module.refs if r.is_call}
    assert {"store.Open", "str.ToUpper", "fmt.Println"} <= calls


def test_strip_c_like_keeps_lines_and_separates_comments():
    text = 'a = "x // y"; // real\n/* block\n   more */ b = `t\nu`;\n'
    code, with_strings, comments = strip_c_like(text)
    assert len(code) == len(text) == len(with_strings) == len(comments)
    assert code.count("\n") == text.count("\n")
    assert "real" in comments and "real" not in code
    assert '"x // y"' in with_strings and "x // y" not in code
    assert "b =" in code


if __name__ == "__main__":
    main_for(globals())
