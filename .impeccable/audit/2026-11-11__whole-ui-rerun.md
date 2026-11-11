# Audit re-run: whole UI (after the hosted-login, harden, and screenshot fixes)

Saved by hand (engine v0.1.22 has no `audit-storage`). Same method as the first audit: detector, then a Playwright probe of 16 page states at 1440 and 390, plus contrast, overflow and keyboard tests. Dataset: the 12-conversation sample archive, so the Review-tab DOM count is NOT comparable with the first run (dataset not recorded). The 333 KB document and source counts are data-independent.

## Audit Health Score: 12/20 (Acceptable). Previous: 11/20
| # | Dimension | Score | Key finding |
|---|---|---|---|
| 1 | Accessibility | 3 (was 2) | Click-only controls 17 -> 0; unnamed fields 52 -> 1; contrast failures remain (12); 4 dashboard fields show no outline/shadow focus (border change unverified) |
| 2 | Performance | 2 | Unchanged: dashboard document 333 KB, 1,899 nodes on the sample archive, no work done here |
| 3 | Theming | 2 | Unchanged: dashboard 564 literal colours (same method on the pre-fix file: 564), 106 !important, 342 inline styles, no reduced-motion |
| 4 | Responsive | 3 | 0 overflow in 60 checks (5 pages + 10 dashboard tabs x 4 widths: 320, 390, 768, 1440); touch targets still small (dashboard 8-83 per tab under 44px) |
| 5 | Implementation integrity | 2 | Public pages pass; with DESIGN.md loaded the detector reports drift: dashboard 213, product 47, admin 31, landing wizard 32 |

## Implementation integrity verdict
PASS for sign-in, comparison and the landing page above the wizard (one token system). FAIL for dashboard and admin (layered patches, `.library-subnav` defined 11x, `--amber` three values), and the landing prompt wizard sits outside the design system.

## Issues: P0 0, P1 2, P2 5, P3 3
- [P1] 12 text elements fail WCAG AA contrast: Workspace idea-status "active" 3.8:1 (every idea card), admin `.stat-sub` 4.12:1 (x5), Overview lifecycle icons 3.4/4.2:1. 1.4.3. -> polish
- [P1] Dashboard weight: 333 KB uncached document, 179 KB inline script. -> optimize
- [P2] Dashboard theming drift (564 literal colours, 106 !important, conflicting --amber, 342 inline styles). -> extract
- [P2] No prefers-reduced-motion handling in dashboard, admin or product. -> harden
- [P2] Touch targets: admin 39 controls under 44px (13px checkbox), dashboard checkboxes 13-18px, selects 19px high, Overview link-buttons 21px. 2.5.8. -> adapt
- [P2] Focus indicator not detected (outline/shadow) on `#project-filter`, `#shelf-search`, `#shelf-status-filter`; may be a border-colour change, unverified. 2.4.7. -> harden
- [P2] Heading skips on dashboard Library and Intake (detector, 2). -> harden
- [P3] `transition: all` in dashboard and landing; Google Fonts (3 families) sends visitor IPs to Google; public Admin link.

## Resolved since the first audit
Click-only controls (17 -> 0) and unnamed fields (52 -> 1; one remains in the dashboard Account tab, `acc-email` style fields count as labelled by their `<label>` and are probe false positives); hosted sign-in; legible screenshots.

## Recommended actions
1. [P1] polish: contrast on idea-status text, admin stat-sub, Overview icons
2. [P1] optimize: dashboard document weight and Review queue size
3. [P2] extract: collapse dashboard tokens and --amber
4. [P2] adapt: touch targets and checkboxes
5. [P2] harden: reduced-motion, focus rings on the 3 inputs, heading order
