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
| **Landing page (index.html): full redesign** | The old page was the category template: centered hero with gradient text and an eyebrow chip, a metrics strip, eight sections of centered heading plus an equal-card grid, emoji icons, an auto-playing animated demo that never paused, and the product's actual mechanism (a finding tied to its source) buried halfway down. | **Replaced.** Direction: an *accession register* (roll ran degraded, no challengers; assigned candidate 4 of 7; contract in `.impeccable/surfaces/index-html.md`). Deep-green ground (the dashboard's green), pale ledger-green record sheets, one vermilion stamp ink; slab-serif display (Zilla Slab), grotesk body (Hanken Grotesk), mono only for data. Ruled tables and definition lists instead of cards; real app screenshots instead of icons. The first viewport leads with one worked example: a source passage with the found phrase marked, "phrase match, not an AI judgment", and working Accept / Defer / Dismiss that stamps the status. |
| Landing: copy and claims | The brief says a redesign keeps product truth. | All existing copy, headings, plan contents and prices preserved. Removed: the stats strip (including an unverified "100%" claim), the platform-logo strip, the animated demo. Added, from verified behaviour: an "Example: 3,000 of 3,005 conversations processed, 5 could not be read" line, and "It never claims access to private cloud chat history". Screenshots are labelled as a sample archive. |
| Landing: verification | | 0 JS errors; every in-page anchor and internal link resolves; the prompt wizard runs all 4 steps and generates a prompt; register works in all 4 states; no horizontal overflow at 1920 / 1440 / 1024 / 768 / 390 / 320; **0 of 188 text elements below WCAG AA**; keyboard focus ring, skip link, landmarks, reduced-motion respected. Detector: 55 findings to 8 static false positives (section padding supplied by an inner wrapper) plus 1 in the preserved wizard. |
| Landing: found and fixed on the way | **GitHub footer link had a space in its URL** (`.../Seed Reflections`); two public nav items used emoji; the public header linked to the Admin login. | Fixed URL (now `.../seedreflections`); emoji removed (wizard included); Admin link left in the footer only. |
| Landing: open | Privacy and Terms still link to `#` (no pages exist); "Open Source" in the footer is an unverified claim; wizard keeps its own card-in-console structure (preserved component). | **Needs the founder**: legal pages, and whether the repository is public. |
| **Dashboard crash with accepted decisions** | Found by the sample archive: the Workspace shelf threw a TypeError (`related_seeds` assumed on every decision) and rendered **empty** for any account that had accepted a single decision. | **Fixed** (tolerates the missing field). Ideas (5) / Threads (12) now render. |
| Dashboard Library sub-menu | The sub-menu was fixed at top:256px and drew over Tools, Prompt Engine and Settings. | **Fixed**: an accordion in the sidebar flow on desktop. No overlaps at 1440 / 768 / 390. |
| **Shared design system** | Three public pages each carried their own CSS (the old landing page alone had 56 KB of inline CSS). | **Shared stylesheet** `assets/site.css` (tokens, type, buttons, header, footer, ledgers, responsive rules) used by landing, sign-in and comparison, with one shared header and footer. Page-specific styles stay in each page. |
| **Sign-in page (auth.html): redesign** | Old page: dark card form, emoji tabs, placeholder name "William", "Platform Master Control" box. | **Replaced** in the same register language: quiet green side panel with the existing tagline and three truths drawn from existing copy; ledger-sheet form panel; ruled plan chooser; real tab semantics. All form IDs and script logic preserved. |
| Sign-in: **default admin password printed publicly** | The Admin tab told every visitor: "Enter your admin password from .env (default: changeme)". The error also said "Check .env file". | **Fixed**: copy removed; error is now just "Invalid admin password." |
| Sign-in: **open redirect** | The `next` parameter was used as the post-login destination with no validation. Tested on the original page: three of four attack links (`https://evil.example`, `//evil.example`, `/\evil.example`) sent a freshly signed-in user to an external site. | **Fixed**: only same-origin paths are accepted. All attack variants now land on the dashboard; a legitimate `next` still works. Verified before and after. |
| Sign-in: **wrong password rule** | Hint said "8+ chars, one uppercase, one number"; the server requires **12 characters** and nothing else. Users following the hint were rejected. | **Fixed**: hint corrected and enforced in the browser (`minlength=12`). |
| Sign-in: **false claim about password reset** | "We'll send a reset link", and on failure "a reset link has been sent". No reset endpoint or email sending exists anywhere (404 on both API versions). | **Fixed**: the page now says "Password reset by email isn't available yet" and tells the user to ask an administrator. **Needs the founder**: what the real recovery path should be. |
| Sign-in: **hosted sign-in cannot work** (NOT fixed) | `js/platform.js` hard-codes the legacy `/api/v1` API, which hosted mode deliberately blocks. Login and signup through this page return "Sign in is temporarily unavailable" on a hosted server. The hosted v2 auth works (tested earlier); this page never calls it. Predates this work. | **Open, release blocker for hosted.** It is an authentication change, so it is proposed, not made: in `platform.js`, detect the server mode from `/api/v2/capabilities` and, when hosted, call `/api/v2/auth/login` and `/api/v2/auth/signup`, reading `error` (not `detail`) from failures. |
| **Comparison page: redesign** | Stat strip, three icon cards, kicker labels ("Comparison 1 of 2"), six equal cards. | **Replaced.** All copy kept word for word (checked mechanically; only the stat strip, icon glyphs, label tags and old nav were dropped). The two comparison tables are real ledgers with the SeedReflections column set apart; on phones each row becomes a heading with labelled lines. All six documentation links preserved. |
| Comparison: found and fixed | The SeedReflections column fell to **1.3:1 contrast** (a shared-stylesheet rule outranked the column colour). Caught by measuring all 180 text elements. | **Fixed**: 0 of 180 below WCAG AA. |
| Verification (all three pages) | | 0 JS errors; no horizontal overflow from 320 to 1920px; 0 contrast failures; keyboard order verified; detector: index 55 to 8, auth 6 to 1, comparison 21 to 4 (the rest are static false positives about section padding). |
| **Impeccable commands run (Nov 11)** | Until now only the detector, the direction roll and the context files had been used. | **`critique`** on the landing page: **21/32 (66%, Acceptable)**, 1 P0 / 3 P1 / 1 P2; snapshot kept locally (the toolkit gitignores it). **`audit`** on the whole UI: **11/20 (Acceptable)**, 0 P0 / 3 P1 / 7 P2 / 4 P3; copy in `.impeccable/audit/`. **`document`**: `DESIGN.md` + `.impeccable/design.json`, every colour verified against the shipped CSS. **Degraded:** run in one context (sub-agents not requested), detector had run earlier; the engine (v0.1.22) has no `audit-storage` command, so the audit copy was saved by hand. |
| Still open from the critique and audit | The commands only found problems; none of their fixes has been applied yet. | Open: harden (keyboard-blocked wizard cards, sign-in plan picker, dashboard plan tiers; unlabeled admin and dashboard fields), optimize (dashboard weight), clarify (jargon, privacy line), layout (legible screenshots), extract (dashboard tokens), adapt (touch targets). |
