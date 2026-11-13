# Seed Reflections deployment

## Local/private runtime

Use `start.bat` or `docker compose up --build`. This path binds the product directly for private use and does not configure public TLS.

## Hosted runtime

For a step-by-step guide to a small Linux server with your own domain, setup, update and backup scripts, see `docs/DEPLOY_SMALL_SERVER.md`.

The production Compose overlay keeps the Python service on a private container network and exposes only Caddy. Caddy obtains and renews TLS certificates, redirects HTTP to HTTPS, enforces the proxy upload boundary, and adds transport security headers.

1. Point the chosen DNS name at the host.
2. Copy `.env.example` to the host's protected environment configuration.
3. Set `SEED_REFLECTIONS_DOMAIN` to the DNS name, without a scheme or path.
4. Review storage, upload, conversation, analysis, and authentication limits.
5. Run `docker compose -f docker-compose.prod.yml config` and inspect the rendered configuration.
6. Run `docker compose -f docker-compose.prod.yml up -d --build`.
7. Verify `https://<domain>/api/v2/health` before allowing user traffic.
8. Run `python release_check.py --origin https://<domain>` and allow traffic only when it exits successfully and every readiness check passes.

Back up the `seed-reflections-data` volume and the Caddy data volume through the hosting provider. Do not expose port `8476` publicly in hosted mode.

The application database uses WAL mode and persistent SQLite authentication throttling. A single shared data volume is required. Do not scale the application container across hosts while using SQLite; moving to a network database is a separate architecture decision.

`/api/v2/health` is a liveness check. `/api/v2/readiness` is the release gate: it verifies the HTTPS public origin, persistence, resource boundaries, enabled billing configuration, and enabled team membership storage. It reports status only and never returns configured secret values.

## Billing activation

Billing remains dormant unless `SEED_REFLECTIONS_BILLING_ENABLED=1`. Before enabling it, provision `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO`, and `STRIPE_PRICE_MASTER` in the deployment secret manager. Register `/api/v1/stripe/webhook` as the Stripe webhook destination and subscribe at minimum to `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, and `customer.subscription.deleted`.

Checkout and customer-portal sessions are created server-side. Hosted billing endpoints require an authenticated runtime user, remote Stripe calls use idempotency keys, webhook signatures use a five-minute replay tolerance, and processed Stripe event IDs are retained durably for duplicate suppression. The admin overview reports only whether secrets and prices are configured; it never returns their values. Do not place Stripe secrets in the repository, browser code, container image, or `docker-compose` file.
