# Current Implementation State

The platform is fully operational as a **local-first web application** containing:
* **Frontend UI**:
  * `index.html`: Product landing page, Stripe tier comparisons, and static checkout gateways.
  * `auth.html`: User account setup, plan selection, and session bootstrap logic.
  * `consumer-dashboard.html`: The core dashboard workspace combining chat, staging pipelines, and the interactive Idea Garden. Features include:
    * Single-submission creation forms for Projects, Decisions, Conflicts, and Lineage Relationships.
    * Persistent expansion state for seed detail panels.
    * Detailed, defensively escaped rendering of intent conflicts and comparisons.
    * **🧬 Lineage & Drift Intelligence View**: SVG lineage graph canvas showing focused 2-3 hop neighborhoods, dynamic node inspector, dual Mission Drift & Decision Coverage gauges, and lost seed checklist alerts.
    * **History Playback Timeline**: Event-driven vertical timeline tracking creations, updates, cryptographic signatures, decisions, and supersessions.
  * `js/platform.js`: Sovereign utility library managing local state, API redirections, and Stripe portal routing.
* **Backend Server**:
  * `server.py`: Local Python HTTPServer running on port `8476` serving as the API controller and datastore. Features include:
    * Process-wide reentrant transaction locking (`DB_LOCK = threading.RLock()`) protecting read-modify-write loops.
    * Atomic database writes using temp file syncing (`fsync`) and replacement (`os.replace`).
    * Direct entity creation routing, strict parameter validation (enums, types, non-empty checks), and automatic creation timestamps.
    * Strict project and seed existence verification for decisions, conflicts, and relationships.
    * **First-Class Relationships**: Storage schema and mutation endpoints supporting explicit provenance details (`proposed_by`, `approval_status`, `approved_by`, `approved_at`, `approval_basis`), registry validation, duplicate check, and retractions.
    * **Immutable Signed Seed Evolution**: Cryptographic content signatures and SHA-256 digest checks block core updates on signed seeds. Successor seeds are created via `/api/v1/seeds/evolve` as Proposed drafts, and can be Superseded via `/api/v1/seeds/supersede` after relationship approval.
    * **Weighted Lost-Seed Scanner**: Inverted protective signal scanner evaluating descendant links, decisions, versions, and transcripts, returning Candidate tiers.
    * **Decision Coverage**: Metrics evaluating Mission Drift (lexical overlap analysis details) and Decision Coverage (percentage of seeds with approved decisions).
    * **Tombstone Provenance Deletion**: Deletes are converted to `Tombstoned` continuity states if the target seed has signature histories or active relationship edges.
    * **Portable Context Packages (v2)**: Generates and imports portable JSON/Markdown packages via `/export-package` and `/import-package` with signature-attestation merge logic.
    * **SCIA Adapter**: Context queries served via `/api/v1/scia/context` to feed external assistants.
    * Null-safe markdown and JSON export pipelines defaulting safely to placeholders.
    * Normalized update endpoint supporting both flat fields and nested `{field, value}` objects.
  * `seeds.json`: Inspectable JSON database.
  * `config.json`: LLM provider credentials and model choices.
* **Testing & Verification**:
  * `tests/test_migration_regression.py`: Overhauled integration test suite with automated sandbox database isolation, background server execution on dynamic free socket ports, and **32 passing tests** covering concurrency, providers, cascade deletes, explicit evolution, signature digests, retractions, and context packages.
  * `tests/test_browser_automation.py`: Headless browser Playwright automation testing UI interactions.
  * `tests/benchmark_performance.py`: High-performance diagnostics reporting traversal overhead under mock scale load.

---

### Project Specification Manifest
The system comprises exactly **24 specifications** detailing core sub-capabilities located within the `/project-handoff/` directory.
