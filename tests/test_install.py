import json
import subprocess
import sys
from pathlib import Path

INSTALL = Path(__file__).resolve().parent.parent / "install.py"


def install(tmp_path, *flags, settings_text=None):
    settings = tmp_path / "settings.json"
    if settings_text is not None:
        settings.write_text(settings_text, encoding="utf-8")
    r = subprocess.run([sys.executable, str(INSTALL), "--target", str(tmp_path / "skills"), "--settings", str(settings), *flags],
                       capture_output=True, text=True, encoding="utf-8")
    return r, settings


def hooks(settings):
    return json.loads(settings.read_text(encoding="utf-8")).get("hooks", {}).get("Stop", [])


def test_copies_the_skill(tmp_path):
    r, _ = install(tmp_path)
    assert r.returncode == 0, r.stderr
    dest = tmp_path / "skills" / "receipts"
    assert (dest / "SKILL.md").is_file()
    assert (dest / "scripts" / "receipt.py").is_file() and (dest / "scripts" / "stop_gate.py").is_file()


def test_installing_twice_replaces_instead_of_nesting(tmp_path):
    install(tmp_path)
    (tmp_path / "skills" / "receipts" / "stale.txt").write_text("old", encoding="utf-8")
    install(tmp_path)
    assert not (tmp_path / "skills" / "receipts" / "stale.txt").exists()
    assert not (tmp_path / "skills" / "receipts" / "receipts").exists()


def test_hook_is_added_once_and_existing_settings_survive(tmp_path):
    r, settings = install(tmp_path, "--hook", settings_text=json.dumps({"switchModelsOnFlag": True}))
    assert r.returncode == 0, r.stderr
    install(tmp_path, "--hook")
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["switchModelsOnFlag"] is True
    stop = hooks(settings)
    assert len(stop) == 1
    assert stop[0]["hooks"][0]["type"] == "command" and "receipts/scripts/stop_gate.py" in stop[0]["hooks"][0]["command"]


def test_hook_keeps_other_stop_hooks(tmp_path):
    other = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo other"}]}]}}
    _, settings = install(tmp_path, "--hook", settings_text=json.dumps(other))
    commands = [h["command"] for e in hooks(settings) for h in e["hooks"]]
    assert "echo other" in commands and len(commands) == 2


def test_settings_are_backed_up_before_a_change(tmp_path):
    original = json.dumps({"theme": "dark"})
    _, settings = install(tmp_path, "--hook", settings_text=original)
    assert (tmp_path / "settings.json.receipts.bak").read_text(encoding="utf-8") == original


def test_invalid_settings_json_is_left_alone(tmp_path):
    r, settings = install(tmp_path, "--hook", settings_text="{ not json")
    assert r.returncode != 0 and settings.read_text(encoding="utf-8") == "{ not json"
    assert not (tmp_path / "skills" / "receipts").exists()   # nothing half-installed


def test_uninstall_removes_the_skill_and_only_our_hook(tmp_path):
    other = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo other"}]}]}}
    _, settings = install(tmp_path, "--hook", settings_text=json.dumps(other))
    r, _ = install(tmp_path, "--uninstall")
    assert r.returncode == 0
    assert not (tmp_path / "skills" / "receipts").exists()
    commands = [h["command"] for e in hooks(settings) for h in e["hooks"]]
    assert commands == ["echo other"]


def test_uninstall_cleans_up_an_empty_hooks_section(tmp_path):
    _, settings = install(tmp_path, "--hook", settings_text="{}")
    install(tmp_path, "--uninstall")
    assert json.loads(settings.read_text(encoding="utf-8")) == {}


def test_hook_only_registers_the_hook_without_copying_the_skill(tmp_path):
    r, settings = install(tmp_path, "--hook-only")
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "skills" / "receipts").exists()
    assert (tmp_path / "receipts-hook" / "stop_gate.py").is_file()
    stop = hooks(settings)
    assert len(stop) == 1 and "receipts-hook/stop_gate.py" in stop[0]["hooks"][0]["command"]


def test_hook_only_twice_does_not_duplicate_the_hook(tmp_path):
    install(tmp_path, "--hook-only")
    _, settings = install(tmp_path, "--hook-only")
    assert len(hooks(settings)) == 1


def test_switching_between_hook_modes_updates_in_place(tmp_path):
    install(tmp_path, "--hook")
    _, settings = install(tmp_path, "--hook-only")
    stop = hooks(settings)
    assert len(stop) == 1 and "receipts-hook" in stop[0]["hooks"][0]["command"]


def test_uninstall_removes_the_hook_script_folder_too(tmp_path):
    _, settings = install(tmp_path, "--hook-only")
    install(tmp_path, "--uninstall")
    assert not (tmp_path / "receipts-hook").exists() and hooks(settings) == []
