# Testing & Acceptance

### Running Tests
Automated regression and migration tests are run with:
```bash
python -m unittest tests/test_migration_regression.py
```

### Acceptance Checklist
1. **Isolated Integration Harness**: Test server starts on a dynamically selected free socket port and writes to a `TemporaryDirectory` sandbox, ensuring zero impact on user files. Automatically isolates `seeds.json`, `config.json`, and the `transcripts` directory.
2. **Server Teardown Safety**: Server shuts down and terminates threads cleanly using `shutdown()`, `server_close()`, and a bounded thread `join(timeout=5)`.
3. **Legacy flat database structures migrate without data loss**.
4. **Strict enum and format validation works** on Seeds, Projects, Decisions, and Conflicts. Invalid inputs return 400 Bad Request and make zero database updates.
5. **Relationship validation works**: Decisions and Conflicts cannot link to non-existent project or seed IDs.
6. **Concurrent write serialization works**: Concurrent multi-threaded API requests are serialized without data races or corrupted JSON outputs. Verified for both same-seed field updates and unique concurrent seed planting.
7. **Draft signatures verify successfully and store trust states**.
8. **Minimal legacy exports remain null-safe** and display placeholder strings instead of raw Python `None` values.
9. **Unknown API routes return a clean JSON 404 response**.
10. **Mock LLM Provider Paths validation**: Intercepts external request paths to OpenAI and Gemini, verifying correct schema parsing and persistence.
11. **Cascade deletion integrity**: Deleting a seed cleans up matching conflicts and removes references from decisions.
12. **Lineage Relationships**: Creation, deletion, and approval validation of first-class relationships.
13. **Immutable signed seed updates**: Updates to signed seeds block core mutations (Forbidden 403) via cryptographic SHA-256 digest validation.
14. **Weighted lost seed detection**: Scans and tiers lost seeds using multi-weighted indicators.
15. **Decision Coverage**: Calculates independent indexes for Mission Drift and Decision Coverage.
16. **Explicit Evolution & Supersession**: Creating proposed successors and authorizing supersessions after relationship approvals.
17. **Retraction/Rejection tombstones**: Retracting/rejecting relationships creates active provenance indicators rather than silent deletions.
18. **Provenance Tombstoning Deletion**: Deleting seeds with signed history or active relationships tombstones the seeds to protect lineage tracking.
19. **Portable Context Package Export**: Compiling formatted Markdown payloads and JSON provenance files via `/api/v1/projects/export-package`.
20. **Collision-Resolving Ingestion**: Ingesting packages and resolving overlaps via `POST /api/v1/projects/import-package`.
21. **SCIA Context Integration**: Querying active seeds, decisions, and approved relationships via `/api/v1/scia/context`.

### Running Browser Automation Tests
Requires `playwright` python library:
```bash
pip install playwright
playwright install chromium
python -m unittest tests/test_browser_automation.py
```

### Running Performance Benchmarks
Profile graph traversals and lost seed calculations under mock dataset load (1,000 seeds, 2,000 relationships):
```bash
python tests/benchmark_performance.py
```
