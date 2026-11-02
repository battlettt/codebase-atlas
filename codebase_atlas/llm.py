"""Optional, off-by-default hook that pipes JSON context to an external command.

Nothing in Codebase Atlas requires this. Output is always labelled as
model-generated so it is never confused with grounded evidence.
"""
import json
import shlex
import subprocess

LLM_TIMEOUT_SECONDS = 120


def llm_label(command):
    return f"[LLM-enriched via `{command}`; not verified against the code]"


def run_llm(command, payload, timeout=LLM_TIMEOUT_SECONDS):
    """Return (text, error). Never raises for command failures."""
    try:
        args = shlex.split(command)
    except ValueError as error:
        return None, f"invalid --llm-command: {error}"
    if not args:
        return None, "empty --llm-command"
    try:
        proc = subprocess.run(args, input=json.dumps(payload), capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"--llm-command failed: {error}"
    if proc.returncode != 0:
        return None, f"--llm-command exited with {proc.returncode}: {proc.stderr.strip()[:200]}"
    text = proc.stdout.strip()
    return (text, None) if text else (None, "--llm-command produced no output")


def question_payload(answer):
    return {
        "kind": "question",
        "question": answer.question,
        "instructions": "Answer only from the evidence below and cite path:line. "
                        "If the evidence does not answer the question, say so.",
        "facts": [text for text, _ in answer.facts],
        "evidence": [{"path": e.path, "line": e.line, "snippet": e.snippet} for e in answer.evidence],
    }


def module_payload(details):
    return {
        "kind": "module",
        "instructions": "Summarize this module in two sentences using only the facts given.",
        "module": details,
    }
