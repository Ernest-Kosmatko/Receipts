#!/usr/bin/env python3
"""Optional Claude Code Stop hook: no "done" without a receipt.

Blocks the stop once when, in the current turn, Claude edited files and its final
message claims completion, but no receipt.py command ran after the last edit.
Quoted text and code in the message are ignored, so quoting a slogan is not a claim.
Never loops (honours stop_hook_active), never touches anything but its own output.
Disable with RECEIPTS_GATE=off.
"""
import json
import os
import re
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
IGNORE_PATH = re.compile(r"([\\/]\.claude[\\/]|scratchpad|[\\/]Temp[\\/]|[\\/]memory[\\/]|[\\/]\.receipts[\\/])", re.I)
CLAIM = re.compile(r"\b(gotowe|gotowa|zrobione|naprawione|naprawiłem|działa|dziala|wszystko (ok|działa)|"
                   r"done|complete[d]?|finished|fixed|ready|works( now)?|all set)\b", re.I)
FENCE = re.compile(r"```.*?```", re.S)
INLINE = re.compile(r"`[^`\n]*`")
BLOCKQUOTE = re.compile(r"^\s*>.*$", re.M)
QUOTED = re.compile(r"“[^”\n]*”|„[^”\n]*”|\"[^\"\n]*\"")
NOISE = ("<system-reminder", "<task-notification", "<local-command", "<command-", "caveat:", "[system")


def claims_done(text):
    """True if the message itself claims completion (words inside quotes, code or blockquotes do not count)."""
    for rx in (FENCE, INLINE, BLOCKQUOTE, QUOTED):
        text = rx.sub(" ", text)
    return bool(CLAIM.search(text))


def is_human(msg):
    c = msg.get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return False
        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
    if not isinstance(c, str) or not c.strip():
        return False
    return not c.strip().lower().startswith(NOISE)


def main():
    if os.environ.get("RECEIPTS_GATE", "").lower() == "off":
        return
    try:
        inp = json.load(sys.stdin)
    except ValueError:
        return
    if inp.get("stop_hook_active"):
        return
    path = inp.get("transcript_path")
    if not path or not os.path.exists(path):
        return

    turn = []  # events since the last human prompt: ("edit"|"receipt"|"text", payload)
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"user"' not in line and '"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("isSidechain") or o.get("type") not in ("user", "assistant"):
                continue
            msg = o.get("message") or {}
            if o["type"] == "user":
                if is_human(msg):
                    turn = []
                continue
            for b in msg.get("content") or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    turn.append(("text", b["text"]))
                elif b.get("type") == "tool_use":
                    name, inp_ = b.get("name", ""), b.get("input") or {}
                    if name in EDIT_TOOLS:
                        target = str(inp_.get("file_path") or inp_.get("notebook_path") or "")
                        if not IGNORE_PATH.search(target):
                            turn.append(("edit", target))
                    elif name in SHELL_TOOLS and "receipt.py" in str(inp_.get("command", "")):
                        turn.append(("receipt", ""))

    edits = [i for i, (k, _) in enumerate(turn) if k == "edit"]
    texts = [t for k, t in turn if k == "text"]
    if not edits or not texts or not claims_done(texts[-1]):
        return
    last_edit = edits[-1]
    if any(k == "receipt" for k, _ in turn[last_edit:]):
        return

    reason = ("Receipts: you edited files this turn and your final message says it is done, but no receipt was "
              "produced after the last edit. Before claiming completion, follow the receipts skill: "
              "`receipt.py init` with acceptance criteria, `run` / `shot` real checks, `mark` what you observed, "
              "`render`, then report the verdict (VERIFIED / PARTIAL / FAILED) and what is not verified. "
              "If this was a trivial change that needs no proof, say so explicitly instead of claiming it is done.")
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
