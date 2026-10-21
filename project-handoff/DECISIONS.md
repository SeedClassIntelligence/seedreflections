# Architecture Decision Log

* **ADR-001: Structured Database wrapping**: We wrapped flat seed lists in a structured dictionary database to support multi-entity schemas (Projects, Decisions, Conflicts) while preserving backward-compatibility.
* **ADR-002: Client-side Degraded Mode**: The dashboard falling back to heuristic parsing ensures that users can access their local archives even when the server is offline or LLM rate limits are hit.
* **ADR-003: Process-wide Concurrency Lock**: Introduced a process-wide `threading.RLock()` to guarantee thread-safe read-modify-write transactions within the server process, avoiding lost updates. Expanded to fully lock the Plant Seed (`/api/v1/seeds`) endpoint.
* **ADR-004: Atomic Disk Persistence**: Transitioned database saves to write to a temp file, perform disk flush and fsync, and replace the database file atomically using `os.replace` to prevent file corruption. Clean up temp files if serialization fails.
* **ADR-005: Relational Integrity Enforcement**: Configured backend validators to check for the actual existence of projects and seeds before saving decisions or conflicts, preventing orphaned entities. Enforced on both Plant Seed and Update Seed endpoints.
* **ADR-006: Cascade Deletion**: Implemented cascade cleanup inside the `/api/v1/seeds/delete` handler to remove orphaned references from child/parent seeds, decisions, and conflicts, preserving integrity across all tables.
* **ADR-007: First-Class Provenance Relationships**: Transitioned to provenance-backed relationship records containing creation source (`created_by`), confidence, message/conversation coordinates (`supporting_sources`), and explicit approval toggles.
* **ADR-008: Immutable Signed Seed Evolution**: Established that cryptographically signed seeds are immutable. Core updates block direct modifications, instead cloning the record, marking the original `"Superseded"`, and drawing a lineage curve.
* **ADR-009: Multi-Weighted Lost Seed Scoring**: Refactored the lost-seed scanner to evaluate a combined weighted score of descendants, decisions, versions, transcript keywords, and update dates, grouping seeds into distinct confidence warning tiers.
* **ADR-010: Split Mission vs. Scope Drift Metrics**: Divided drift analysis into independent indices: Mission Drift (charter alignment) and Scope Drift (seeds without accepted architectural decisions).
* **ADR-012: Cryptographic Signature Digest Enforcement**: Immature mutations are blocked by validating the actual signature record and computing SHA-256 content digests rather than checking a Boolean flag alone.
* **ADR-013: Split Evolution Proposing and Supersession Authorization**: Separated evolution proposing from the final supersession authorization. Seeds evolve as Proposed drafts, and can only transition the original to Superseded through a distinct user approval action.
* **ADR-014: Tombstone Provenance Retention on Delete**: Seed deletion check converts seeds to a "Tombstoned" continuity state if they participate in active signatures, decisions, conflicts, or relationships, preventing historical context erasure.
* **ADR-015: Retracted and Rejected Relationship States**: Retracted/Rejected relationship edges are preserved via tombstone records instead of silent deletions, keeping full audit logs of structural shifts.
* **ADR-016: Portable Context Package v2 Format**: Standardized a unified markdown-pasted context envelope and JSON dump query endpoint `/api/v1/projects/export-package` to boot chats with complete boundaries.
* **ADR-017: Collision-Resolving Package Ingestion**: Created `/api/v1/projects/import-package` which merges incoming seeds, decisions, and relationships, resolving collisions via signatures and timestamps.
* **ADR-018: Headless Browser Automation Test Runner**: Configured Playwright-based headless browser integration checks to guarantee UI stability across seed/decision creation, setting changes, and export actions.
* **ADR-019: Graph Traversal and Calculations Profiling Benchmarks**: Added scaling benchmarks to monitor graph hops, lost seed scoring, and drift intersections to maintain sub-10ms performance baselines.



