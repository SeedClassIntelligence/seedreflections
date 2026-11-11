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
| Workspace, phone and tablet | Project memory panel stayed 244px wide (an id-scoped fixed width beat the "100% when stacked" rule); "Add or connect" wrapped onto three lines (action row had no wrap). | **Fixed**: panel 244 to 348px at 390px wide, button one line (71x47 to 127x30). Desktop unchanged. Verified at 390 / 768 / 1440. |
| Phone navigation | The bottom bar holds 8 destinations but fits 4: Tools, Prompt Engine, Settings and Admin sat off-screen with no hint. | **Fixed**: a "More" menu for the four secondary destinations (focus moves in, Escape and outside-tap close it, items reachable). Desktop nav unchanged (all 8 visible). |
| Contrast (measured on the rendered page, every tab) | 9 real failures: amber "unreadable" notice 3.8:1, Tools status text 3.66:1, tool mark 4.27:1. The detector's cream-surface findings (1.4:1 etc.) are **dead CSS that is never rendered**, so they are not real failures. | **Fixed**: 0 text failures on all 10 tabs (the 2 remaining are colour emoji, not text). |
| Landing page (index.html) | **Two scripts failed to parse, so none of their code ran** (2 SyntaxErrors on every load). They were duplicates of working code earlier in the file, left by an old patch script: literal line breaks inside string literals, plus a variable name missing from a declaration. They also contained placeholder Stripe *test* checkout links that would have gone live if the syntax had simply been repaired. Nothing in the markup called them. | **Fixed by removing the dead blocks** (about 1,200 lines): zero runtime change, zero errors, no dead handlers. |
| Admin dashboard (admin-dashboard.html) | **The whole admin script failed to parse** (unescaped quotes in the user-table click handlers), so the admin page had no working JavaScript. Repairing only the quotes would have exposed **stored XSS**: usernames, emails, plan, status, webhook events and log lines were written into the page as raw HTML (a user named with an img onerror payload would run code in the admin's browser). | **Fixed with escaping**: every interpolation escaped; handler arguments passed as escaped JSON string literals. Verified in a browser: page loads with 0 errors; a hostile name renders as literal text with nothing injected; Plan and Delete buttons receive the exact strings even containing quotes and alert(1). |
| product.html, admin header | Phone-width overflow (126px and 105px): a 1fr grid column that grew to its content; a header row that never wrapped. | **Fixed**; all six pages now 0 overflow at 1440 and 390. |
| Landing, comparison, sign-in, admin, product | 95 style findings (eyebrow chips, kickers, -0.16em tracking, Inter, glows, side-tab accents) | Open: not yet touched. These are judgment calls for the visual redesign, not breakage. |
| Dashboard cockpit padding | 5 "cramped-padding" findings on the joined cockpit shell | **Declined**: the shell is one bordered panel whose heads and bodies carry their own padding; visually correct. |
| Not yet run | `critique` and `audit` (agent commands), `DESIGN.md` (`document`), rendered contrast on tabs other than Workspace, keyboard-focus audit, `harden` empty/error states | Open |
