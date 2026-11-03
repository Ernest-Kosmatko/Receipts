# Changelog

## 1.0.0

First release.

- `receipt.py` with `init`, `run`, `shot`, `attach`, `mark`, `unverified`, `render`, `check` and `status`
- Verdict computed from the criteria: FAILED, PARTIAL or VERIFIED
- Headless screenshots at real viewport widths, including phone widths below 500 px
- Self-contained HTML receipt with light and dark themes
- Optional Stop hook that blocks a completion claim without a receipt; quoted text and code are ignored
- `install.py` for installing the skill and the hook, with a backup of `settings.json`
