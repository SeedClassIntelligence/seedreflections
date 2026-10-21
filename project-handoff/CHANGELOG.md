# Changelog

### [v1.5.0] - 2026-07-19
* **Portable Context Packages (v2)**: Implemented `/api/v1/projects/export-package` to compile complete JSON and structured Markdown packages for pasting into new AI chats. Added export modals with copy and download options on the dashboard.
* **Authoritative Ingestion & SCIA Adapter**: Implemented `POST /api/v1/projects/import-package` with collision-resolution merge logic (signature-based checks and timestamp comparisons) and `GET /api/v1/scia/context` context query adapter for external assistants. Added import file uploaders and raw JSON merge views.
* **Browser Automation Suite**: Added `tests/test_browser_automation.py` using Python's Playwright API, covering seed creation, decision mappings, and context package modal interactions.
* **Traversal & Performance Benchmarking**: Added `tests/benchmark_performance.py` profiling lost seeds calculations (5.38ms), 3-hop neighborhood canvas traversals (1.09ms), and intent charter overlaps (7.16ms) under scale (1k seeds, 2k relationships).
* **Test Suite Expansion**: Added 3 new integration tests covering context exports, imports, and SCIA queries, bringing the suite to 32 passing checks.

### [v1.4.0] - 2026-07-19
* **Signed-Content Immutability pass**: Direct mutations on signed seeds reject core changes with HTTP 403 Forbidden using actual cryptographic signatures and digest verification.
* **Explicit Evolution & Supersession**: Added `/api/v1/seeds/evolve` to propose successor seeds without automatic supersession, and `/api/v1/seeds/supersede` to authorize supersession transitions after user relationship approvals.
* **Provenance Relationships v2**: Replaced Boolean approvals with explicit fields (`proposed_by`, `approval_status`, `approved_by`, `approved_at`, `approval_basis`, `supporting_sources`), registry-validated types, duplicate prevention, and retraction tombstones.
* **Decision Coverage**: Renamed scope drift to Decision Coverage and implemented independent percentage calculations in both the backend analysis and frontend dashboard visual dials.
* **Lexical Overlap Analysis**: Labeled keyword overlaps as deterministic lexical analysis (not semantic), returning matched terms, missing charter words, and new terms arrays with confidence limitations.
* **Tombstone Provenance Deletion**: Configured delete seed endpoint to preserve historical provenance by tombstoning instead of hard-deleting seeds participating in signatures, decisions, conflicts, or relationships.
* **Harden Integration Suite**: Expanded integration checks to 29 tests, verifying signed mutations blocks, retractions, duplicate edges, and tombstones.

### [v1.3.0] - 2026-07-18
* **Lineage & Provenance Relationships**: Created a new `relationships` table in the database structure with `created_by`, `confidence`, `supporting_sources`, `approved` and `approval_date` tracking. Added API endpoints for creating, deleting, and approving relationships.
* **Immutable Signed Seed Evolution**: Refactored the update seed endpoint to block in-place mutation of cryptographically signed seeds. Any modifications automatically create an evolved clone seed, map the original to `Superseded`, and establish an `"Evolved Into"` lineage connection.
* **Weighted Lost-Seed Engine**: Implemented `/api/v1/analysis/lost-seeds` to compute a multi-weighted lost seed score based on absence of descendants, decisions, versions, transcript mentions, and age, categorizing seeds into Possible, Likely, and High Confidence tiers.
* **Dual Drift Analysis**: Split drift diagnostics into independent metrics: `Mission Drift` (deviation from core Project charter) and `Scope Drift` (unapproved seeds lacking decision references).
* **Interactive Neighborhood Graph**: Implemented a scalable visual SVG lineage graph in the dashboard. Displays focused 2-3 hop subgraphs centered on a selected seed, with double-click re-centering, curve links, and a sidebar inspector.
* **Chronological History Timeline**: Added dynamic event-driven history playback timelines inside seed inspector sidebars, sorting creation, signatures, decision links, and evolutions.
* **Expanded Integration Suite**: Added 4 new integration tests covering relationships, evolution cloning, lost seed scoring, and drift metrics, raising the test suite to 21 passing checks.

### [v1.2.0] - 2026-07-18
* **Concurrency Locking**: Integrated a process-wide `threading.RLock()` database transaction lock covering all read-modify-write loops, including locking the Plant Seed (`/api/v1/seeds`) endpoint.
* **Atomic Save Operations**: Refactored `save_db` to serialize JSON data to a `.tmp` file, flush buffers, call `os.fsync` for disk synchronization, and swap files atomically using `os.replace`. Added cleanup code to remove the `.tmp` file on serialization failure.
* **Input Validation & Safety**: Added strict validation rules for Projects, Decisions, and Conflicts. Enforced enum validators and project existence checks on the Plant Seed endpoint.
* **POST Route Restructure**: Cleaned up `do_POST` dispatch chain to use a single `if/elif/else` structure, immediately returning a JSON response for unknown routes. Removed redundant `import re` statements inside function bodies.
* **Export Expansion**: Rewrote `/export` Markdown builder to dynamically handle missing attributes in legacy records, outputting clean default placeholders instead of Python `None` values.
* **UI Controls & Modals**: Added owner, stage, status, severity, and type dropdowns to creation modals. Prevented double-submissions via button disabling and "Saving..." text indicators.
* **Seed Detail State**: Implemented expanded seed panel memory across visual garden re-renders.
* **Test Isolation**: Overhauled regression tests to run in temporary directories on dynamically allocated free ports with multi-threaded concurrent write checks, mock LLM provider path integration, and config/transcript directory sandboxing.
* **Cascade Delete**: Implemented cascade deletion in the Delete Seed endpoint to clean up orphaned references inside decisions and conflicts.

### [v1.1.0] - 2026-07-16
* Added Project Grouping.
* Added Source Provenance records.
* Added multi-dimensional status fields (Evidence, Authority, Continuity).
* Added Decision and Conflict Registers.
* Added Markdown and JSON exports for seed detail.
