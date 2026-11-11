# SeedReflections Product Capabilities, Workflows, and Tiers

**Status:** Authoritative product source of truth  
**Last verified:** November 5, 2026  
**Audience:** Product, design, engineering, marketing, sales, support, and release operations

This document defines what SeedReflections is, what it currently does, how a consumer uses it, what each subscription tier actually controls, and which capabilities require deployment configuration. Public website copy, pricing, onboarding, sales material, and support documentation should be checked against this file before publication.

## 1. Product definition

SeedReflections is an AI-work recovery, organization, and continuation platform. It turns exported or user-authorized AI conversations and supporting documents into a readable, searchable archive; flags explicit idea and decision language for human review; preserves source lineage; and gives the user a workspace to continue the work as plans, briefs, reports, task sets, and notes. Current candidate detection uses phrase rules; model-assisted discovery and synthesis remain to be proven separately.

The customer promise is:

> Bring your scattered AI work into one governed workspace, find the ideas and decisions buried inside it, verify them against the original source, and continue the work without starting over.

SeedReflections is not an AI provider and does not claim unrestricted access to private cloud chat histories. It accepts data through exports, uploads, pasted content, selected local sources, and authorized integration deliveries.

## 2. Consumer journey

1. **Enter the Workspace.** The Workspace is the operating center and first destination.
2. **Add or connect sources.** Upload an export or document, paste content, authorize a SeedBridge folder, or create a scoped integration connection.
3. **Normalize the material.** Different source formats enter one archive model while retaining platform, conversation, message, file, and import provenance.
4. **Review the archive.** Browse and search readable conversations and source material in the Library.
5. **Analyze with evidence.** The platform identifies candidate ideas, decisions, tasks, constraints, and recovery opportunities. Machine findings remain reviewable; they do not silently become user truth.
6. **Confirm and organize.** Accept, defer, or reject findings; connect confirmed material to projects; and inspect evidence and lineage when needed.
7. **Continue the work.** Use the Workspace to ask questions and create or update persistent work artifacts.
8. **Measure coverage.** Use Overview for archive statistics, source/platform coverage, recovery progress, and operational status.
9. **Carry work forward.** Export artifacts or create a focused context package for another AI session without transferring the entire archive.

## 3. Product areas

### Workspace

The primary working surface. It provides source intake, conversational work, project context, artifact creation, and on-demand evidence/lineage inspection without sending the user through disconnected pages.

### Library

The durable record of imported material and interpreted knowledge. It includes readable conversations, ideas, decisions, and sources with search, filtering, review state, and source traceability.

### Overview

The measurement and administration surface. It shows archive totals, ideas discovered, recovered work, connected platforms, source coverage, synchronization state, quota/account information, and other workspace-level status.

### Settings and account controls

Hosted deployments provide authentication, subscription management, workspace-team controls, integration management, model/provider configuration where enabled, backup/restore operations, and account administration.

### Task-aware model gateway

SeedReflections maintains a capability catalog for available models and can route extraction, classification, summarization, research, planning, writing, coding, and conversational tasks to a matching model. A workspace may use automatic task-based selection or manually select an available model. The initial catalog prioritizes open models served locally through Ollama; managed and bring-your-own-provider profiles can extend the same catalog when their credentials and endpoints are configured.

Model selection does not itself grant tools. Browsing, filesystem access, code execution, deployment, and external actions require separately implemented and authorized SeedReflections tools. A model API credential supplies inference and does not grant access to a provider's private conversation history.

Model credentials are write-only through the settings API. Local Windows deployments protect them with the current user's DPAPI boundary. Hosted and enterprise deployments use per-credential AES-256-GCM data keys wrapped by a 32-byte master key injected through the deployment secret manager. The database stores only ciphertext, wrapped keys, key hints, and lifecycle metadata; settings responses never return a credential. Hosted BYOK fails closed when the master key is absent or invalid.

## 4. Source ingestion and connectivity

### File and content intake

- ChatGPT-style JSON exports are a primary ingestion path.
- Claude and generic conversation structures can be normalized when supplied as supported JSON or textual documents.
- The document pipeline accepts supported uploaded formats and pasted conversation text.
- Large uploads are staged and processed as jobs rather than requiring the browser to hold the entire archive in memory.
- Source files and message-level evidence are preserved with hashes and coverage metadata.
- Duplicate and changed imports are reconciled rather than silently multiplying the same evidence.

### SeedBridge desktop companion

SeedBridge is a read-only companion for user-authorized local AI-work sources. It currently discovers Codex, Claude Code, Claude Cowork, Cursor, and explicit user-selected folders. The consumer previews eligible content, selects the permitted scope, separately authorizes the connection, and then synchronizes changed JSON/JSONL files. Content hashes prevent unchanged files from being re-imported.

SeedBridge does not modify source files and does not claim access to cloud-only history. Remote pairing requires HTTPS. On Windows, its token is protected with the current user's DPAPI boundary; if OS protection is unavailable, the token is not stored.

### Direct integration API

A user can create a scoped, revocable connection token for an AI platform, agent, automation, MCP-style adapter, plugin, or other integration service. Authorized services deliver supported conversation JSON to the same normalized ingestion pipeline. Tokens are displayed once and stored as digests, not recoverable plaintext. Revocation stops future delivery without deleting already imported evidence.

This makes SeedReflections provider-agnostic at the ingestion boundary. It does not imply that every AI vendor exposes a consumer-history API.

## 5. Intelligence, review, and recovery

- Detects candidate ideas, decisions, constraints, tasks, project intent, drift, and unfinished work.
- Links interpretations to original conversation evidence.
- Supports accept, defer, and reject review decisions.
- Abstains when evidence is insufficient instead of requiring a fabricated finding.
- Scores recovery candidates and explains why work may be worth returning to.
- Preserves project, decision, conflict, lineage, and lifecycle relationships.
- Provides prompt utilities for recovery, intent planting, coherence checks, session handoffs, prioritization, provenance requests, and project bootstrap.
- Supports focused context packages for continuing work in another AI session.

## 6. Persistent work artifacts

The Workspace can create and maintain:

- Plans
- Briefs
- Reports
- Task sets
- Notes

Artifacts support draft, active, complete, and archived states. They can link to conversations, seeds/ideas, and projects; maintain recent version history; and export as Markdown. They are included in normalized workspace backup and restore.

## 7. Provenance, integrity, and recovery controls

- Original source evidence remains inspectable.
- Source and backup digests are verified.
- Evidence and lineage are available on demand rather than occupying permanent workspace space.
- Hosted workspaces are tenant-isolated.
- Integration tokens are scoped, one-time displayed, hashed at rest, and revocable.
- Seed-signature verification state and certificate mappings persist when the external signature authority is configured and available.
- Backups include normalized workspace state, archive records, review state, relationships, artifacts, and preserved source files.
- Restore verifies package and source checksums before changing tenant state.
- Large hosted backups are streamed from disk in bounded chunks.

## 8. Team collaboration

When team collaboration is enabled for a hosted deployment:

- A user may belong to multiple workspaces and switch between them.
- Owners can generate email-bound, single-use invitation links.
- Owners manage member roles.
- Editors can import, analyze, and change workspace material.
- Viewers can read but server-side authorization rejects mutations.
- The last owner cannot be removed or demoted.

Automatic invitation email delivery requires a configured mail provider. Without one, the owner receives the secure invitation link for manual delivery.

## 9. Deployment modes and dormant capabilities

### Local mode

Runs on the user's device with local SQLite persistence. It is appropriate for private use and product evaluation. Hosted billing and team collaboration may remain dormant.

### Hosted mode

Adds authenticated tenant workspaces, public HTTPS origin enforcement, persistent deployment storage, production backups, optional Stripe billing, optional team collaboration, and the hosted SeedBridge pairing boundary.

### Release controls

- Liveness: `/api/v2/health`
- Production readiness: `/api/v2/readiness`
- Automated gate: `release_check.py --origin <public-origin>`

Billing and teams are implemented but feature-flagged. They are not active merely because the code exists. Production activation requires the corresponding configuration, secrets, infrastructure, and successful hosted readiness check.

## 10. Subscription tiers: currently enforced behavior

| Tier | Price shown | Confirmed seed capacity | Monthly reflections | Billing behavior |
|---|---:|---:|---:|---|
| Free | $0 | 20 | 50 | Default hosted account tier |
| Pro | $9/month | Unlimited in application quota logic | 250 | Stripe Checkout/portal when production billing is enabled |
| Master | $20/month | Unlimited in application quota logic | Unlimited in application quota logic | Stripe Checkout/portal when production billing is enabled |

Local mode has a separate **Local** entitlement with Pro-level core quotas (999,999 confirmed seeds and 250 monthly reflections). It is not a paid Pro subscription. The settings and quota surfaces should show Local consistently.

“Unlimited” is implemented as a very high application quota, not a promise of infinite infrastructure. Upload size, storage, compute, security, abuse-prevention, and deployment limits still apply.

### Shared capabilities currently available in the product architecture

The current backend does **not** comprehensively enforce feature-by-feature entitlements for Library, Workspace, artifacts, SeedBridge, direct integration delivery, backups, teams, custom model configuration, priority processing, or developer tools based solely on Free/Pro/Master. The reliable enforced distinctions are the seed and monthly-reflection quotas above, plus deployment feature flags and server authorization.

Consequently, public pricing must not present the following as finished tier guarantees until entitlement rules and tests exist:

- “Team sharing (5 seats)” as a Master-only, five-seat-enforced benefit.
- “Priority parsing” as a Master-only queue with measurable priority behavior.
- “Host Platform Master,” which has no sufficiently precise product definition.
- “Developer tools” or API access as a tier-exclusive benefit unless token creation and API routes enforce that tier.
- “Persisted database” or “local browser storage” as tier properties; persistence is determined primarily by deployment mode, and the authoritative store is SQLite rather than browser-only storage.
- “No limits on the core recovery tools” without immediately disclosing the 20-seed and 50-reflection Free quotas.

## 11. Billing implementation and activation

The production billing path is built around server-created Stripe Checkout and customer-portal sessions. Webhooks verify signatures, use a five-minute tolerance, record durable event claims, reject duplicate processing, and synchronize account plan state. Billing remains dormant until enabled with live Stripe secret, webhook secret, Pro price ID, Master price ID, public HTTPS origin, and registered webhook endpoint.

No page should imply that a paid subscription is purchasable in a deployment where billing readiness is false.

## 12. What the public website should communicate

The front page should make these capabilities understandable in this order:

1. Recover and read AI work that users cannot meaningfully navigate in raw exports.
2. Bring work in through exports, documents, pasted content, authorized local synchronization, or scoped integrations.
3. Normalize many providers into one searchable Library.
4. Identify ideas and decisions while preserving evidence and requiring human review.
5. Continue the work in one Workspace using projects and durable artifacts.
6. Carry focused context into any AI system without moving the entire archive.
7. Protect user control through local-first operation, tenant isolation, scoped access, provenance, backup, and restore.
8. Support governed team workspaces when enabled.

The website should distinguish three connection truths:

- **Supported now:** user exports, uploads, paste, supported documents, SeedBridge-selected local sources, and scoped integration delivery.
- **Possible through adapters:** a vendor, agent, plugin, MCP service, or automation that is authorized to deliver supported data.
- **Not promised:** universal direct access to every vendor's private cloud conversation history.

## 13. Claims governance

Before a claim is published, classify it as one of the following:

- **Available:** implemented, reachable in the intended mode, and verified.
- **Configuration-dependent:** implemented but requires a feature flag, external service, credential, or hosted infrastructure.
- **Adapter-dependent:** possible only when an authorized third-party or user-run adapter supplies the data.
- **Planned:** not yet implemented or not yet governed by the required entitlement/operational controls.

Marketing language must not collapse these categories. Product capability, deployment activation, and vendor permission are three different facts.

## 14. Known website/documentation corrections

The following need reconciliation against this document:

- The landing page does not adequately represent SeedBridge, direct integration delivery, normalized Library views, evidence review, work artifacts, team roles, backup/restore, and production safeguards.
- The landing page includes tier benefits that are not yet enforced as tier entitlements.
- `project-handoff/BILLING_AND_TIERS.md` is incomplete and should no longer be treated as the product definition.
- `project-handoff/PROJECT_OVERVIEW.md` describes the original concept but not the completed platform surface.
- The main `README.md` is an engineering/deployment entry point, not a full product manual.

## 15. Release truth

The application code is a release candidate and the local release gate passes. A public paid release is complete only after the hosted deployment has a real HTTPS domain, durable production storage, live billing configuration if billing is offered, enabled and verified team configuration if teams are offered, a backup/restore drill, and a successful readiness check against the public origin.

