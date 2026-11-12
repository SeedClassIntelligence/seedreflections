# SeedReflections: CTO review findings

- **Reviewed baseline:** `3a4a981` (code: `706e979`), November 11, 2026
- **Method:** I ran the real server in local and hosted modes against a synthetic corpus and drove the dashboard with a real browser. Nothing here touched production data or services.
- **Recommendation: NO-GO for public release.** One security item (S1) needs your decision first. Eight defects I found are already fixed on this branch and listed in section 2.

Labels used: **VERIFIED** (observed running), **TEST** (automated test evidence), **INFERENCE** (reasoned, not observed), **OPEN**, **DECISION** (founder decision needed).

---

## 0. The handoff's "137 passing" did not reproduce

| | Result |
|---|---|
| Baseline on Linux | 137 run, **1 failed**, 5 skipped |
| Cause | `test_mock_llm_provider_paths` needs a Windows-only credential store (see D1) |
| After this review | **148 run, 0 failed, 5 skipped** |
| Still not run here | 4 browser tests (Python Playwright not installed in this environment) and 1 Windows DPAPI test |

---

## 1. Release blockers still open

| ID | Sev | Finding | Class |
|---|---|---|---|
| **S1** | **Critical** | **Local mode is readable and writable by any website.** The API needs no authentication and answers any `Origin` with `Access-Control-Allow-Origin: *`, approves preflight, and accepts any `Host` header (DNS rebinding). A page the user merely visits can read the whole archive from `localhost:8476` and write to it. I confirmed the headers; I did not build a browser exploit. | VERIFIED headers, INFERENCE exploit |
| **S2** | High | Admin password defaults to `changeme` when `ADMIN_PASSWORD` is unset, and the `/admin` check uses a non-constant-time comparison. I added a readiness check for hosted mode (D8) but did not audit the admin API routes. | VERIFIED default, OPEN rest |
| **R1** | High | **No real release gate ran.** `release_check.py` only reads `/api/v2/readiness`, which validates configuration strings. It passed for `https://example.test` with no TLS, certificate, HSTS or header check. No real HTTPS origin, billing webhook or team feature was exercised. | VERIFIED |
| **R2** | ~~High~~ **Closed (Nov 11)** | Local in-app restore now exists: verified preview, typed `REPLACE` confirmation, safety snapshot, automatic rollback, live credentials/tokens/identity preserved. Proven through the real dashboard on a 3,306-conversation archive and in `tests/test_local_restore.py` (6 tests incl. tamper, mid-restore failure rollback, running-job refusal, expired token). Device-loss recovery = restore from the user's own complete backup; hosted account recovery remains a separate identity-verified process (not built). | VERIFIED, TEST |
| **P1** | High | **Review queue cannot be worked at scale.** The UI renders 250 cards (about 1,510 buttons) with no pagination control, no filters and no batch actions, so 3,657 of 3,907 candidates are unreachable. The API now pages (D4); the UI does not yet. | VERIFIED |

### S1: proposed patch (not applied, needs approval)

In local mode, allow cross-origin access only from the server's own origin, and refuse requests whose `Host` is not `localhost` or `127.0.0.1`:

- Echo `Access-Control-Allow-Origin` only when `Origin` is `http://localhost:<port>` or `http://127.0.0.1:<port>`; otherwise omit it.
- Return 403 when the `Host` header is not `localhost[:port]` or `127.0.0.1[:port]`.
- Check that SeedBridge and your own tools use no other origin before shipping.

I held this back because it changes access control. Say the word and I will apply it with tests.

---

## 2. Defects found and fixed on this branch

Each was reproduced first, then fixed, and verified again. "Test" means the new regression file `tests/test_cto_review_regressions.py`: 11 tests, of which **9 fail on the pre-fix code**. The two that pass either way are a control case (a fully readable archive stays "complete") and the store-level Overview count (that bug was in the request handler, so it is proven by the live run, not by this test).

| ID | Sev | What was wrong | Evidence | Fix |
|---|---|---|---|---|
| **D1** | High | **Static server exposed the repository.** Any file under the working directory was served unauthenticated, including `server.py`, `.git/config`, `/data/archive.db` and `/admin-dashboard.html` (bypassing the `/admin` gate). The path check was a string `startswith`. Docker is partly protected (data lives in `/data`), but source and anything else in the image were exposed. | VERIFIED before: all returned 200. After: 17 paths return 404, all public pages and assets return 200 | Strict allowlist (`static_file_path`): public extensions only, top-level pages or `assets/ js/ sdk/`, no dotfiles, real-path containment. Test. |
| **D2** | High | **Search crashed on punctuation.** `C++`, `what?`, `pricing-model` or a bare `AND` dropped the connection with no response. | VERIFIED, 4 of 5 queries gave empty replies | Queries tokenised and quoted. Count and list now share one filter. Test. |
| **D3** | High | **Gaps were hidden.** JSON archive coverage was a hard-coded `complete` / `unreadable: []`. 5 empty conversations were counted as processed and, with search, were invisible. | VERIFIED: 3005/3005 complete before; **3000/3005 partial, 5 named** after, in local and hosted | Coverage derived from what was normalised. Test. |
| **D4** | High | **Review queue lied about its size.** The local queue was silently capped at 250 and the UI said "250 pending" while 3,907 were pending. Hosted was unbounded. | VERIFIED | `limit`/`offset`, `total`, `has_more`; UI shows "Showing 250 of 3,907". Test. |
| **D5** | Critical | **Relationship generation was O(n²) and unbounded.** 3,907 candidates produced **3,092,674 links**, a **1.68 GB** database from 26 MB of input, and a 116 s analysis. The hosted version also ran a query per pair. At a realistic "years of AI use" scale this is days of compute and terabytes. | VERIFIED, measured | Inverted index plus a per-candidate cap of 8. **15,616 links, 97 MB, 21 s** on the same corpus. Test. |
| **D6** | High | **Overview metrics were wrong.** Messages summed only the first 500 conversations (3,643 vs 28,590). Conversations and Awaiting review read **0** on a populated archive because they depended on other tabs having loaded. Per-provider "Ideas / Classified" counted accepted items only and gave 0 after full analysis. | VERIFIED with screenshots | Totals come from `/api/v2/overview`; provider cards now show analyzed, awaiting review and unreadable per platform, from the server. The 28,590 figure was verified live; its unit test does not distinguish the old code. |
| **D7** | Medium | **Local backup returned 409.** The "portable archive" card promised backup and restore; three of its five buttons had no handler (`exportSeeds`, `exportInterchangePackage`, `importInterchangePackage`). | VERIFIED | Local backup download added (SQLite online backup, SHA-256 manifest, credentials stripped; integrity `ok` on 3,306 conversations). `exportSeeds` implemented. The two package buttons removed (needs a project-scoped design). Test. |
| **D8** | Medium | **Readiness overclaimed.** On Linux it reported `credential_storage: passed`, yet saving a model key returned 503. Hosted mode never checked for the default admin password. | VERIFIED | Both checks are now honest. Test. |
| **D9** | Medium | **Invented usage numbers** in Settings: "12 / 50", "84 / 250", "84 / Unlimited" were hard-coded per plan. Pricing cards showed the claims your own product doc forbids (`Host Platform Master`, `Priority parsing`, `Persisted database`). The UI defaulted to Pro while the doc says Free. | VERIFIED | Real usage or "Usage unavailable"; forbidden claims removed from dashboard and `auth.html`; badge follows the plan the server enforces. I introduced and then fixed a request loop during this change; the final browser run is clean. |

---

## 3. Open findings (not fixed)

| ID | Sev | Finding | Class |
|---|---|---|---|
| **O1** | ~~High~~ **Closed (Nov 11)** | Model keys off Windows: OS keychain (macOS Keychain / Linux Secret Service via `keyring`); where none exists, saved keys are disabled and an explicit session-only key is offered; no plaintext fallback; keys never in backups. Also fixed: the Settings screen toasted "Key settings updated!" even when the server rejected the key. Verified live (503 + clear message, session key works, no file on disk contains the key, restart forgets it) and in `tests/test_model_key_storage.py` (7 tests). **Not verified:** a real macOS Keychain or Linux Secret Service (this container has neither; tests use an in-memory stand-in). | VERIFIED, TEST |
| **O2** | High | **Hosted restore is bound to its own workspace and overwrites silently.** A backup cannot be restored into a new account (correct for isolation, but account-loss recovery is undefined), and restore discards post-backup work with no confirmation or safety snapshot. Tamper, truncation and non-zip uploads were all rejected with state unchanged. | VERIFIED, DECISION |
| **O3** | Medium | **"Ideas" are regex keyword rules** (`evidence_rules_v1`: "we decided", "todo", "let's"), not model analysis. Public copy and onboarding must not imply AI-identified ideas. | VERIFIED, DECISION on wording |
| **O4** | Medium | **Plan source of truth is split.** The enforced account plan (local default `pro`, identity "Workspace Developer") differs from the `user_plan` setting. Hosted mode has no usage route (the only one is legacy v1, blocked in hosted). | VERIFIED |
| **O5** | Medium | **Local mode has no source-evidence route** (`/api/v2/sources` returns 409). I did not verify how the dashboard's "Evidence & lineage" gets source text locally. | OPEN |
| **O6** | Low | Keyboard focus is suppressed on the project selector; headline copy still says "Idea Intelligence" in the page title. | VERIFIED |
| **O7** | Info | Public pricing still says "Unlimited seeds / reflections". Your doc says this is a high application quota and must be disclosed as such. | VERIFIED |

---

## 4. What passed

- **Tenant isolation (VERIFIED, hosted, 2 tenants):** the second tenant got 404 on the first tenant's conversation, source, source download and candidate review; anonymous requests got 401.
- **Auth:** rate limiting kicked in on the 11th bad login (429); a weak password was rejected; malformed JSON returns 400 on four write routes.
- **Hosted CORS and headers:** origin pinned to the configured origin; `X-Frame-Options`, `nosniff`, `Referrer-Policy` present.
- **Import at scale:** a 26 MB export with 3,005 conversations imported in 5 s as a background job; Claude-format and text imports worked; a truncated JSON file failed loudly with a clear reason.
- **Hosted backup and restore (VERIFIED):** a 5.3 MB backup in 1.4 s; a tampered source was rejected (`integrity verification failed`); a valid restore returned the workspace to its backup-time state.
- **Interface:** zero console errors, zero failed requests and no dead controls after the fixes. *Correction (Nov 11):* this item originally also said there was zero horizontal overflow at 768 and 390 px on every tab. That was overstated: the narrow-width check had covered only four tabs. A full 10-tab check found the Artifacts tab overflowing by 123px (768) and 411px (390); it is fixed and all 10 tabs now pass at 1440 / 768 / 390.
- **Evidence path:** accepted decisions carry source conversation and message IDs.

---

## 5. Not done, and why it matters

- **No real HTTPS deployment.** TLS, HSTS, certificates and the release gate against a public origin are untested (R1).
- **No live Stripe, team or email flows.** Only the existing unit tests cover them.
- **No provider connector tests.** I had no provider accounts. From code and docs: SeedBridge and `/api/v2/integrations/import` are ingestion paths, not provider-authorized cloud connectors. I did not audit `/api/v2/tools/*`.
- **Synthetic data only.** I wrote the ChatGPT and Claude export shapes myself; they are not real exports. No PDFs, large (GB) archives, or concurrent users were tested.
- **No human usability review.** The interface was checked mechanically and by screenshot, not with a new user.
- **Admin dashboard and admin API** were not audited beyond the gate; **secret history** was not scanned.
- **Responsive panel behaviour** was checked for overflow only, not collapse and reflow.

## 6. Decisions I need from you

1. **S1:** approve the local-mode origin and Host restriction (recommended, release blocker).
2. **R2 / O2:** local in-app restore, and what recovery should look like after account loss.
3. **O1:** how local model keys should be protected off Windows.
4. **O3:** whether to keep rule-based extraction as the baseline and say so plainly, or add model-assisted extraction first.
5. **O4:** which plan a local user is on by default.
6. **P1:** priority and shape of the Review queue (pagination, filters, batch accept).

## 7. Housekeeping

- `project-handoff/ARCHITECTURE.md`, `CURRENT_IMPLEMENTATION.md` and `DESIGN_SYSTEM.md` are marked historical.
- About 20 one-off `patch_*.py`, `repair_*.py` and similar scripts sit in the repository root. They are excluded from the Docker image, but they are clutter and a source-disclosure risk; I left them alone pending your call.
- `workroom-prototype.html` is not in the repository; I did not touch it.

---

## 9. Found during the sign-in and comparison UI work (Nov 11)

| ID | Sev | Finding | Status |
|---|---|---|---|
| **S3** | **High** | **Hosted sign-in cannot work.** `js/platform.js` hard-codes the legacy `/api/v1` API, which hosted mode blocks, so login and signup through `auth.html` fail on a hosted server ("Sign in is temporarily unavailable"). VERIFIED against a running hosted server. Predates the redesign. | **OPEN, needs approval** (authentication change). Proposed fix: choose the v2 auth endpoints when `/api/v2/capabilities` reports hosted. |
| S4 | High | Open redirect on the sign-in page via the `next` parameter. | **Fixed** (same-origin paths only), before and after tested. |
| S5 | High | The public Admin tab printed the default admin password ("changeme") and hinted at `.env`. | **Fixed** in the page. The default itself is still accepted by the server when `ADMIN_PASSWORD` is unset (hosted readiness now fails on it). |
| O8 | Medium | **Password reset does not exist** (no endpoint, no email sending), while the UI claimed a reset link was sent. | UI made honest. **DECISION:** what recovery path to offer. |
| O9 | Low | Password hint said 8+ chars with an uppercase and a number; the server requires 12 characters. | **Fixed** |
