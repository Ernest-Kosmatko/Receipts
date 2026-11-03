# Install Receipts with Claude

This page is written so that Claude Code can follow it on its own. It is also the exact list of steps if you prefer to do it yourself.

## Ask Claude to do it

Paste this into Claude Code:

```text
Install the Receipts skill from https://github.com/Ernest-Kosmatko/Receipts by following docs/install-with-claude.md
```

## Steps for the agent

Receipts is a Claude Code skill that makes the agent prove its work before it says "done". Install it with the plugin system when `claude` is available, and fall back to the manual route otherwise.

### 1. Plugin route (preferred)

Run these in the shell:

```bash
claude plugin marketplace add Ernest-Kosmatko/Receipts
claude plugin install receipts@ernest-kosmatko
```

Check the result with `claude plugin list`. The entry `receipts@ernest-kosmatko` should be enabled. The skill is then available as `/receipts:receipts`, and Claude also uses it on its own.

### 2. Manual route (when the plugin commands are not available)

```bash
git clone https://github.com/Ernest-Kosmatko/Receipts.git
cd Receipts
python install.py
```

This copies the skill to `~/.claude/skills/receipts`. Check it with:

```bash
python ~/.claude/skills/receipts/scripts/receipt.py --version
```

Use `python3` if `python` is not on the path. Python 3.9 or newer is required. There are no other dependencies.

### 3. The Stop hook is optional

The hook blocks a "done" when files were edited and no receipt was produced. It edits `~/.claude/settings.json`, so **ask the user before installing it**. Do not install it by default.

If the user agrees, from a clone of the repository:

```bash
python install.py --hook         # skill and hook, manual route
python install.py --hook-only    # hook only, when the skill came from the plugin
```

The installer backs up `settings.json` first, never overwrites a file it cannot parse, and never adds the hook twice. Remove everything with `python install.py --uninstall`.

### 4. Finish

Tell the user to start a new Claude Code session. Skills and plugins are loaded at the start of a session, so the current one will not see the new skill.

## If something goes wrong

- **`claude: command not found`**: use the manual route
- **`python: command not found`**: try `python3`, or install Python 3.9 or newer
- **Marketplace not found**: check the owner and repository name, `Ernest-Kosmatko/Receipts`, and that the repository is public
- **Screenshots fail**: `shot` needs Chrome, Edge or Chromium. Everything else works without a browser
