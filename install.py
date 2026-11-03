#!/usr/bin/env python3
"""Install or remove the receipts skill for Claude Code.

    python install.py                  copy the skill to ~/.claude/skills/receipts
    python install.py --hook           also register the Stop hook in ~/.claude/settings.json
    python install.py --uninstall      remove the skill and the hook

Options: --target DIR (skills folder), --settings FILE (settings.json to edit).
Standard library only. settings.json is backed up before every change and is never
overwritten if it cannot be parsed.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "skill"
MARKER = "receipts/scripts/stop_gate.py"   # identifies our hook entry in settings.json


def hook_command(dest):
    python = "python" if sys.platform == "win32" else "python3"
    return f'{python} -I "{(dest / "scripts" / "stop_gate.py").as_posix()}"'


def load_settings(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{path} is not valid JSON ({e}); not touching it. Fix the file or add the hook by hand.")
    if not isinstance(data, dict):
        sys.exit(f"{path} does not hold a JSON object; not touching it.")
    return data


def save_settings(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copyfile(path, path.with_name(path.name + ".receipts.bak"))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_ours(entry):
    return any(MARKER in h.get("command", "").replace("\\", "/") for h in entry.get("hooks", []) if isinstance(h, dict))


def add_hook(path, command):
    data = load_settings(path)
    stop = data.setdefault("hooks", {}).setdefault("Stop", [])
    for entry in stop:
        if isinstance(entry, dict) and is_ours(entry):
            for h in entry["hooks"]:
                if isinstance(h, dict) and MARKER in h.get("command", "").replace("\\", "/"):
                    h["command"] = command          # refresh the path instead of adding a duplicate
            save_settings(path, data)
            return "updated"
    stop.append({"hooks": [{"type": "command", "command": command}]})
    save_settings(path, data)
    return "added"


def remove_hook(path):
    if not path.exists():
        return False
    data = load_settings(path)
    stop = data.get("hooks", {}).get("Stop", [])
    kept = [e for e in stop if not (isinstance(e, dict) and is_ours(e))]
    if len(kept) == len(stop):
        return False
    if kept:
        data["hooks"]["Stop"] = kept
    else:
        del data["hooks"]["Stop"]
        if not data["hooks"]:
            del data["hooks"]
    save_settings(path, data)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hook", action="store_true", help="also register the Stop hook")
    ap.add_argument("--uninstall", action="store_true", help="remove the skill and the hook")
    ap.add_argument("--target", default=str(Path.home() / ".claude" / "skills"), help="skills folder")
    ap.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"), help="settings.json to edit")
    args = ap.parse_args(argv)

    dest = Path(args.target) / "receipts"
    settings = Path(args.settings)

    if args.uninstall:
        if dest.exists():
            shutil.rmtree(dest)
            print(f"Removed {dest}")
        else:
            print(f"Nothing to remove at {dest}")
        if remove_hook(settings):
            print(f"Removed the Stop hook from {settings}")
        return 0

    if not (SRC / "SKILL.md").exists():
        sys.exit(f"Skill sources not found at {SRC}")
    if args.hook:
        load_settings(settings)   # fail early, before anything is copied, if settings.json is unusable
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"Installed the skill to {dest}")
    if args.hook:
        print(f"Stop hook {add_hook(settings, hook_command(dest))} in {settings} (backup: {settings.name}.receipts.bak)")
    print("Start a new Claude Code session to load it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
