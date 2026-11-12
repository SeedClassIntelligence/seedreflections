# Audit: whole UI after restoring the original front page and aligning the rest (fdf9f84)

Isolated sub-agent, no earlier results visible. 7 pages (index, prompts, auth, comparison, admin, dashboard, product), every dashboard tab, 8 dashboard dialogs plus admin dialog exercised by keyboard, all 4 wizard types x 4 steps, 1440 and 390 wide (overflow also 320/768), reduced motion emulated. Dataset: 12 conversations / 23 candidates; product page database empty, so its list states were measured on injected demo markup using its own classes. Not comparable with earlier audits (different design). Saved by hand (no `audit-storage` in engine v0.1.22).

## Audit Health Score: 13/20 (Acceptable)
| # | Dimension | Score | Key finding |
|---|---|---|---|
| 1 | Accessibility | 3 | App surfaces strong (dialogs, 0 contrast failures on 10 tabs); public pages have contrast failures, no reduced-motion, unannounced sign-in errors |
| 2 | Performance | 3 | Dashboard 347 KB with about 271 KB inline; unused 25 KB serif font; 1.56 MB unreferenced images; large-archive behaviour not measured |
| 3 | Theming | 2 | Palette matches DESIGN.md everywhere; 7 pages use 7 token vocabularies; dashboard is ten stacked layers (114 !important, 6 :root) |
| 4 | Responsive | 3 | 0 overflow at 320/390/768/1440 on every page and state; header and footer targets 21-27px; sub-nav clips Admin with no hint |
| 5 | Implementation integrity | 2 | Conditional pass: one palette, one font, shared header; wizard buttons use classes that do not exist; hover colour differs per page |

## Issues: P0 0, P1 3, P2 8, P3 5
- [P1] Prompt Engine wizard buttons are unstyled: `btn-primary`, `btn-ghost`, `btn-sm` are not defined on that page, so Next/Back/Copy render as grey browser buttons (prompts.html:739, 757, 758). -> polish
- [P1] Contrast under 4.5:1 on public pages: index platform strip `.platform-item` (opacity .7) 2.34:1 on 7 labels; prompts wizard step 2 `.len-sub` 8px captions at 3.66:1. WCAG 1.4.3. -> colorize, typeset
- [P1] Sign-in and sign-up error and success messages have no live region; auth has no heading and no <main>. WCAG 4.1.3, 1.3.1, 2.4.1. -> harden
- [P2] Index animations ignore prefers-reduced-motion (4 infinite). -> animate
- [P2] Dashboard stylesheet is ten stacked layers; dead telemetry strip; unused Fraunces font. -> distill
- [P2] No shared tokens or components; hover colour differs (auth blue #79b8ff, admin teal, dashboard #4ade80, others none). -> document, polish
- [P2] Dead controls: Privacy/Terms href="#"; four inert chips in the dashboard Prompt tab; unused avatar affordance. -> clarify
- [P2] Heading and landmark gaps: no <main> on index/auth, no <h1> on prompts/auth, admin and dashboard Prompt tab heading skips. -> harden
- [P2] Public sub-nav scrolls sideways and clips Admin on phones. -> adapt
- [P2] Review and Library lists unpaginated on the client (extrapolated 2,750 nodes at the 250-card server default; not measured). -> optimize
- [P2] Auth hover state turns blue. -> polish
- [P3] Touch targets, no color-scheme: dark, 8-10px captions, transition:all (48), pasted duplicate CSS, unreferenced assets, thin auth focus ring.

## Verified passes
All 8 dashboard dialogs and the admin dialog trap focus, close on Escape and return focus; 0 contrast failures on all 10 dashboard tabs, admin, auth, comparison and product demo states; 0 overflow; roving-tabindex radios respond to arrows; 0 unnamed controls; console clean.
