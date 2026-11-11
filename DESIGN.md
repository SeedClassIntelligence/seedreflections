---
name: SeedReflections
description: A dark, GitHub-style console for AI work. Near-black ground, Inter throughout, one green for the action that matters.
colors:
  ground: "#06080f"
  card: "#0d1117"
  surface: "#161b22"
  raised: "#1c2128"
  border: "#21262d"
  border-strong: "#30363d"
  text: "#f0f6fc"
  text-secondary: "#c9d1d9"
  text-muted: "#8b949e"
  text-dim: "#7d8590"
  primary: "#3fb950"
  primary-hover: "#4ade80"
  link-blue: "#58a6ff"
  cyan: "#39d0d8"
  teal: "#2dd4bf"
  amber: "#d29922"
  danger: "#f85149"
  danger-fill: "#da3633"
  purple: "#bc8cff"
typography:
  display:
    fontFamily: "Inter, sans-serif"
    fontSize: "76px"
    fontWeight: 900
    lineHeight: 1.08
    letterSpacing: "-2.5px"
  headline:
    fontFamily: "Inter, sans-serif"
    fontSize: "46px"
    fontWeight: 900
    lineHeight: 1.12
    letterSpacing: "-1.5px"
  title:
    fontFamily: "Inter, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.4
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  lede:
    fontFamily: "Inter, sans-serif"
    fontSize: "20px"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "Inter, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "1.65px"
  button:
    fontFamily: "Inter, sans-serif"
    fontSize: "15px"
    fontWeight: 700
  mono:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "12px"
    fontWeight: 400
rounded:
  sm: "4px"
  md: "6px"
  lg: "9px"
  xl: "12px"
  card: "16px"
  pill: "20px"
spacing:
  button-y: "13px"
  button-x: "24px"
  card-sm: "24px"
  card-lg: "36px"
  section-y: "64px"
  section-x: "72px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#000000"
    rounded: "{rounded.lg}"
    padding: "13px 24px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.cyan}"
    rounded: "{rounded.lg}"
    padding: "13px 24px"
  button-nav-signup:
    backgroundColor: "{colors.primary}"
    textColor: "#000000"
    rounded: "{rounded.md}"
    padding: "6px 14px"
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    padding: "36px 28px"
  eyebrow-pill:
    backgroundColor: "rgba(63,185,80,.1)"
    textColor: "{colors.primary}"
    rounded: "{rounded.pill}"
    padding: "5px 14px"
---

# Design System: SeedReflections

Derived on 2026-11-11 from the shipped front page (`index.html`), then applied to sign-in, comparison, the Prompt Engine, the dashboard, admin and the local product page. Values were measured from rendered output, not copied from intent. The creative language below is derived from what is shipped and from `PRODUCT.md`; the founder has not yet confirmed the wording.

## Overview

**Creative North Star: "The Dark Console."** A GitHub-dark workbench: a near-black page, slightly lighter cards, thin borders, and a single green that says "do this." Headlines are heavy and tight (Inter 900), with the second half of the hero line in a green-to-teal gradient. The product feels like a tool for people who live in terminals and notebooks, not a marketing brochure.

What it commits to (from `PRODUCT.md`):
- Claims match what is built. No invented logos, counts or testimonials.
- Evidence comes before assertion: the interface shows the source, then asks you to decide.
- It is consistent. The dashboard, admin, sign-in, comparison and Prompt Engine use the same palette, the same type and the same green.

## Colors

Tonal layering, not shadows, separates surfaces: ground `#06080f` → card `#0d1117` → surface `#161b22` → raised `#1c2128`, with `#21262d` / `#30363d` for borders.

- **Action Green `#3fb950`** (primary, hover `#4ade80`). The primary button, the nav "Sign Up", the logo's "Seed", eyebrows, selected states. **Text on it is black.** White on this green is about 2.3:1 and fails.
- **Link Blue `#58a6ff`.** Inline links only.
- **Cyan `#39d0d8`.** The current nav item and the secondary outline button. Teal `#2dd4bf` appears only in the hero gradient.
- **Amber `#d29922`, Danger `#f85149`** (filled danger buttons use `#da3633` with white text), **Purple `#bc8cff`.** Status and category accents, never decoration.
- **Text:** `#f0f6fc` primary, `#c9d1d9` secondary, `#8b949e` muted, `#7d8590` for the dimmest text that must still pass contrast (about 4.9:1 on `#0d1117`).

Rule, The One Green Rule: green marks the single action or the selected state. If a screen has three green things, two of them should not be.

## Typography

Inter everywhere (weights 300–900), JetBrains Mono for code, prompts and numbers in tables.

- **Display** 76px / 900 / -2.5px, hero only, centred, max 900px wide.
- **Headline** 46px / 900 / -1.5px, section titles.
- **Body** 16px / 1.6. **Lede** 20px / 1.65 in `#c9d1d9`.
- **Label** 11px / 700 / uppercase with wide tracking, in green, above section titles.
- **Buttons** 15px / 700. **Nav** 12–13px / 600.

The app (dashboard, admin) uses the same family at smaller sizes: page titles Inter 800 at 24–36px with -0.03em, body 13–14px.

## Layout

Marketing pages: sections centred in a 900px column with 5% side gutters, 64px top and 80px bottom padding. A two-row sticky header: logo and Sign In / Sign Up on top (50px), five links below (38px), identical on every public page.

App pages: a fixed left rail (224px; icons only at ≤900px; a bottom bar with a "More" menu at ≤720px) and a content area on the same dark ground.

## Elevation & Depth

Flat. Cards are `#0d1117` with a 1px `#21262d` border and no shadow. The only depth is a soft green radial glow behind the hero (`rgba(63,185,80,.07)` at the top) and a large dark shadow under the Prompt Engine console card (`0 16px 48px rgba(0,0,0,.4)`).

## Shapes

Buttons 9px; small buttons and inputs 6px; nav chips 4px; testimonial-style cards 12px; pricing and console cards 16px; eyebrow pills fully rounded (20px). Borders are 1px; selected cards use 1.5px in green.

## Components

- **Primary button.** Green fill, black text, 700 weight, 13px 24px, hover brightens to `#4ade80`.
- **Outline button.** Transparent, cyan 1px border and text; hover to green.
- **Nav sign-up.** Green fill, black text, 6px radius, 13px.
- **Card.** `#0d1117`, 1px border, 16px radius, 36px 28px padding.
- **Eyebrow pill.** Green text on `rgba(63,185,80,.1)` with a 1px green border at 30%.
- **Fields.** `#161b22` fill, border `#6e7681` or stronger (at least 3:1 against the card), focus ring in green.

## Do's and Don'ts

Do
- Put black text on green. Use `#7d8590` or lighter for dim text.
- Keep one green action per view; use the outline style for the second.
- Use the same header, the same five nav items and the same footer on every public page.
- Keep claims to what is built (see `PRODUCT.md`).

Don't
- Don't recolour a page to its own palette (green-black, cream, light). The dashboard and the local product page were each doing this; both are now on this system.
- Don't use a serif for headings, and don't use a blue primary button (sign-in used one; it is green now).
- Don't use white text on `#3fb950`, or `#6e7681` and darker for text on `#0d1117`.
- Don't use the plant icon (🌱) in navigation or UI chrome. (It stays inside generated prompt text, which is product output.)

## Known gaps

- The Prompt Engine page keeps the original 8–12px captions inside the wizard.
- The dashboard stylesheet is still several stacked layers (about 106 `!important`); the palette is unified, the CSS is not.
- Privacy and Terms are not written yet; their links go nowhere.
