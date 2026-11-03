#!/usr/bin/env python3
"""Receipts: keep a ledger of proof for a task and render it as one HTML card.

A task has acceptance criteria. Each criterion ends up verified, failed or
unverified, backed by evidence (a command that was really run, a screenshot that
was really looked at). The verdict is derived, never typed by hand:
  FAILED    any criterion failed
  PARTIAL   some criterion is still pending / unverified
  VERIFIED  every criterion verified

Subcommands: init, run, shot, attach, mark, unverified, render, check, status.
State lives in ./.receipts (override with --dir or $RECEIPTS_DIR).
"""
import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

__version__ = "1.0.0"

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"|(?i:(password|has[łl]o|token|secret|api[_-]?key))\s*[:=]\s*\S+)"
)
STATUSES = ("pending", "verified", "failed", "unverified")


# ---- storage ---------------------------------------------------------------
def base_dir(args):
    return Path(args.dir or os.environ.get("RECEIPTS_DIR") or ".receipts")


def ledger_path(args):
    b = base_dir(args)
    rid = args.id
    if not rid:
        cur = b / "current"
        if not cur.exists():
            sys.exit("No active receipt. Run: receipt.py init --task ... --criteria ...")
        rid = cur.read_text(encoding="utf-8").strip()
    return b / f"{rid}.json"


def load(args):
    p = ledger_path(args)
    if not p.exists():
        sys.exit(f"Receipt not found: {p}")
    return p, json.loads(p.read_text(encoding="utf-8"))


def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def redact(s):
    return SECRET.sub("[REDACTED]", s)


def verdict(data):
    st = [c["status"] for c in data["criteria"]]
    if not st:
        return "INVALID"
    if "failed" in st:
        return "FAILED"
    if all(s == "verified" for s in st):
        return "VERIFIED"
    return "PARTIAL"


def crit(data, n):
    if not 1 <= n <= len(data["criteria"]):
        sys.exit(f"Criterion {n} does not exist (1..{len(data['criteria'])})")
    return data["criteria"][n - 1]


# ---- subcommands -----------------------------------------------------------
def cmd_init(args):
    b = base_dir(args)
    b.mkdir(parents=True, exist_ok=True)
    rid = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    data = dict(id=rid, created=dt.datetime.now().isoformat(timespec="seconds"), task=args.task,
                cwd=str(Path.cwd()), criteria=[dict(text=t, status="pending", note="") for t in args.criteria],
                evidence=[], not_verified=[])
    p = b / f"{rid}.json"
    save(p, data)
    (b / "current").write_text(rid, encoding="utf-8")
    print(f"Receipt {rid} opened with {len(args.criteria)} criteria. Ledger: {p}")


def cmd_run(args):
    p, data = load(args)
    t0 = time.time()
    try:
        r = subprocess.run(args.cmd, shell=True, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=args.timeout)
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired as e:
        out, code = f"(timed out after {args.timeout}s)\n{(e.stdout or '')}", 124
    lines = out.strip().splitlines()
    tail = redact("\n".join(lines[-args.tail:]))
    ev = dict(kind="cmd", cmd=redact(args.cmd), exit=code, seconds=round(time.time() - t0, 1),
              output=tail, total_lines=len(lines), criterion=args.criterion)
    data["evidence"].append(ev)
    if args.criterion:
        c = crit(data, args.criterion)
        c["status"] = "verified" if code == 0 else "failed"
        c["note"] = c["note"] or f"{clip(args.cmd, 60)} (exit {code})"
    save(p, data)
    print(tail[-1500:])
    print(f"\n[receipt] exit={code} recorded" + (f", criterion {args.criterion} -> {data['criteria'][args.criterion-1]['status']}" if args.criterion else ""))
    sys.exit(0 if code == 0 else 1)


def find_browser():
    cands = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for c in cands:
        if Path(c).exists():
            return c
    for n in ("google-chrome", "chromium", "chromium-browser", "chrome", "microsoft-edge"):
        w = shutil.which(n)
        if w:
            return w
    return None


MIN_WINDOW = 500


def crop_png(path, w, h):
    """Trim the blank strip beside the iframe when Pillow is available; harmless if not."""
    try:
        from PIL import Image
        im = Image.open(path)
        im.crop((0, 0, min(w, im.width), min(h, im.height))).save(path)
    except Exception:
        pass


def cmd_shot(args):
    p, data = load(args)
    br = find_browser()
    if not br:
        sys.exit("No Chrome/Edge/Chromium found for headless screenshots. Take screenshots with another tool and use: receipt.py attach")
    target = args.target
    if not re.match(r"^[a-z]+://", target):
        f = Path(target).resolve()
        if not f.exists():
            sys.exit(f"Target not found: {target}")
        target = f.as_uri()
    outdir = (base_dir(args) / data["id"]).resolve()  # browsers resolve relative paths against their own cwd
    outdir.mkdir(parents=True, exist_ok=True)
    made = []
    for w in [int(x) for x in args.widths.split(",")]:
        h = args.height or (844 if w < 600 else 900)
        out = outdir / f"shot-{len(data['evidence']) + 1}-{w}x{h}.png"
        shoot, win_w = target, w
        if w < MIN_WINDOW:
            # Headless Chrome/Edge never lays out narrower than ~500px, so a "390px" window would silently be
            # a 500px layout cropped to 390. An iframe gives the page a genuine 390px viewport instead.
            wrap = outdir / f"_wrap-{w}.html"
            wrap.write_text(f'<!doctype html><meta charset="utf-8"><body style="margin:0;background:#fff">'
                            f'<iframe src="{html.escape(target)}" style="width:{w}px;height:{h}px;border:0;display:block"></iframe>',
                            encoding="utf-8")
            shoot, win_w = wrap.as_uri(), MIN_WINDOW
        with tempfile.TemporaryDirectory() as prof:
            cmd = [br, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                   f"--window-size={win_w},{h}", f"--virtual-time-budget={args.wait}", f"--screenshot={out}", shoot]
            subprocess.run(cmd, capture_output=True, timeout=90)
        if not out.exists():
            sys.exit(f"Screenshot failed at {w}px")
        if w < MIN_WINDOW:
            crop_png(out, w, h)
        data["evidence"].append(dict(kind="shot", path=str(out), width=w, height=h, target=args.target,
                                     criterion=args.criterion, seen=False))
        made.append(str(out))
    save(p, data)
    print("Screenshots saved (a screenshot alone proves nothing: open each image, look at it, then run `mark`):")
    for m in made:
        print("  ", m)


def cmd_attach(args):
    p, data = load(args)
    src = Path(args.file)
    if not src.exists():
        sys.exit(f"File not found: {src}")
    outdir = base_dir(args) / data["id"]
    outdir.mkdir(parents=True, exist_ok=True)
    dst = outdir / f"attach-{len(data['evidence']) + 1}-{src.name}"
    shutil.copyfile(src, dst)
    data["evidence"].append(dict(kind="shot", path=str(dst), width=0, height=0, target=args.label or src.name,
                                 criterion=args.criterion, seen=False))
    save(p, data)
    print(f"Attached {dst}")


def cmd_mark(args):
    p, data = load(args)
    c = crit(data, args.criterion)
    if args.status == "verified" and not args.note:
        sys.exit("Marking verified requires --note: say what you observed (what you saw or what the output showed).")
    c["status"], c["note"] = args.status, args.note or c["note"]
    for ev in data["evidence"]:
        if ev["kind"] == "shot" and ev.get("criterion") == args.criterion:
            ev["seen"] = True
    save(p, data)
    print(f"Criterion {args.criterion} -> {args.status}. Verdict now: {verdict(data)}")


def cmd_unverified(args):
    p, data = load(args)
    data["not_verified"].append(args.text)
    save(p, data)
    print("Recorded under 'Not verified'.")


def clip(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def git_summary():
    try:
        if subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True).returncode:
            return None
        st = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        stat = subprocess.run(["git", "diff", "--stat", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        return (st.strip() + "\n\n" + stat.strip()).strip()
    except FileNotFoundError:
        return None


CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1c1b19;--mute:#6b6860;--line:#e3e0d8;--ok:#14663a;--okbg:#e2f3ea;
--bad:#a3261a;--badbg:#fbe6e3;--mid:#8a5a00;--midbg:#fcf0d4;--code:#f1efe9}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141413;--card:#1e1d1b;--ink:#efede6;--mute:#a09c92;
--line:#33312d;--ok:#6fd49b;--okbg:#17331f;--bad:#ff8f84;--badbg:#3a1a17;--mid:#f1c15f;--midbg:#392c10;--code:#171614}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;overflow-wrap:anywhere}
.top>div,.row>div,.card{min-width:0}
main{max-width:760px;margin:0 auto;padding:28px 16px 56px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin-bottom:16px}
.top{display:flex;gap:16px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap}
h1{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);margin:0 0 6px;font-weight:600}
.task{font-size:20px;font-weight:650;margin:0;max-width:30em}
.stamp{border:2px solid currentColor;border-radius:8px;padding:6px 14px;font-weight:800;letter-spacing:.12em;font-size:15px;transform:rotate(-2deg)}
.VERIFIED{color:var(--ok)}.FAILED{color:var(--bad)}.PARTIAL,.INVALID{color:var(--mid)}
.meta{color:var(--mute);font-size:13px;margin-top:10px}
h2{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin:0 0 12px}
.row{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--line)}.row:first-of-type{border-top:0}
.chip{flex:none;align-self:flex-start;font-size:11px;font-weight:700;letter-spacing:.06em;padding:3px 8px;border-radius:99px;text-transform:uppercase}
.chip.verified{background:var(--okbg);color:var(--ok)}.chip.failed{background:var(--badbg);color:var(--bad)}
.chip.pending,.chip.unverified{background:var(--midbg);color:var(--mid)}
.note{color:var(--mute);font-size:13px;margin-top:2px}
pre{background:var(--code);border-radius:8px;padding:10px 12px;overflow:auto;font:12px/1.45 ui-monospace,Consolas,monospace;margin:8px 0 0;white-space:pre-wrap;word-break:break-word}
details{border-top:1px solid var(--line);padding:10px 0}details:first-of-type{border-top:0}
summary{cursor:pointer;font-weight:600;font-size:14px}.exit{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--mute)}
.shots{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start}.shot{max-width:100%}.shot img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:8px;display:block}
.shot.phone img{max-width:240px}.cap{font-size:12px;color:var(--mute);margin-top:4px}
ul{margin:0;padding-left:20px}li{margin:4px 0}
"""


def cmd_render(args):
    p, data = load(args)
    v = verdict(data)
    e = html.escape
    rows = []
    for i, c in enumerate(data["criteria"], 1):
        note = f'<div class="note">{e(c["note"])}</div>' if c["note"] else ""
        rows.append(f'<div class="row"><span class="chip {c["status"]}">{c["status"]}</span>'
                    f'<div><div>{i}. {e(c["text"])}</div>{note}</div></div>')
    cmds, shots = [], []
    for ev in data["evidence"]:
        label = f' (criterion {ev["criterion"]})' if ev.get("criterion") else ""
        if ev["kind"] == "cmd":
            cmds.append(f'<details><summary>{e(clip(ev["cmd"], 90))}{e(label)} '
                        f'<span class="exit">exit {ev["exit"]} · {ev["seconds"]}s</span></summary>'
                        f'<pre>{e(ev["output"] or "(no output)")}</pre></details>')
        else:
            f = Path(ev["path"])
            if not f.exists():
                continue
            b64 = base64.b64encode(f.read_bytes()).decode()
            mime = "image/png" if f.suffix.lower() == ".png" else "image/jpeg"
            seen = "" if ev.get("seen") else " (not yet reviewed)"
            size = f'{ev["width"]}px' if ev.get("width") else ""
            cls = "phone" if 0 < ev.get("width", 0) < 600 else ""
            shots.append(f'<div class="shot {cls}"><img alt="screenshot" src="data:{mime};base64,{b64}">'
                         f'<div class="cap">{e(size)} {e(str(ev["target"]))}{e(label)}{e(seen)}</div></div>')
    nv = "".join(f"<li>{e(x)}</li>" for x in data["not_verified"])
    pend = [i for i, c in enumerate(data["criteria"], 1) if c["status"] in ("pending", "unverified")]
    if pend:
        nv += f"<li>Criteria without proof: {', '.join(map(str, pend))}</li>"
    g = git_summary()
    body = f"""<main>
<div class="card"><div class="top"><div><h1>Receipt</h1><p class="task">{e(data["task"])}</p></div>
<div class="stamp {v}">{v}</div></div>
<div class="meta">{e(data["created"])} · {e(data["cwd"])} · {len(data["criteria"])} criteria · {len(data["evidence"])} pieces of evidence</div></div>
<div class="card"><h2>Acceptance criteria</h2>{"".join(rows)}</div>
{f'<div class="card"><h2>Commands that were run</h2>{"".join(cmds)}</div>' if cmds else ""}
{f'<div class="card"><h2>Screenshots</h2><div class="shots">{"".join(shots)}</div></div>' if shots else ""}
<div class="card"><h2>Not verified</h2>{f"<ul>{nv}</ul>" if nv else "<div class='note'>Nothing declared. Everything above was checked.</div>"}</div>
{f'<div class="card"><h2>Changes</h2><pre>{e(g)}</pre></div>' if g else ""}
</main>"""
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>Receipt {e(data["id"])}</title><style>{CSS}</style></head><body>{body}</body></html>')
    out = base_dir(args) / f"{data['id']}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"Receipt card: {out.resolve()}\nVerdict: {v}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())


def cmd_check(args):
    p, data = load(args)
    v = verdict(data)
    print(f"Verdict: {v}")
    for i, c in enumerate(data["criteria"], 1):
        if c["status"] != "verified":
            print(f"  {i}. [{c['status']}] {c['text']}")
    sys.exit(0 if v == "VERIFIED" else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"receipts {__version__}")
    ap.add_argument("--dir", default="")
    ap.add_argument("--id", default="", help="receipt id (default: current)")
    sub = ap.add_subparsers(dest="sub", required=True)

    s = sub.add_parser("init"); s.add_argument("--task", required=True); s.add_argument("--criteria", nargs="+", required=True); s.set_defaults(f=cmd_init)
    s = sub.add_parser("run"); s.add_argument("--cmd", required=True); s.add_argument("--criterion", type=int, default=0)
    s.add_argument("--timeout", type=int, default=180); s.add_argument("--tail", type=int, default=30); s.set_defaults(f=cmd_run)
    s = sub.add_parser("shot"); s.add_argument("--target", required=True); s.add_argument("--widths", default="390,1280")
    s.add_argument("--height", type=int, default=0); s.add_argument("--wait", type=int, default=2500)
    s.add_argument("--criterion", type=int, default=0); s.set_defaults(f=cmd_shot)
    s = sub.add_parser("attach"); s.add_argument("--file", required=True); s.add_argument("--label", default="")
    s.add_argument("--criterion", type=int, default=0); s.set_defaults(f=cmd_attach)
    s = sub.add_parser("mark"); s.add_argument("--criterion", type=int, required=True)
    s.add_argument("--status", choices=STATUSES[1:], required=True); s.add_argument("--note", default=""); s.set_defaults(f=cmd_mark)
    s = sub.add_parser("unverified"); s.add_argument("text"); s.set_defaults(f=cmd_unverified)
    s = sub.add_parser("render"); s.add_argument("--open", action="store_true"); s.set_defaults(f=cmd_render)
    s = sub.add_parser("check"); s.set_defaults(f=cmd_check)
    s = sub.add_parser("status"); s.set_defaults(f=cmd_check)
    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
