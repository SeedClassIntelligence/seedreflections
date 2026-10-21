# Next Builder Prompt

You are tasked with implementing Phase 5 of the Seed Reflection system expansion.

### Current Base State
* Database mutations are protected using a process-wide `threading.RLock()` and written atomically via temporary file replacement.
* All modal forms enforce field validation, display "Saving..." indicators, and disable buttons during active requests.
* Defensively escaped, multi-attribute Linked Conflicts are displayed dynamically in expanded seed panels.
* **Lineage & Provenance Relationships**: Dynamic visual SVG lineage neighborhood graph rendering, registry validation, duplicate check, and retracted/rejected tombstones.
* **Immutable Signed Seed Evolution**: Cryptographic content digest verification blocks direct core modifications. Successor seeds are created via `/api/v1/seeds/evolve` as Proposed drafts, and are authorized as Superseded via `/api/v1/seeds/supersede` after user relationship approval.
* **Weighted Lost-Seed Scanner**: Inverted protective signal evaluation returns Candidate tiers (Possible, Likely, High Confidence).
* **Dual Drift Metrics**: Calculations and frontend gauges render Mission Drift (lexical analysis) and Decision Coverage.
* **Tombstone Deletion**: Preserves historical provenance on seeds that participate in active signatures, decisions, conflicts, or relationships.
* **Portable Context Packages (v2)**: Packages complete JSON/Markdown context configurations for chat bootstrapping, importable via collision-resolving merge handlers.
* **SCIA Adapter**: Context queries served via `/api/v1/scia/context` to feed external assistants.
* The test harness executes integration tests using dynamically allocated ports and isolated temporary sandboxes with 32 passing test assertions, plus Playwright browser automation tests and scaling traversal benchmarks.

### Your Goal
1. **FileCell Alignment Scanner**: Build a local checker verifying that exported seeds align with actual files (FileCells) inside the bounded WorkCell scope.
2. **Constellation Sync Adapters**: Implement optional stub integrations for private Seed Signature authorities or enterprise backend verification interfaces.
3. **Enterprise Authentication Integration**: Provide configuration endpoints to secure workspace API keys under global settings templates.

