#!/usr/bin/env python3
"""Install or remove the receipts skill for Claude Code without the plugin system.

    python install.py                  copy the skill to ~/.claude/skills/receipts
    python install.py --hook           also register the Stop hook in ~/.claude/settings.json
    python install.py --hook-only      register only the Stop hook (for people who installed the plugin)
    python install.py --uninstall      remove the skill, the hook script and the hook

Options: --target DIR (skills folder), --settings FILE (settings.json to edit).
Standard library only. settings.json is backed up before every change and is never
overwritten if it cannot be parsed.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "plugin" / "skills" / "receipts"
OURS = re.compile(r"receipts[^\"']*stop_gate\.py")   # matches both places the hook script can live


def hook_command(script):
    python = "python" if sys.platform == "win32" else "python3"
    return f'{python} -I "{script.as_posix()}"'


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


def is_ours(command):
    return bool(OURS.search(command.replace("\\", "/")))


def our_entry(entry):
    return isinstance(entry, dict) and any(isinstance(h, dict) and is_ours(h.get("command", "")) for h in entry.get("hooks", []))


def add_hook(path, command):
    data = load_settings(path)
    stop = data.setdefault("hooks", {}).setdefault("Stop", [])
    for entry in stop:
        if our_entry(entry):
            for h in entry["hooks"]:
                if isinstance(h, dict) and is_ours(h.get("command", "")):
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
    kept = [e for e in stop if not our_entry(e)]
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
    ap.add_argument("--hook-only", action="store_true", help="register only the Stop hook, without copying the skill")
    ap.add_argument("--uninstall", action="store_true", help="remove the skill, the hook script and the hook")
    ap.add_argument("--target", default=str(Path.home() / ".claude" / "skills"), help="skills folder")
    ap.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"), help="settings.json to edit")
    args = ap.parse_args(argv)

    dest = Path(args.target) / "receipts"
    settings = Path(args.settings)
    hook_dir = settings.parent / "receipts-hook"   # where --hook-only keeps the script

    if args.uninstall:
        for folder in (dest, hook_dir):
            if folder.exists():
                shutil.rmtree(folder)
                print(f"Removed {folder}")
        if remove_hook(settings):
            print(f"Removed the Stop hook from {settings}")
        return 0

    if not (SRC / "SKILL.md").exists():
        sys.exit(f"Skill sources not found at {SRC}")
    if args.hook or args.hook_only:
        load_settings(settings)   # fail early, before anything is copied, if settings.json is unusable

    if args.hook_only:
        hook_dir.mkdir(parents=True, exist_ok=True)
        script = hook_dir / "stop_gate.py"
        shutil.copyfile(SRC / "scripts" / "stop_gate.py", script)
        print(f"Copied the hook script to {script}")
        print(f"Stop hook {add_hook(settings, hook_command(script))} in {settings} (backup: {settings.name}.receipts.bak)")
        print("Start a new Claude Code session to load it.")
        return 0

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"Installed the skill to {dest}")
    if args.hook:
        print(f"Stop hook {add_hook(settings, hook_command(dest / 'scripts' / 'stop_gate.py'))} in {settings} (backup: {settings.name}.receipts.bak)")
    print("Start a new Claude Code session to load it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
