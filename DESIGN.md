---
name: SeedReflections public site
description: An accession register for your AI work. Deep-green ground, ledger-sheet records, one stamp ink.
colors:
  field: "#0c3626"
  field-deep: "#0a2f21"
  field-deepest: "#07251a"
  on-field: "#e9f3e5"
  on-field-muted: "#a8d6bb"
  ledger-sheet: "#dfead9"
  ledger-sheet-shade: "#d2e1cb"
  ink: "#10261c"
  ink-muted: "#3b5748"
  ledger-rule: "#a9c0a0"
  seed-green: "#3fb950"
  seed-green-hover: "#58cb69"
  seed-green-ink: "#06210f"
  stamp-vermilion: "#b8391f"
  highlighter: "#f2e08a"
typography:
  display:
    fontFamily: "Zilla Slab, Georgia, serif"
    fontSize: "clamp(2.7rem, 5.6vw, 4.7rem)"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.012em"
  headline:
    fontFamily: "Zilla Slab, Georgia, serif"
    fontSize: "clamp(1.95rem, 3.5vw, 3rem)"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.008em"
  title:
    fontFamily: "Zilla Slab, Georgia, serif"
    fontSize: "1.3rem"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "Hanken Grotesk, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.62
  label:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "0.78rem"
    fontWeight: 500
    letterSpacing: "0.07em"
rounded:
  sm: "3px"
  md: "4px"
  lg: "6px"
spacing:
  gutter: "clamp(20px, 4vw, 48px)"
  section: "clamp(72px, 9vw, 132px)"
  column-gap: "clamp(28px, 4vw, 64px)"
components:
  button-primary:
    backgroundColor: "{colors.seed-green}"
    textColor: "{colors.seed-green-ink}"
    rounded: "{rounded.md}"
    height: "48px"
    padding: "12px 22px"
  button-primary-hover:
    backgroundColor: "{colors.seed-green-hover}"
  button-line:
    backgroundColor: "transparent"
    textColor: "{colors.on-field}"
    rounded: "{rounded.md}"
    height: "48px"
  register-entry:
    backgroundColor: "{colors.ledger-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "22px"
  field-input:
    backgroundColor: "#f3f8ef"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "50px"
---

# Design System: SeedReflections public site

> **Scope.** This file documents the **landing, sign-in and comparison pages** and the shared stylesheet `assets/site.css`. It was written from the shipped pages, not from intentions. The dashboard (`consumer-dashboard.html`), admin and product pages are an **older, different system that does not yet follow it** (see the audit in `.impeccable/audit/`). The Creative North Star below was derived from the recorded direction contract and the built pages, not chosen in an interview; change it freely.

## Overview

**Creative North Star: "The Accession Register"**

Every recovered finding is entered in a register: where it came from, what was found, who found it, and whether a person has decided. The site is built as that record. A deep-green field is the desk; pale ledger sheets are the records; one vermilion stamp ink marks a human decision. Nothing is decorative that a register would not hold: rules, columns, labels, a stamp.

The page makes one argument, that **every finding stays tied to its source and you decide what becomes true**, and it shows that argument as an object (a source passage, the found phrase marked, three choices) before it explains it in words. Copy is plain and declarative; claims are limited to what the product does.

**Key Characteristics:**
- Drenched deep-green ground, the same hue family as the product's own sidebar.
- Ruled tables and definition lists carry structure; there are no icon cards.
- Hard edges (3–6px radius), 1–2px rules, flat surfaces. No gradients, no glow.
- One interaction moment: the stamp.
- Real product screenshots, labelled as a sample archive, instead of illustration.

## Colors

A restrained, committed palette: one hue family (green) in three depths plus one pale ledger tint, one action green, one stamp ink.

### Primary
- **Seed Green** (#3fb950): the action colour. Primary buttons, the seed mark, focus rings, the "gaps shown" and bullet squares. Text on it is **Seed Green Ink** (#06210f).
- **Seed Green Hover** (#58cb69): hover and focus ring on dark grounds.

### Secondary
- **Stamp Vermilion** (#b8391f): the stamp ink. It marks a decided state ("Accepted by you") and error text on sheets. Used sparingly, on pale grounds only.

### Neutral
- **Field** (#0c3626), **Field Deep** (#0a2f21), **Field Deepest** (#07251a): page grounds, alternating by section; the deepest is the footer and the prompt-tools band.
- **On Field** (#e9f3e5) and **On Field Muted** (#a8d6bb): text on the green grounds. Muted is tinted from the green, never grey; ≥7:1 on Field.
- **Ledger Sheet** (#dfead9) and **Ledger Sheet Shade** (#d2e1cb): the record sheets and shaded quotation blocks.
- **Ink** (#10261c) and **Ink Muted** (#3b5748): text on sheets (≥6:1).
- **Ledger Rule** (#a9c0a0): hairlines on sheets. **Highlighter** (#f2e08a): marks the found phrase in a source passage.

### Named Rules
**The One Stamp Rule.** Vermilion appears only as a stamp or an error. It never decorates, and it never labels a neutral state: an "Active" label is not vermilion. *(The landing page's "Active" artifact state currently breaks this; see the critique.)*
**The Tinted Neutral Rule.** There is no grey. Every neutral is a shade of the field green or the ledger sheet.

## Typography

**Display Font:** Zilla Slab (with Georgia). **Body Font:** Hanken Grotesk (with system-ui). **Label/Mono Font:** JetBrains Mono, used only for data, accession numbers, labels and stamps.

**Character:** A slab serif with a typewriter's firmness for headlines, against a plain, readable grotesk. The mono face is a measuring tool, never a costume.

### Hierarchy
- **Display** (700, clamp 2.7–4.7rem, 1.04): the page headline only. The second sentence drops to weight 400 in the muted tint; emphasis comes from weight, never colour.
- **Headline** (600, clamp 1.95–3rem, 1.1): section headings; balanced wrap.
- **Title** (600, 1.3rem, 1.25): row terms and plan names.
- **Body** (400, 17px, 1.62, ≤62ch): copy. Ledes are 1.18rem in the muted tint.
- **Label** (500, 0.78rem, +0.07em, uppercase): table headers, register field names, stamps.

### Named Rules
**The No Kicker Rule.** A heading carries its own weight. There are no small labels above headings.

## Layout

A 12-column grid (max 1240px, side gutter `clamp(20px, 4vw, 48px)`) with a `clamp(28px, 4vw, 64px)` column gap. Sections alternate grounds (field, field-deep, ledger sheet) to set rhythm; each has `clamp(72px, 9vw, 132px)` block padding. Long left-hand columns are sticky above 1081px. Breakpoints: 1080 (stack the hero and screenshot rows), 860 (collapse the 12-column grid to one column, because column gaps alone overflow narrow phones), 760 (header nav becomes a scrolling row; tables become labelled blocks), 480, 359. Verified: no horizontal overflow from 320 to 1920px.

## Elevation & Depth

Flat by default. Depth appears only on **objects** (the register entry, product screenshots), as a soft offset shadow, never as a halo.

### Shadow Vocabulary
- **Register object** (`box-shadow: 0 26px 48px -18px rgba(0,0,0,.6)`): the hero register entry on the green field.
- **Screenshot on field** (`0 28px 50px -20px rgba(0,0,0,.65)`) and **on sheet** (`0 24px 44px -22px rgba(16,38,28,.55)`).

### Named Rules
**The Flat Surface Rule.** Sections, tables and buttons carry no shadow. Zero-offset glows are never used.

## Shapes

Small, hard radii: 3px inputs, 4px buttons, 6px objects. Structure is drawn with 1px hairlines and a single 2px rule above each table or list. Stamps are square-cornered, bordered, and rotated −2° so they read as inked. The only fully rounded elements are radio dots.

## Components

### Buttons
- **Shape:** 4px radius, 48px high, 2px border.
- **Primary:** Seed Green fill, Seed Green Ink text, bold. Hover lightens to #58cb69; active moves 1px.
- **Line (secondary):** transparent with a 2px border in the ground's text colour; fills on hover. **Link-arrow:** bold text with a 2px underline and an arrow that nudges right on hover.

### Register entry (signature component)
A ledger-sheet object with an ink title bar ("Accession register / Example entry"), ruled field rows (label in mono, value in body), a quoted source passage on the shaded sheet with the found phrase in Highlighter, and a status cell holding the **stamp**. Three equal buttons (Accept, Defer, Dismiss) change the stamp, with a short scale-in animation. It reads as a record, never a form.

### Stamp
Mono, uppercase, +0.08em, 2px border, rotated −2°. Colour = meaning: ink-muted (pending, deferred), vermilion (accepted).

### Ledger tables and definition lists
A 2px rule on top, 1px rules between rows, mono column heads. The SeedReflections column in comparison tables is the one pale-sheet column. On phones each row becomes a heading with labelled lines. Definition lists use a 5/7 term-and-description split.

### Inputs / Fields
- **Style:** 2px ink stroke, #f3f8ef fill, 3px radius, 50px high, 16px text. **Focus:** 3px seed-green outline with 1px offset. **Error:** a bordered message in vermilion with `role="alert"`; success in dark green with `role="status"`.

### Navigation
Sticky header on the field: wordmark (seed mark + "Seed" in green), text links, "Sign in" and a primary "Start free". The current page has `aria-current` and a faint fill. Below 760px the links become a single horizontally scrolling row.

## Do's and Don'ts

### Do:
- **Do** show the mechanism as an object before explaining it.
- **Do** tint every neutral from the field green or the ledger sheet; keep text at ≥4.5:1 (it measures ≥6:1).
- **Do** use rules, columns and mono labels to build structure.
- **Do** label sample data as sample data, and report gaps ("5 could not be read") alongside successes.
- **Do** make every choice control a real button or radio input.

### Don't:
- **Don't** put a kicker or eyebrow above a heading.
- **Don't** use gradient text, glows, glass, or hard offset shadows.
- **Don't** use emoji or unicode glyphs as icons.
- **Don't** build equal icon-plus-heading-plus-text card grids, or put a card inside a card.
- **Don't** use a cream or parchment page ground; the ledger sheet is an object on the field, not the page.
- **Don't** invent testimonials, customer counts, benchmarks or integrations.
- **Don't** show anything as the product doing what it does not do (no implied access to a provider's private history).
