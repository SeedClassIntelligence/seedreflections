# Seed Reflection — Standalone Product

> Find every lost idea in your AI conversations.

**Seed Reflections** imports complete AI conversation exports and documents, preserves their source evidence, maps reviewable ideas and decisions, and provides a workspace for continuing the work.

This folder is completely independent and has no dependencies on the Seed Reflections Code Indexer repository.

---

## Folder Structure

```
seed-reflection-isolated/
├── consumer-dashboard.html ← Main dashboard UI (seeds, garden, chats)
├── admin-dashboard.html    ← Admin panel
├── index.html              ← Landing and setup page
├── about.html              ← Platform info & philosophy
├── js/
│   └── platform.js         ← Frontend platform client
├── server.py               ← Unified local/hosted/enterprise runtime
├── archive_store.py        ← Local archive persistence and evidence analysis
├── tenant_archive_store.py ← Tenant-isolated hosted archive persistence
├── workspace_store.py      ← Normalized workspace persistence
├── auth_store.py           ← Hosted authentication and sessions
├── start.bat               ← Quick start script for Windows
├── data/archive.db         ← Authoritative SQLite database (created at runtime)
├── Dockerfile              ← Non-root production container
└── .env.example            ← Deployment configuration contract
```

---

## Setup & Running Locally

1. **Install document readers**:
   `python -m pip install -r requirements.txt`

2. **Start the unified server**:
    *   **Windows**: Double-click `start.bat`
    *   **Mac/Linux**: Run `python server.py` in your terminal.

3. **Access the dashboard**:
    Open [http://localhost:8476/consumer](http://localhost:8476/consumer) in your browser.

## Container deployment

Run `docker compose up --build`. The application listens on port `8476`, stores all mutable state in the `seed-reflections-data` volume, runs as a non-root user, and exposes `/api/v2/health` for orchestration health checks.

For hosted or enterprise mode, copy `.env.example` into your deployment secret/configuration system. Set an explicit `SEED_REFLECTIONS_PUBLIC_ORIGIN`; startup rejects wildcard or missing origins outside local mode. Do not bake `.env`, databases, uploads, or source evidence into the image.

Public hosting uses `docker-compose.prod.yml` and the TLS reverse-proxy boundary documented in [DEPLOYMENT.md](DEPLOYMENT.md). The application port stays private in that configuration.

## Persistence and recovery

SQLite is authoritative. `seeds.json` is retained only as legacy migration evidence. Hosted tenant backups include normalized workspace state, archive records, review state, relationships, and preserved source files. Restore verifies the package checksum and every source digest before changing tenant state.
For large hosted archives, `GET /api/v2/backup/download` creates a disk-backed ZIP and streams it in bounded chunks instead of base64-expanding source files in application memory.
New containers set `SEED_REFLECTIONS_MIGRATE_LEGACY=0` and therefore start with an empty workspace. Set it to `1` only when intentionally performing the one-time migration of an existing `seeds.json` installation.

## Direct API connections

The **Bring In History → Direct API connections** panel creates a scoped connection token for an AI platform, agent, automation, or integration service. The token is shown once and stored only as a SHA-256 digest. Deliveries enter the same normalized Archive Map used by uploads and synchronized folders.

Send JSON to `POST /api/v2/integrations/import` with `Authorization: Bearer <connection-token>`. Accepted payloads are:

```json
{"conversations":[{"id":"thread-1","title":"Research","messages":[{"role":"user","content":"An idea"}]}]}
```

```json
{"conversation":{"id":"thread-1","title":"Research","messages":[{"role":"user","content":"An idea"}]}}
```

```json
{"id":"thread-1","title":"Research","messages":[{"role":"user","content":"An idea"}]}
```

Manage connections through `GET /api/v2/integrations`, `POST /api/v2/integrations`, and `POST /api/v2/integrations/{id}/revoke`. Revocation stops future deliveries but preserves already imported evidence.

---

## Cryptographic Seed Signature Integration

*   **SDK Loaded**: The frontend automatically loads the Seed Signature SDK statically.
*   **Sign Seed**: Click the **✍️ Sign Seed** button on any unsigned seed in your dashboard.
*   **Session Endpoint**: The backend `server.py` handles the server-to-server POST request to exchange platform API keys for widget session tokens.
*   **Verification persistence**: Once signed, the backend registers the verified signature status and certificate mapping in the authoritative SQLite workspace. `seeds.json` remains legacy migration evidence only.
*   **Graceful Fallback**: If the external authority is offline, the signing flow fails closed and notifies you gracefully.
