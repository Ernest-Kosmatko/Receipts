"""Checks the Claude Code plugin packaging against the rules in the plugin documentation."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
ID_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def entry_and_manifest():
    entry = load(MARKETPLACE)["plugins"][0]
    root = ROOT / entry["source"]
    return entry, root, load(root / ".claude-plugin" / "plugin.json")


def test_marketplace_has_the_required_fields():
    data = load(MARKETPLACE)
    assert data["name"] and data["owner"]["name"] and isinstance(data["plugins"], list) and data["plugins"]
    assert data.get("description"), "the validator warns about a missing description"


def test_marketplace_and_plugin_names_are_valid_ids():
    data = load(MARKETPLACE)
    entry, _, manifest = entry_and_manifest()
    for name in (data["name"], entry["name"], manifest["name"]):
        assert ID_PART.match(name), name
        assert not name.lower().startswith(RESERVED_PREFIXES) and name.lower() not in {"claude", "anthropic", "claude-code"}
    assert data["name"].lower() not in {"agent-skills", "claude-plugins-official", "claude-code-plugins"}


def test_entry_name_matches_the_manifest_name():
    entry, _, manifest = entry_and_manifest()
    assert entry["name"] == manifest["name"]


def test_relative_source_is_valid_and_exists():
    entry, root, _ = entry_and_manifest()
    assert entry["source"].startswith("./") and ".." not in entry["source"] and "\\" not in entry["source"]
    assert root.is_dir()


def test_plugin_holds_the_skill_in_the_default_location():
    _, root, _ = entry_and_manifest()
    skill = root / "skills" / "receipts"
    assert (skill / "SKILL.md").is_file()
    assert (skill / "scripts" / "receipt.py").is_file() and (skill / "scripts" / "stop_gate.py").is_file()


def test_skill_frontmatter_names_the_skill():
    _, root, _ = entry_and_manifest()
    text = (root / "skills" / "receipts" / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1)
    assert re.search(r"^name: receipts$", front, re.M) and re.search(r"^description: \S", front, re.M)


def test_manifest_urls_are_urls_and_version_matches_the_project():
    _, _, manifest = entry_and_manifest()
    assert manifest["homepage"].startswith("https://") and manifest["repository"].startswith("https://")
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    assert manifest["version"] == version


def test_the_version_is_set_in_one_place_only():
    entry, _, _ = entry_and_manifest()
    assert "version" not in entry   # plugin.json wins, and the validator warns when both are set


def test_install_commands_in_the_readme_match_the_marketplace():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    data = load(MARKETPLACE)
    plugin = data["plugins"][0]["name"]
    assert f"claude plugin install {plugin}@{data['name']}" in readme
    assert "claude plugin marketplace add Ernest-Kosmatko/Receipts" in readme
