# SeedReflections: CTO handoff directive

- **Owner:** Seed-Class Intelligence
- **Canonical repository:** https://github.com/SeedClassIntelligence/seedreflections
- **Working branch:** `main`
- **Baseline commit:** `706e9793082b804830b5a43136958b2ceab5d6f6` (November 10, 2026)
**Status:** Engineering handoff and independent review request. A push and passing tests are not a production release approval.

## Your mandate

Lead the technical and product-design assessment of SeedReflections as one coherent platform. Preserve the founder's mission, verify the actual consumer journey against the implemented system, finish the functional and visual integration, and give the founder an evidence-based release recommendation. Work in the canonical repository on `main`; do not create a competing product or quietly replace the existing architecture. Propose any material change to protected architecture, production data, payment flows, authentication, or access control for founder review before execution.

The founder's central problem is concrete: after years of AI use, people receive large JSON exports, documents, PDFs, and copied threads that are difficult to read or revisit. They need to recover what they thought, find ideas and decisions, verify where each finding came from, and continue the work. The product must support complete imports at scale and many source platforms. It must not imply that an LLM API key gives unrestricted access to a provider's private conversation history.

## Product objective and intended journey

The current product definition is [PRODUCT_CAPABILITIES_AND_TIERS.md](PRODUCT_CAPABILITIES_AND_TIERS.md). Use it as the product and public-claims baseline, then verify its assertions against code and a running deployment.

1. The user enters **Workspace** first. Source intake and ongoing work live there.
2. They upload an AI export (JSON is the primary path), another supported document, or pasted text; authorize a local source through SeedBridge; or receive data from a scoped integration.
3. The system ingests the entire eligible source, normalizes conversations and documents into one archive, and records source/platform, message, import, hash, and coverage evidence. It reports unreadable and unprocessed material rather than hiding gaps.
4. **Library** lets the user read, search, filter, and open conversations, sources, ideas, decisions, and work artifacts.
5. **Review** presents candidate ideas, decisions, tasks, and other findings with source evidence. The user accepts, defers, or rejects them; machine suggestions do not silently become accepted truth.
6. The user opens an item into Workspace and continues through conversation, a brief, plan, report, task set, or note. Evidence and lineage remain accessible in context. Model selection can be automatic by task or explicit where configured; model credentials alone do not grant external tools or source access.
7. **Overview** reports meaningful archive and work status, including dynamic source/platform coverage, processing gaps, review progress, and operational state. Avoid duplicate or invented metrics.
8. Settings, tools, team, billing, backup, and admin functions govern the platform without fragmenting the core journey.

## What we were using

The following is the documented implementation map, supported by a targeted repository inspection. Treat each capability as a verification target rather than an independently certified production feature.

- **Runtime:** Python `server.py` serves the application and REST API. SQLite is the authoritative local store; `archive_store.py`, `tenant_archive_store.py`, and related stores handle archive, workspace, and hosted boundaries. The older `project-handoff/ARCHITECTURE.md` still says `seeds.json` is the database and is stale.
- **Consumer UI:** `consumer-dashboard.html`, with `index.html` as the public landing page and `admin-dashboard.html` for administration. Current navigation includes Workspace, Review, Library, Overview, Tools, Prompt Engine, and Settings. A local `workroom-prototype.html` was intentionally not committed because it is an alternate design reference, not the canonical dashboard.
- **Intake:** uploaded exports/documents and paste; normalized archive ingestion; SeedBridge (`seedbridge_client.py`) for explicitly selected local JSON/JSONL sources; scoped, revocable integration delivery through `/api/v2/integrations/import`. Vendor-specific private cloud chat access requires an actual authorized adapter or vendor capability. No universal direct connector has been established.
- **AI:** task-aware model routing with local/open-model support and optional configured provider credentials. Review task routing and tool authorization separately from source ingestion.
- **Deployment:** local runtime and hosted configuration in one codebase. `Dockerfile`, `docker-compose.prod.yml`, `.env.example`, `DEPLOYMENT.md`, `/api/v2/health`, `/api/v2/readiness`, and `release_check.py` define the deployment path. Billing and team features are configuration-dependent; implementation in source is not evidence they are active in production.
- **Design direction:** the founder wants a modern, professional, distinctive product. The public home page set the original messaging and brand baseline. The dashboard uses green navigation and a dark work area, but the founder has repeatedly rejected superficial recolors, disconnected pages, generic AI-dashboard patterns, and popup-heavy retrofits. The founder selected the open-source [Impeccable project](https://github.com/pbakaus/impeccable) as the design workflow to use for this redesign. It is an agent design toolkit, not SeedReflections' application runtime.

## Required use of Impeccable

Use the founder-selected open-source **Impeccable** toolkit during the next design and implementation pass, not merely as inspiration. Its upstream repository describes project setup, product/design context files, targeted critique and audit commands, responsive and error-state checks, and a deterministic design-pattern detector. Follow its current installation instructions for the CTO's coding environment and record the version or commit used. The upstream Codex path currently starts with `npx impeccable install`, then `$impeccable init`; confirm the installed version's instructions before running them.

Apply it to the **existing SeedReflections interface**, beginning with the real Workspace, Review, Library, Overview, Tools, Prompt Engine, Settings, and Admin flows. Establish product context from `PRODUCT_CAPABILITIES_AND_TIERS.md` and the founder's direction; document the current visual system; run targeted `critique` and `audit` reviews; use `shape`, `layout`, `typeset`, `adapt`, `clarify`, `harden`, and `polish` where their findings call for them; and run the detector against source and rendered pages. Keep a before/after finding log and verify changes in the running product. Treat toolkit findings as inputs to judgment, not automatic authority over product messaging, workflows, or architecture.

**Current integration status:** the repository contains a CSS comment describing an “Impeccable guided legibility and navigation pass,” but this handoff did not find an installed Impeccable project skill, context files, detector configuration, or saved audit report in the canonical repo. Do not report that its full workflow was run previously. Set it up, apply it, and include its findings and fixes in the review evidence.

## Verified at this handoff

- The listed baseline commit was pushed to `origin/main` at the repository above; local `main` tracked `origin/main` immediately afterward.
- `python -m unittest discover -s tests` completed with **137 tests passing** on the local Windows environment. This covered code-level and included browser workflows; it does not prove a production deployment, complete source coverage, usability, or security certification.
- The latest staged change passed `git diff --cached --check`, and a targeted staged secret-pattern check found no matching newly added credentials. This is not a full historical secret audit. Previously exposed credentials, if any, still require rotation.
- The untracked local `workroom-prototype.html` was excluded from the push. It must not be treated as a second production UI without an explicit disposition decision.

### Evidence correction: do not equate implementation with consumer capability

The 137-test run does **not** establish that a person can complete the full journey on a real export. The principal dashboard browser workflow in `tests/test_browser_automation.py` checks that navigation and several controls appear; it does not perform a complete import, review, continuation, and return visit. `tests/test_product_v2.py` exercises an API path with a small synthetic conversation. `tests/acceptance_year_scale.py` defines a separate 2,500-conversation synthetic acceptance run, but that script was **not** included in the 137-test `unittest discover` result. The existence of routes, UI labels, and product documentation establishes implementation intent, not live usability, whole-document processing, universal cloud access, or production activation. Independently verify those claims before representing them as available to consumers.

## Required CTO review and completion work

1. **Trace one real end-to-end journey:** import a representative large export and mixed documents; verify counts, processing coverage, readable conversations, review decisions, opening an idea in Workspace, persistent artifacts, evidence links, export, backup, and restore. Record what is proven and what fails.
2. **Audit the interface as a system:** run every dashboard route and control, including Review, Library, Overview, Tools, Prompt Engine, Settings, and Admin. Verify responsive widths, collapsible side panels, full usable workspace width, empty/loading/error states, keyboard access, and consistent components. Remove dead controls and modal-only detours where they obscure the flow.
3. **Make Overview truthful:** derive platform/source coverage from the actual archive, not a fixed list of providers. Define each displayed metric, denominator, and action. Show unsupported, unknown, skipped, and failed material explicitly.
4. **Keep one product language:** reconcile landing, comparison, pricing, onboarding, dashboard, and any animation with the actual capability and entitlement rules. Preserve the founder's core message while correcting overclaims. Update or clearly mark the older handoff documents that conflict with the current architecture.
5. **Audit integration boundaries:** distinguish import/export, local synchronization, integration delivery, and true provider-authorized cloud connectors. Document each provider's supported method and test it. Do not label a connection as live when it only accepts a manually supplied API token or payload.
6. **Review security and operations before release:** authentication, tenant isolation, credential storage, token scopes/revocation, file and PDF handling, resource limits, logging, backups, restore, TLS, readiness, billing webhook handling, and team permissions. Use controlled test data; protect live data and payment/auth boundaries.
7. **Decide release status with evidence:** run the release gate against the intended public HTTPS origin, exercise a backup/restore drill, verify live configuration for any offered paid/team feature, and perform an independent product usability review. Give the founder a concise go/no-go list with severity, owner, proof, and next action.

## Acceptance standard

The platform is ready only when a new user can bring a large real export into Workspace, understand what was processed, find and inspect their original conversations, review evidence-backed ideas, continue one idea into persistent work, and return later without losing context. Navigation must be coherent and the dashboard must visibly represent the breadth of the product. Public claims and tier promises must match active, tested behavior. The founder, not the implementation or a passing test count, makes the final release decision after the CTO presents evidence.

## Sources to read first

1. `PRODUCT_CAPABILITIES_AND_TIERS.md` — current product definition and claims rules.
2. `README.md` and `DEPLOYMENT.md` — runtime and deployment boundary.
3. `consumer-dashboard.html`, `server.py`, archive/workspace/auth stores, and `seedbridge_client.py` — actual implementation.
4. `tests/` and `release_check.py` — automated evidence and release gate.
5. `project-handoff/` — historical specifications and intent; verify each against current implementation. In particular, `ARCHITECTURE.md`, `CURRENT_IMPLEMENTATION.md`, and `DESIGN_SYSTEM.md` contain older descriptions and must not override current product truth.

Report findings as **verified fact, test evidence, inference, unresolved issue, architecture conflict, or founder decision needed**. Do not claim a capability is complete solely because a route, UI label, or test exists.
