# Signing with Seed Signature

Seed Signature is the signing authority for every platform. SeedReflections is one **partner platform**: its server holds a platform key, asks the authority for a short-lived signing session, and the user signs inside the authority's own widget. SeedReflections never holds or creates a signing key. Contract: `docs/EMBED_WIDGET.md` and `docs/PARTNER_PORTAL.md` in the seedsignature repository.

## What a user does
Work artifacts → write and save → **Sign with Seed Signature**. The widget opens, they upload the exported file and sign. The signature id and certificate link are saved with the artifact. If the text is edited afterwards, the artifact says "Signed, then edited" until it is signed again, because the certificate no longer matches it.

## How the connection works
1. The browser asks SeedReflections for a session (`POST /api/v2/seed-signature/session`, signed-in users only, rate limited).
2. The SeedReflections server calls `POST {SEED_SIGNATURE_API_URL}/api/v1/embed/sessions` with `X-Platform-API-Key`, `external_user_id` (the SeedReflections user id), `content_type` and `title`.
3. The authority answers with `sessionToken` and `widgetUrl` (15-minute session). SeedReflections passes on only those, and refuses an answer whose widget address is on another host.
4. The browser loads the authority's own widget script and opens the widget. On completion the page sends `signatureId` and `certificateUrl` to `POST /api/v2/artifacts/{id}/signature`, which accepts only a certificate address on the authority.

## To turn it on (a Seed Signature administrator does the first part)
1. In Seed Signature, an administrator issues SeedReflections a platform key. A controlled first-party platform can be issued directly by an administrator (see `PARTNER_PORTAL.md`).
2. Set `SEED_SIGNATURE_API_URL` (for example the Cloud Run platform address) and `SEED_SIGNATURE_PLATFORM_API_KEY` in the server's `.env`, then restart.
3. Rotate the key from Seed Signature's Partner Access if it is ever exposed. SeedReflections needs no code change.

## A security problem found and fixed while building this
SeedReflections contained an older, built-in "signing" simulator (`/api/seed/create`, `/widget/sign`, `/widget/sign/submit`, `/sdk/seed-signature-widget.js`). It produced ids from a plain hash, not from Seed Signature, and it was reachable **without signing in, including in hosted mode**: anyone could mint a fake "signature" with a certificate link on our domain, and the page it generated printed the submitted text unescaped (stored cross-site scripting on the app's own address). Now:
- All of those routes return 404 in hosted and enterprise mode, and in local mode unless `SEED_REFLECTIONS_LOCAL_SIGNING_DEMO=1` is set on purpose. The dashboard no longer loads the built-in widget.
- Everything the demo pages print is HTML-escaped, and the in-memory session list is capped.
- Recommendation: delete the simulator entirely once you have confirmed nothing you use depends on it.

## Not proven
- Nothing was run against the real Seed Signature platform or its real widget; tests use a stand-in that follows the documented path, header and answer shape.
- The widget signs the file the user uploads there. SeedReflections records the artifact text's digest at signing time and flags later edits, but it cannot yet prove the uploaded file is that exact text. Server-side bridge signing (`/api/v1/bridge/*` in the authority) would close that gap and needs a separate design with you.
