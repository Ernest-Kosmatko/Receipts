# Changelog

## 1.1.0

- Packaged as a Claude Code plugin: `claude plugin marketplace add Ernest-Kosmatko/Receipts`, then `claude plugin install receipts@ernest-kosmatko`
- `docs/install-with-claude.md`, so Claude can install the skill from a single prompt
- `install.py --hook-only` registers the Stop hook for people who installed the plugin
- The skill now lives in `plugin/skills/receipts/`
- New README with a logo, a flow diagram and a verdict table

## 1.0.0

First release.

- `receipt.py` with `init`, `run`, `shot`, `attach`, `mark`, `unverified`, `render`, `check` and `status`
- Verdict computed from the criteria: FAILED, PARTIAL or VERIFIED
- Headless screenshots at real viewport widths, including phone widths below 500 px
- Self-contained HTML receipt with light and dark themes
- Optional Stop hook that blocks a completion claim without a receipt; quoted text and code are ignored
- `install.py` for installing the skill and the hook, with a backup of `settings.json`
