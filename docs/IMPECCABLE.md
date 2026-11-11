# Impeccable design workflow: setup record and finding log

## Setup (Nov 11 2026)

| | |
|---|---|
| Toolkit | Impeccable, open source (Apache-2.0), https://github.com/pbakaus/impeccable |
| npm CLI | `impeccable@4.8.2` (used for `detect`) |
| Skill files | copied from upstream commit `fead7938331bb92129e3c5ce14f600611067bd06` into `.claude/skills/impeccable` and `.claude/agents` |
| Why copied, not installed | `npx impeccable install` failed: its download host `impeccable.style` is blocked by this environment's network proxy. Upstream documents a manual copy path; the files were reviewed before copying. |
| Context files | `PRODUCT.md` written after a founder interview (confirmed facts only). `DESIGN.md` not yet written. |

**Deliberately not enabled**
- **Auto-run design hook** (`.claude/settings.json`): it runs a downloaded engine binary on every edit and turn end. Not added until the founder approves it. The detector is run explicitly instead.
- **Live mode** (`/impeccable live`): upstream documents that Apply can launch an agent CLI with approvals and sandboxing off. Not used on this repository.

**Detector scope:** source scan covers pattern rules only; the rendered-page scan sees only the tab visible at load (Workspace). The other tabs (Review, Library, Overview, Tools, Prompt Engine, Settings, Admin) have not had a rendered contrast pass. Toolkit findings are inputs to judgment, not authority over messaging, workflows or architecture.

Reproduce:
```bash
npx impeccable@4.8.2 detect --json consumer-dashboard.html index.html admin-dashboard.html auth.html comparison.html product.html assets/style.css js/platform.js
CHROME_PATH=<chrome> npx impeccable@4.8.2 detect --json http://localhost:8476/consumer
```

## Baseline (before any design change): 148 source + 9 rendered findings

Raw output: `docs/impeccable-baseline-source.json`, `docs/impeccable-baseline-rendered.json`.

| Rule | Count | Why it matters here |
|---|---:|---|
| tiny-text (11px body) | 43 | legibility; below the accessibility baseline in PRODUCT.md |
| undersized-ui-text (<11px functional) | 20 | labels and controls too small to read comfortably |
| extreme-negative-tracking | 17 | letter-spacing as tight as -0.16em on landing headline |
| cramped-padding | 13 | content flush against container edges |
| dark-glow | 9 | zero-offset neon glows |
| kicker-above-heading / hero-eyebrow-chip | 9 | generic AI-landing pattern |
| border-accent-on-rounded + side-tab | 12 | the most recognizable "AI card" tell |
| overused-font | 7 | Inter as primary face |
| low-contrast / gray-on-color | 8 | one is 1.4:1 (need 4.5:1) |
| pulsing-dot, gradient-text, skipped-heading, nested-cards, flat-type-hierarchy, stripes | 11 | |

By file: index.html 55, consumer-dashboard.html 53, comparison.html 21, admin-dashboard.html 9, auth.html 6, product.html 2, style.css 2.

## Finding log

Updated as fixes land. Status: open / fixed (verified in running product) / declined (reason).

| Area | Finding | Status |
|---|---|---|
| (to be filled as each pass completes) | | |
