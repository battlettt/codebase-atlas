"""Grounded Q&A: citations point at real lines; unsupported questions are refused."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import SAMPLE, main_for, run_cli, sample_atlas, self_atlas  # noqa: E402

from codebase_atlas.report.text import format_answer  # noqa: E402
from codebase_atlas.retrieval import NOT_SUPPORTED, CodeIndex, ask, question_terms, stem, tokenize  # noqa: E402

UNSUPPORTED = [
    "How does the payment gateway process refunds?",
    "Which database stores user passwords?",
    "Where is the kubernetes deployment configured?",
    "What is the meaning of life?",
]


def _line(root, path, line):
    with open(os.path.join(root, path), encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    assert 1 <= line <= len(lines), f"{path}:{line} out of range"
    return lines[line - 1]


def assert_citations_real(root, answer):
    assert answer.evidence, "supported answers must cite evidence"
    for item in answer.evidence:
        text = _line(root, item.path, item.line)
        assert item.snippet == text.strip()[:160]
        searchable = set(tokenize(text)) | (set(tokenize(item.path)) if item.kind == "path" else set())
        assert set(item.matched) <= searchable, f"{item.path}:{item.line} does not mention {item.matched}"
    for _, citations in answer.facts:
        for citation in citations:
            path, line = citation.rsplit(":", 1)
            _line(root, path, int(line))


def test_tokenize_and_stem():
    assert "load_items" in tokenize("load_items") and "load" in tokenize("loadItems")
    assert stem("loaded") == stem("load") == stem("loading")
    assert stem("applied") == stem("apply")
    assert stem("discounts") == stem("discount")
    assert question_terms("How does it work?") == []


def test_answer_cites_real_lines_for_symbol_question():
    answer = ask(sample_atlas(), "Where is load_items used?")
    assert answer.supported
    assert_citations_real(SAMPLE, answer)
    cited = {(e.path, e.line) for e in answer.evidence}
    assert ("inventory/store.py", 8) in cited and ("inventory/report.py", 7) in cited
    fact = answer.facts[0][0]
    assert "inventory/store.py:8" in fact and "inventory/report.py:7 (call)" in fact


def test_answer_for_concept_question_across_languages():
    atlas = sample_atlas()
    for question, expected_path in [
        ("How are discounts applied?", "web/src/cart.ts"),
        ("How are inventory items loaded?", "inventory/store.py"),
        ("What does Quote return?", "go/internal/rates/rates.go"),
    ]:
        answer = ask(atlas, question)
        assert answer.supported, question
        assert_citations_real(SAMPLE, answer)
        assert expected_path in {e.path for e in answer.evidence}, question


def test_refuses_unsupported_questions():
    atlas = sample_atlas()
    index = CodeIndex(atlas)
    for question in UNSUPPORTED:
        answer = ask(atlas, question, index=index)
        assert not answer.supported, question
        assert answer.evidence == [] and answer.facts == []
        assert format_answer(answer).startswith(NOT_SUPPORTED)


def test_refuses_empty_or_stopword_only_question():
    answer = ask(sample_atlas(), "how does it work?")
    assert not answer.supported and "no searchable terms" in answer.reason


def test_cli_refusal_prints_only_the_refusal_and_exits_3():
    code, out, _ = run_cli("ask", SAMPLE, UNSUPPORTED[0])
    assert code == 3
    assert out.startswith(NOT_SUPPORTED) and len(out.strip().splitlines()) == 1
    assert not re.search(r"\.(py|ts|go):\d+", out), "a refusal must not cite anything"


def test_cli_supported_answer_has_file_line_citations():
    code, out, _ = run_cli("ask", SAMPLE, "Where is load_items used?")
    assert code == 0
    assert "inventory/report.py:7" in out and "no language model" in out


def test_self_analysis_question_is_grounded():
    atlas = self_atlas()
    root = atlas.root
    answer = ask(atlas, "How is the reading order computed?")
    assert answer.supported
    assert_citations_real(root, answer)
    assert "codebase_atlas/analysis/reading_order.py" in {e.path for e in answer.evidence}


if __name__ == "__main__":
    main_for(globals())
