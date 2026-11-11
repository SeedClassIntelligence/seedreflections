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
| Dashboard, all tabs | 189 font-size declarations below 12px (8 to 11.5px): detector `tiny-text` + `undersized-ui-text` | **Fixed**: 12px floor. Dashboard source findings 53 to 19; rendered Workspace 9 to 4. Layout re-verified: no page overflow or clipped text on all 10 tabs at 1440 / 768 / 390 px. |
| Artifacts tab | Page overflowed horizontally by **123px at 768** and **411px at 390** (editor grid `280px 1fr` grew to the textarea width; metadata row never stacked). Pre-existing, found by the new all-tab narrow-width check, not caused by the font change (identical before). | **Fixed**: `minmax(0,1fr)` columns, stack below 900 / 600px. Verified. |
| Review cards | Kind label and "Phrase match" ran together ("DECISIONPhrase match"). | **Fixed** (10px gap). Verified in browser. |
| Review cards | The same sentence ("Direct decision language found in a user-authored source message. Human confirmation required.") repeats on every card; 250 cards render about 1,500 buttons; no filters, detail view or pagination. | Open: belongs to the Review work-inbox redesign. |
| Workspace, phone width | Project memory panel fills about two thirds of the width; "+ Add or connect" wraps to three lines; Tools / Prompt Engine / Settings not reachable from the 4-item bottom bar. | Open: Workspace layout pass. |
| Dashboard | low-contrast (4; one is 1.4:1) and gray-on-color on cream surfaces; 5 cramped-padding in the cockpit layout; 2 side-tab accents; overused font (Inter); 2 skipped headings | Open |
| Landing / comparison / auth / admin | 95 findings (index 55, comparison 21, admin 9, auth 6, product 2, style 2), including -0.16em tracking on the hero headline and the eyebrow-chip + kicker pattern | Open: not yet touched |
| Not yet run | `critique` and `audit` (agent commands), `DESIGN.md` (`document`), rendered contrast on tabs other than Workspace, keyboard-focus audit, `harden` empty/error states | Open |
