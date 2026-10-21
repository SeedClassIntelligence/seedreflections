# Seed Reflections deployment

## Local/private runtime

Use `start.bat` or `docker compose up --build`. This path binds the product directly for private use and does not configure public TLS.

## Hosted runtime

The production Compose overlay keeps the Python service on a private container network and exposes only Caddy. Caddy obtains and renews TLS certificates, redirects HTTP to HTTPS, enforces the proxy upload boundary, and adds transport security headers.

1. Point the chosen DNS name at the host.
2. Copy `.env.example` to the host's protected environment configuration.
3. Set `SEED_REFLECTIONS_DOMAIN` to the DNS name, without a scheme or path.
4. Review storage, upload, conversation, analysis, and authentication limits.
5. Run `docker compose -f docker-compose.prod.yml config` and inspect the rendered configuration.
6. Run `docker compose -f docker-compose.prod.yml up -d --build`.
7. Verify `https://<domain>/api/v2/health` before allowing user traffic.

Back up the `seed-reflections-data` volume and the Caddy data volume through the hosting provider. Do not expose port `8476` publicly in hosted mode.

The application database uses WAL mode and persistent SQLite authentication throttling. A single shared data volume is required. Do not scale the application container across hosts while using SQLite; moving to a network database is a separate architecture decision.
