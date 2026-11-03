"""Keeps the repository plain: no emoji, no long dashes, no tool attribution in text files."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", ".receipts"}
BINARY = {".png", ".gif", ".mp4", ".jpg", ".jpeg", ".webp", ".ico"}


def _span(first, last):
    return chr(first) + "-" + chr(last)


# built from code points so this file stays plain ASCII
EMOJI = re.compile("[" + _span(0x1F300, 0x1FAFF) + _span(0x2600, 0x27BF) + chr(0xFE0F) + chr(0x2B50) + chr(0x2B06) + chr(0x2705) + "]")
LONG_DASH = chr(0x2014)
ATTRIBUTION = re.compile(r"co-authored-by|generated (with|by)|noreply@anthropic", re.I)


def text_files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS) and p.suffix.lower() not in BINARY:
            yield p


def read(p):
    return p.read_text(encoding="utf-8", errors="replace")


def test_no_emoji_in_text_files():
    offenders = [str(p.relative_to(ROOT)) for p in text_files() if EMOJI.search(read(p))]
    assert not offenders, offenders


def test_no_long_dashes_in_prose():
    offenders = [str(p.relative_to(ROOT)) for p in text_files() if p.suffix.lower() in {".md", ".txt"} and LONG_DASH in read(p)]
    assert not offenders, offenders


def test_no_tool_attribution_in_files_or_commit_messages():
    offenders = [str(p.relative_to(ROOT)) for p in text_files() if p.name != "test_style.py" and ATTRIBUTION.search(read(p))]
    assert not offenders, offenders
    if (ROOT / ".git").exists():
        log = subprocess.run(["git", "log", "--format=%B"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
        assert not ATTRIBUTION.search(log)
