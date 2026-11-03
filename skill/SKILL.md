---
name: receipts
description: Claude never says "done" without proof. Before reporting that any non-trivial task is finished (code change, bug fix, UI or visual change, build, config, script), use this skill to define acceptance criteria, run real checks (tests, build, the actual program, headless screenshots at phone and desktop width), look at the evidence, and hand the user a one-page HTML receipt with a derived verdict (VERIFIED / PARTIAL / FAILED) and an explicit list of what was not verified. Use it whenever you are about to write "done", "fixed", "gotowe", "działa", when the user says "prove it", "sprawdź to", "daj dowód", "are you sure", or complains that something was reported done but was broken.
---

# Receipts

The user should never have to check your work to find out whether it works. A receipt is the proof: what was promised, what was actually run or looked at, what the result was, and what is still unchecked. The verdict is computed from the evidence, so it cannot be talked up.

```bash
R="python -I ${CLAUDE_SKILL_DIR}/scripts/receipt.py"
```

Run it from the project root so the ledger lands in `./.receipts/` (suggest adding it to `.gitignore`). Outside a project, pass `--dir <scratch folder>` to every call.

## When to use it, and when not

Use it for any turn where you changed files and are about to report the outcome. Skip it only for trivial or purely conversational work (a typo, a rename, answering a question). If you skip it on a change, do not write "done"; write what you changed and that you did not verify it.

## Workflow

### 1. Write the criteria first
Turn the user's request into 2-6 acceptance criteria that can each be proven. Write them in the user's language, concrete and observable, including constraints the user already stated in the conversation (platform, style, "no emoji", reference colors). A vague criterion ("looks good") cannot be verified: sharpen it ("the header fits a 390px screen with no horizontal scroll").

```bash
$R init --task "Portfolio page for YouTube thumbnails" --criteria \
  "Page loads with no console errors" \
  "Gallery fits a 390px phone screen without horizontal scroll" \
  "Colors match the reference the user pasted" \
  "No emoji anywhere in the page text"
```

### 2. Get evidence, one criterion at a time
- **Anything executable:** run it through the ledger so exit code and output are recorded: `$R run --cmd "npm test" --criterion 1`. Exit 0 marks the criterion verified, non-zero marks it failed. Use the narrowest command that really exercises the claim; "the file was written" is not proof that the program works.
- **Anything visual:** `$R shot --target index.html --widths 390,1280 --criterion 2` (headless Chrome/Edge, accepts a file or URL). Then **open every screenshot with the Read tool and look at it**. A screenshot alone proves nothing; the criterion stays `pending` until you have looked.
- **Compare against references:** if the user supplied an image, colors or a layout, view it next to your result and say which differences you see.
- **Something you cannot run** (needs the user's device, a secret, a paid service): do not fake it. Record it: `$R unverified "Android install not tested: no device available"`.

### 3. Mark what you observed
```bash
$R mark --criterion 2 --status verified --note "390px: gallery stacks to one column, no horizontal scroll, header intact"
$R mark --criterion 3 --status failed   --note "accent is #2b6 in the page, reference is #1f7a5a"
```
`verified` requires a note describing what you saw or what the output showed. Mark `failed` when it failed, even if you plan to fix it.

### 4. Fix, then re-prove
If anything failed, fix it and re-run the same check on the same criterion; the status updates and the old evidence stays visible. Do not delete a failure to get a better verdict.

### 5. Render and report
```bash
$R render --open
$R check        # exit 0 only when every criterion is verified
```
Tell the user, in their language, in this order: the verdict, what was proven (one line per criterion), what is **not** verified, and the path to the card. Do not paste the whole receipt.

Verdict rules (computed, not chosen): any `failed` gives FAILED; any `pending` or `unverified` gives PARTIAL; only all-verified gives VERIFIED. Never describe a PARTIAL or FAILED receipt as done.

## Honesty rules

- Never mark `verified` from reading code, from a successful write, or from "it should work". Verified means you ran it or looked at it.
- A passing test suite only proves what the tests cover; if the change is outside them, say so under `unverified`.
- Report failures first and plainly. A FAILED receipt delivered with a fix plan is a good outcome; a VERIFIED stamp on unverified work is the one thing this skill exists to prevent.
- No emoji and no decorative language in criteria, notes or the report.

## Optional: enforce it with a Stop hook

Advice gets forgotten under pressure; a hook does not. `scripts/stop_gate.py` blocks the end of a turn once when files were edited, the final message claims completion, and no receipt ran after the last edit. Words inside quotes, code spans and blockquotes are ignored. It never loops and can be disabled with `RECEIPTS_GATE=off`.

It changes the user's `settings.json`, so **ask before installing it**. The installer in the repository does it safely (backup, no duplicates):

```bash
python install.py --hook
```

## Limits

Headless Chrome/Edge cannot lay out narrower than about 500px, so for widths below 500 the tool loads the page inside an iframe of the exact width (a true 390px viewport, media queries included) and crops the result when Pillow is installed. A site that forbids framing (X-Frame-Options) will show blank at phone width: use a local copy or another tool. Screenshots capture the first screen only (set `--height` for taller views) and cannot log in or click. For interactive flows use a browser tool, save or `attach` the screenshot, and still mark criteria from what you saw. The completion-claim detector in the hook is keyword-based (Polish and English) and will miss unusual phrasing.
