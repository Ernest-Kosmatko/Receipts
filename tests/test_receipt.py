import base64
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "plugin" / "skills" / "receipts" / "scripts" / "receipt.py"
# 1x1 PNG
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


class Receipts:
    def __init__(self, tmp_path):
        self.dir = tmp_path / ".receipts"
        self.cwd = tmp_path

    def run(self, *args, check=False):
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--dir", str(self.dir), *args],
                           cwd=self.cwd, capture_output=True, text=True, encoding="utf-8")
        if check:
            assert r.returncode == 0, r.stdout + r.stderr
        return r

    def ledger(self):
        files = list(self.dir.glob("*.json"))
        assert len(files) == 1
        return json.loads(files[0].read_text(encoding="utf-8"))

    def html(self):
        files = list(self.dir.glob("*.html"))
        assert len(files) == 1
        return files[0].read_text(encoding="utf-8")


@pytest.fixture
def rc(tmp_path):
    return Receipts(tmp_path)


def test_version_flag(rc):
    r = rc.run("--version")
    assert r.returncode == 0 and re.match(r"receipts \d+\.\d+\.\d+", r.stdout)


def test_init_opens_a_receipt(rc):
    rc.run("init", "--task", "T", "--criteria", "first", "second", check=True)
    data = rc.ledger()
    assert [c["status"] for c in data["criteria"]] == ["pending", "pending"]
    assert (rc.dir / "current").read_text(encoding="utf-8") == data["id"]


def test_run_success_marks_criterion_verified(rc):
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    r = rc.run("run", "--cmd", 'python -c "print(42)"', "--criterion", "1")
    assert r.returncode == 0
    data = rc.ledger()
    assert data["criteria"][0]["status"] == "verified"
    assert data["evidence"][0]["exit"] == 0 and "42" in data["evidence"][0]["output"]


def test_run_failure_marks_criterion_failed_and_returns_nonzero(rc):
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    r = rc.run("run", "--cmd", 'python -c "import sys; sys.exit(3)"', "--criterion", "1")
    assert r.returncode == 1
    data = rc.ledger()
    assert data["criteria"][0]["status"] == "failed" and data["evidence"][0]["exit"] == 3


def test_run_without_criterion_leaves_statuses_alone(rc):
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    rc.run("run", "--cmd", 'python -c "print(1)"', check=True)
    assert rc.ledger()["criteria"][0]["status"] == "pending"


def test_timeout_is_recorded_as_a_failure(rc):
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    r = rc.run("run", "--cmd", 'python -c "import time; time.sleep(10)"', "--criterion", "1", "--timeout", "1")
    assert r.returncode == 1
    data = rc.ledger()
    assert data["evidence"][0]["exit"] == 124 and data["criteria"][0]["status"] == "failed"


def test_mark_verified_requires_a_note(rc):
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    r = rc.run("mark", "--criterion", "1", "--status", "verified")
    assert r.returncode != 0 and "requires --note" in (r.stdout + r.stderr)
    assert rc.ledger()["criteria"][0]["status"] == "pending"


def test_unknown_criterion_is_rejected(rc):
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    assert rc.run("mark", "--criterion", "5", "--status", "failed", "--note", "x").returncode != 0


def test_verdict_rules(rc):
    rc.run("init", "--task", "T", "--criteria", "a", "b", "c", check=True)
    assert "PARTIAL" in rc.run("check").stdout
    rc.run("mark", "--criterion", "1", "--status", "verified", "--note", "saw it", check=True)
    rc.run("mark", "--criterion", "2", "--status", "verified", "--note", "saw it", check=True)
    r = rc.run("check")
    assert r.returncode == 1 and "PARTIAL" in r.stdout and "3." in r.stdout
    rc.run("mark", "--criterion", "3", "--status", "failed", "--note", "broke", check=True)
    assert "FAILED" in rc.run("check").stdout
    rc.run("mark", "--criterion", "3", "--status", "verified", "--note", "fixed and rechecked", check=True)
    r = rc.run("check")
    assert r.returncode == 0 and "VERIFIED" in r.stdout


def test_unverified_status_keeps_the_verdict_partial(rc):
    rc.run("init", "--task", "T", "--criteria", "a", check=True)
    rc.run("mark", "--criterion", "1", "--status", "unverified", "--note", "needs a device", check=True)
    assert "PARTIAL" in rc.run("check").stdout


def test_check_without_an_active_receipt_fails(rc):
    r = rc.run("check")
    assert r.returncode != 0 and "No active receipt" in (r.stdout + r.stderr)


def test_render_lists_what_is_not_verified(rc):
    rc.run("init", "--task", "T", "--criteria", "a", "b", check=True)
    rc.run("mark", "--criterion", "1", "--status", "verified", "--note", "ok", check=True)
    rc.run("unverified", "Not tested on Android", check=True)
    rc.run("render", check=True)
    page = rc.html()
    assert "PARTIAL" in page and "Not tested on Android" in page and "Criteria without proof: 2" in page


def test_render_escapes_html(rc):
    rc.run("init", "--task", "<b>bold</b>", "--criteria", "<script>alert(1)</script>", check=True)
    rc.run("render", check=True)
    page = rc.html()
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page and "<b>bold</b>" not in page


def test_secrets_in_command_output_are_redacted(rc):
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    rc.run("run", "--cmd", 'python -c "print(\'token=hunter2hunter2 key sk-abcdefghijklmnopqrstuvwx\')"', check=True)
    out = rc.ledger()["evidence"][0]["output"]
    assert "hunter2" not in out and "sk-abcdefgh" not in out and "[REDACTED]" in out


def test_attached_image_is_embedded_in_the_card(rc, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(PNG)
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    rc.run("attach", "--file", str(img), "--label", "home page", "--criterion", "1", check=True)
    rc.run("render", check=True)
    assert "data:image/png;base64," in rc.html() and "not yet reviewed" in rc.html()


def test_marking_a_criterion_counts_its_screenshots_as_reviewed(rc, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(PNG)
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    rc.run("attach", "--file", str(img), "--criterion", "1", check=True)
    rc.run("mark", "--criterion", "1", "--status", "verified", "--note", "looked at it", check=True)
    rc.run("render", check=True)
    assert "not yet reviewed" not in rc.html()


def test_shot_of_a_missing_target_fails(rc):
    rc.run("init", "--task", "T", "--criteria", "c1", check=True)
    assert rc.run("shot", "--target", "does-not-exist.html").returncode != 0


def test_version_numbers_agree():
    root = Path(__file__).resolve().parent.parent
    in_script = re.search(r'__version__ = "([^"]+)"', SCRIPT.read_text(encoding="utf-8")).group(1)
    in_project = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    in_changelog = re.search(r"^## (\d+\.\d+\.\d+)", (root / "CHANGELOG.md").read_text(encoding="utf-8"), re.M).group(1)
    assert in_script == in_project == in_changelog


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_render_can_leave_out_the_git_summary(rc, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    rc.run("init", "--task", "T", "--criteria", "a", check=True)
    rc.run("render", check=True)
    assert "<h2>Changes</h2>" in rc.html()
    rc.run("render", "--no-changes", check=True)
    assert "<h2>Changes</h2>" not in rc.html()
