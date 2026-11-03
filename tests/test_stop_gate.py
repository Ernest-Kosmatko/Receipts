import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parent.parent / "plugin" / "skills" / "receipts" / "scripts" / "stop_gate.py"


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def text(t):
    return {"type": "text", "text": t}


def edit(path):
    return {"type": "tool_use", "name": "Edit", "id": "1", "input": {"file_path": path}}


def shell(command):
    return {"type": "tool_use", "name": "Bash", "id": "2", "input": {"command": command}}


def gate(tmp_path, lines, active=False, env=None, stdin=None):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    payload = stdin if stdin is not None else json.dumps({"transcript_path": str(transcript), "stop_hook_active": active})
    r = subprocess.run([sys.executable, "-I", str(GATE)], input=payload, capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, **(env or {})})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def blocked(result):
    return result is not None and result["decision"] == "block"


def test_blocks_a_completion_claim_after_edits_without_a_receipt(tmp_path):
    result = gate(tmp_path, [user("fix it"), assistant(edit("/proj/app.js")), assistant(text("Done, everything works."))])
    assert blocked(result) and "receipt" in result["reason"]


def test_allows_when_a_receipt_ran_after_the_last_edit(tmp_path):
    lines = [user("fix it"), assistant(edit("/proj/app.js")), assistant(shell("python receipt.py render")), assistant(text("Done."))]
    assert gate(tmp_path, lines) is None


def test_blocks_when_the_receipt_came_before_the_last_edit(tmp_path):
    lines = [user("x"), assistant(shell("python receipt.py render")), assistant(edit("/proj/app.js")), assistant(text("Done."))]
    assert blocked(gate(tmp_path, lines))


def test_a_new_human_prompt_starts_a_fresh_turn(tmp_path):
    lines = [user("a"), assistant(edit("/proj/app.js")), assistant(text("ok")), user("what does this do?"),
             assistant(text("It is done by X."))]
    assert gate(tmp_path, lines) is None


def test_allows_a_claim_without_edits(tmp_path):
    assert gate(tmp_path, [user("what is this?"), assistant(text("Done, here is the answer."))]) is None


def test_allows_edits_without_a_claim(tmp_path):
    lines = [user("x"), assistant(edit("/proj/a.js")), assistant(text("I changed the file but did not test it."))]
    assert gate(tmp_path, lines) is None


def test_ignores_edits_to_agent_housekeeping_files(tmp_path):
    lines = [user("x"), assistant(edit("/home/dev/.claude/projects/p/memory/n.md")), assistant(text("Done."))]
    assert gate(tmp_path, lines) is None


def test_never_loops(tmp_path):
    lines = [user("x"), assistant(edit("/proj/a.js")), assistant(text("Done."))]
    assert gate(tmp_path, lines, active=True) is None


def test_polish_completion_claims_are_detected(tmp_path):
    assert blocked(gate(tmp_path, [user("x"), assistant(edit("/proj/a.js")), assistant(text("Gotowe, wszystko działa."))]))


@pytest.mark.parametrize("message", [
    "The slogan is “No done without proof.” I changed the file.",
    'I added a line that says "all done" to the README.',
    "Use `done` as the status value.",
    "```\nstatus = done\n```\nThat is the change.",
    "> done\nI edited the quote.",
    "Dopisałem hasło „gotowe” do pliku.",
])
def test_quoted_words_and_code_are_not_a_claim(tmp_path, message):
    assert gate(tmp_path, [user("x"), assistant(edit("/proj/a.js")), assistant(text(message))]) is None


def test_can_be_switched_off(tmp_path):
    lines = [user("x"), assistant(edit("/proj/a.js")), assistant(text("Done."))]
    assert gate(tmp_path, lines, env={"RECEIPTS_GATE": "off"}) is None


def test_malformed_input_is_ignored(tmp_path):
    assert gate(tmp_path, [], stdin="not json") is None
    assert gate(tmp_path, [], stdin=json.dumps({"transcript_path": str(tmp_path / "missing.jsonl")})) is None
