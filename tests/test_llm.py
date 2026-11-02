"""Optional --llm-command hook: off by default, labelled, never required."""
import json
import os
import shlex
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_test_support import SAMPLE, main_for, run_cli  # noqa: E402

from codebase_atlas.llm import run_llm  # noqa: E402

ECHO = (f"{shlex.quote(sys.executable)} -c "
        + shlex.quote("import sys, json; d = json.load(sys.stdin); "
                      "print('ENRICHED', d['kind'], len(d.get('evidence', [])))"))


def test_run_llm_pipes_json_and_returns_stdout():
    text, error = run_llm(ECHO, {"kind": "question", "evidence": [1, 2]})
    assert error is None and text == "ENRICHED question 2"


def test_run_llm_failures_are_reported_not_raised():
    for command in ["", "definitely-not-a-real-command-xyz",
                    f"{shlex.quote(sys.executable)} -c 'import sys; sys.exit(4)'"]:
        text, error = run_llm(command, {})
        assert text is None and error


def test_ask_without_hook_never_mentions_llm():
    code, out, _ = run_cli("ask", SAMPLE, "How are discounts applied?")
    assert code == 0 and "LLM" not in out


def test_ask_with_hook_is_labelled_and_keeps_evidence():
    code, out, _ = run_cli("ask", SAMPLE, "How are discounts applied?", "--llm-command", ECHO)
    assert code == 0
    assert "Evidence:" in out and "web/src/cart.ts:15" in out
    assert "[LLM-enriched via" in out and "not verified against the code" in out
    assert "ENRICHED question" in out


def test_hook_is_not_called_for_unsupported_questions():
    with tempfile.TemporaryDirectory() as tmp:
        marker = os.path.join(tmp, "called")
        command = (f"{shlex.quote(sys.executable)} -c "
                   + shlex.quote(f"open({marker!r}, 'w').write('x'); print('should not appear')"))
        code, out, _ = run_cli("ask", SAMPLE, "How are refunds sent to the payment gateway?", "--llm-command", command)
        assert code == 3 and not os.path.exists(marker) and "should not appear" not in out


def test_map_module_with_hook_receives_module_context():
    dump = (f"{shlex.quote(sys.executable)} -c "
            + shlex.quote("import sys, json; d = json.load(sys.stdin); print(d['kind'], d['module']['path'])"))
    code, out, _ = run_cli("map", SAMPLE, "--module", "inventory/store.py", "--llm-command", dump)
    assert code == 0 and "module inventory/store.py" in out and "[LLM-enriched via" in out


def test_broken_hook_degrades_gracefully():
    code, out, err = run_cli("ask", SAMPLE, "How are discounts applied?", "--llm-command", "no-such-binary-xyz")
    assert code == 0 and "Evidence:" in out and "--llm-command failed" in err
    json.dumps(out)


if __name__ == "__main__":
    main_for(globals())
