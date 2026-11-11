# Audit: whole UI, isolated sub-agent run 2 (after contrast, focus, field border, dialog, wizard-move, landing and a11y P2 fixes)

Isolated sub-agent, no earlier results visible. 7 pages (index, prompts, auth, comparison, product, admin, dashboard), dashboard tabs and 9 dialogs exercised with the keyboard, 1440 and 390 wide, overflow also at 320/768, reduced-motion emulated. Dataset: 12 conversations / 23 candidates, so Review-tab DOM size is understated. Hosted mode, error and empty states not tested. Saved by hand (no `audit-storage` in engine v0.1.22).

## Audit Health Score: 13/20 (Acceptable). Previous isolated run: 11/20
| # | Dimension | Score | Key finding |
|---|---|---|---|
| 1 | Accessibility | 3 (was 2) | 0 contrast failures except one 3.24:1 label (wizard step 2); dialogs exemplary; toast not a live region; auth tabs/radios not keyboard-complete; dashboard has no main/skip link |
| 2 | Performance | 3 (was 2) | Fast at rest; dashboard 345 KB doc (about 75 KB gzipped), 184 KB inline JS, about 1,900 nodes; fonts via CSS @import; 752 KB unreferenced asset |
| 3 | Theming | 2 | Dashboard 461 literal colours vs 699 var(), 6 :root blocks, 115 !important; admin and product separate token systems |
| 4 | Responsive | 3 | 0 overflow at all widths; a few controls under 44px; px-only type in the apps; no Sign Out at 390 |
| 5 | Implementation integrity | 2 | Public pages PASS; dashboard is nine stacked override layers; inert controls styled as tabs |

## Issues: P0 0, P1 4, P2 11, P3 5
- [P1] `#toast` has no live region (119 call sites silent to assistive tech). WCAG 4.1.3. -> harden
- [P1] No Sign Out control at phone widths: hidden by `@media(max-width:720px)` rule at consumer-dashboard.html:1097; More menu and Settings have none (tested in local mode). -> adapt
- [P1] Dashboard stylesheet is an unmanaged patch stack (196 selectors declared more than once, 6 :root, --accent redefined 5x). -> document, polish
- [P1] Wizard step 2 `.len-sub` (opacity .7) 3.24:1, prompts.html:66. WCAG 1.4.3. -> polish
- [P2] Auth tabs unreachable by keyboard (tabindex -1, no arrow handler); a11y.js radios are all Tab stops with no arrow behaviour. -> harden
- [P2] Dashboard has no main/header landmarks and no skip link; 46 Tab stops on Workspace. -> harden
- [P2] Four inert spans styled as tabs in the Prompt Engine tab (cursor:pointer, no role/handler). -> distill
- [P2] Heading levels: wizard h1 to h3, dashboard Prompt tab h2 to h4, footer column titles are h2 on every public page, review headings are user text with aria-level override. -> harden
- [P2] Undersized targets: `#wfocus-stuck` 14x14 (the only SC 2.5.8 failure after spacing), wizard buttons 21-29px, footer links 22px, admin checkbox 13px. -> adapt
- [P2] One unnamed select (Settings team row); Sign Out title-only; password field name polluted by the Forgot? link. -> harden
- [P2] Dead CSS ships (.telemetry-strip, body::before, copied reduced-motion block referencing undefined --accent). -> optimize
- [P2] Third-party font loading on every page; @import chain in dashboard. -> optimize
- [P2] App type is px-only (dashboard 330 px declarations, 0 rem). -> typeset
- [P2] Inline-style sprawl (dashboard 342, admin 75, index 29, prompts 27). -> polish
- [P2] Admin tab exposed on the public sign-in card. -> clarify
- [P3] site.css global motion kill; transition:all (dashboard 13, prompts 5); static spinner under reduced motion; selected plan row flush to edge; unreferenced assets/proof_of_creation.png; body overflow-x hidden.

## Verified passes
Dialogs (8 dashboard + admin) at 1440 and 390: role, name, inert background, focus in and trapped, Escape closes, focus returns. 0 overflow, 0 console errors, no keyboard traps, visible focus on every stop, aria-current on dashboard nav, one h1 per page.

## Detector
384 findings with DESIGN.md, 39 without. Mostly drift for pages DESIGN.md scopes out. cramped-padding mostly false positives (full-bleed sections; `.plan-opt` hit is real). low-contrast x4 on the dashboard are dead CSS on a display:none strip.
