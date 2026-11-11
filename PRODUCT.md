# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary:** a heavy AI user with years of scattered history: large JSON exports, documents, PDFs and copied threads across several AI platforms. They can no longer find what they thought or decided, cannot tell where a conclusion came from, and want to keep working rather than start over.

Also served, in this order: independent builders and founders who use AI as a thinking partner on projects; later, teams managing AI-assisted work in a shared, governed workspace.

*(Confirmed by the founder, Nov 11 2026: primary-user and positioning options were accepted as proposed.)*

## Product Purpose

Bring scattered AI work into one governed workspace, find the ideas and decisions buried in it, verify each against its original source, and **continue the work inside the platform**: investigate, ideate, plan, write, revise, build and manage work using preserved project memory.

Success is a person who imports a large real export, understands exactly what was and was not processed, finds and inspects their original conversations, reviews evidence-backed findings, advances one idea into substantial persistent work, and returns later without losing context.

## Positioning

Cross-provider, **evidence-first** recovery that becomes a **project-centered work surface**. One archive across many AI platforms in which every finding links to its original source, nothing becomes accepted truth without a human decision, and work continues from that preserved context. A single AI vendor's own project feature cannot truthfully hold another vendor's history or show the user the gaps in it.

The Workspace is an **operating surface**, not a generic AI playground: durable project memory, source selection, working conversations, artifacts, decisions, tasks and authorized tools in context.

## Operating Context

- Entry is **Workspace**; source intake and ongoing work live there. Surrounding areas: Review, Library, Overview, Tools, Prompt Engine, Settings, Admin.
- Intake paths: uploaded exports and documents, pasted text, SeedBridge (user-authorized local sources), scoped integration delivery. No path implies access to a provider's private cloud history.
- Runs locally (private use, SQLite) or hosted (authenticated tenants, optional billing and teams).

## Capabilities and Constraints

**AI model: confirmed direction.** By default, users work on **SeedReflections' own AI service running underneath the product**; they do not need to bring anything. As an **optional addition**, a user may supply their own model API key, and may **bring their own coding assistant or agent** into the platform. A model key supplies inference only. It never implies access to a provider's private history, and it never implies tools, browsing, coding or file access: those exist only where SeedReflections has built, permissioned and made them user-visible.

**Status of that direction (verified against code, Nov 11 2026):**
- Built: task-aware model routing over a catalog (local open models via Ollama; configured providers); bring-your-own key with OS-backed or session-only storage.
- **Not built / unverified:** a managed inference service that SeedReflections operates for all users (the code has only a default settings label `managed`); bring-your-own-agent/coding-assistant integration; tool adapters (the Gmail / Drive / Calendar connect route returns `authorization_handoff_unavailable`); a source-grounded persistent working conversation (current Workspace chat sees at most 40,000 characters of one transcript, and the v2 chat route returns a fixed summary).

**Durable constraints (confirmed):**
- Human review is mandatory. Machine findings are suggestions; accepting, editing, deferring or dismissing is always the user's act.
- Gaps are shown, never hidden: unreadable, skipped, unsupported and failed material is surfaced explicitly.
- No implied provider access: a key or connector never implies access it does not have.
- Project-centered work surface, not a chat playground.
- Finding detection today is **transparent phrase rules**, labelled as such. Model-assisted discovery and cross-conversation synthesis come later, separately verified, with human review still mandatory.
- Local mode is the "Local" plan (existing Pro-level core limits), not a paid Pro subscription. Hosted signup is Free until a paid entitlement is confirmed.

**Open decisions (not yet made):**
- Who hosts the managed AI inference, with what cost, budget and abuse controls, and which models.
- How a user's own agent connects: the permission model, execution state, and how its output becomes a traceable project source or artifact.
- Review work-inbox shape was decided in principle (filters by project/source/type, detail with surrounding context, Accept / Edit and Accept / Defer / Dismiss, relationship suggestions kept separate, review history); detailed design is open.

## Brand Commitments

Name: SeedReflections (Seed-Class Intelligence). The public home page set the original messaging and brand baseline. The founder wants a modern, professional, distinctive product and has repeatedly rejected superficial recolors, disconnected pages, generic AI-dashboard patterns and popup-heavy retrofits.

## Evidence on Hand

- `PRODUCT_CAPABILITIES_AND_TIERS.md` (product and claims baseline), `CTO_REVIEW_FINDINGS.md` (verified findings), `README.md`, `DEPLOYMENT.md`.
- A real, running consumer dashboard (`consumer-dashboard.html`) and landing page (`index.html`).
- **Absent, and must not be fabricated:** customer testimonials, usage numbers, benchmarks, paid-customer counts, provider partnerships, security certifications.

## Product Principles

1. **Evidence before assertion.** Every finding shows where it came from; the interface never presents a machine suggestion as fact.
2. **Show the gaps.** What was not processed matters as much as what was.
3. **The user's own context is the asset.** Work continues from preserved project memory rather than restarting elsewhere.
4. **Capability is claimed only when built.** Models, tools and connectors are named for what they actually do.
5. **Own AI by default, open by choice.** The service works out of the box; bringing a key or an agent is a deliberate, protected option.

## Accessibility & Inclusion

No product-specific standard has been confirmed yet. Baseline until decided: WCAG 2.2 AA contrast and target size, full keyboard access, readable text sizes. The detector currently reports 11px body text, sub-11px functional text and a 1.4:1 contrast failure; these count against this baseline.
