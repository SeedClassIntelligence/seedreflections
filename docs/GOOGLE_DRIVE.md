# Google Drive source: what it is, how to turn it on, what is and is not proven

**Status: built, tested against a stand-in for Google, not yet run against real Google. Off until you add credentials.**
This touches sign-in and stores third-party access tokens, so it needs the founder's review before release.

## What a user sees
Sources → **Google Drive** (or Tools → Connect). They sign in on Google's own page, choose **one folder** (never the whole Drive), review the list of files, tick a consent box, and import. They can **Sync now** later (only new or changed files are imported) and **Disconnect** (access is revoked at Google; documents already imported stay in their archive).

## What it asks Google for
`openid email` and `drive.readonly`. Read-only: it cannot change or delete anything in Drive. Google labels `drive.readonly` a **restricted** scope. That has consequences for a public launch (below).

## Security properties (each has a test)
- Sign-in uses the authorization-code flow with PKCE and a one-time, 10-minute `state` tied to the workspace that started it. A replayed, unknown or expired state is refused.
- The Google password is never seen. Tokens are stored encrypted (hosted: per-credential data keys under the deployment master key; local: OS keychain, or session-only if none) and are never returned by any route.
- Another account cannot browse, preview or import with someone else's connection or review.
- Nothing is imported without the explicit consent flag. Folder ids are validated, so they cannot inject into Drive queries.
- Files over 25 MB, unsupported types, anything beyond 500 files or three folder levels are skipped and reported, never silently dropped.
- Disconnect revokes the refresh token at Google and deletes this workspace's Drive records. Account deletion removes them too (every Drive table carries `workspace_id`).
- If Google reports access removed, the connection is cleared and the user is told to reconnect.
- Hosted storage quota applies to every imported file.

## To turn it on (you do this)
1. In Google Cloud Console, create an OAuth client of type **Web application**.
2. Authorized redirect URI: `https://YOUR-DOMAIN/api/v2/google/callback` (and `http://127.0.0.1:8476/api/v2/google/callback` for a local install).
3. Enable the **Google Drive API** for the project. Configure the consent screen with your Privacy and Terms links (the live pages) and the two scopes above.
4. Set `SEED_REFLECTIONS_GOOGLE_CLIENT_ID` and `SEED_REFLECTIONS_GOOGLE_CLIENT_SECRET` in the deployment secrets (never in the repo).
5. While the app is in **Testing**, only test users you list on the consent screen can connect, which is enough for you and a small group. Moving to **Production** with a restricted scope requires Google's verification and, for apps that store restricted data on servers, an annual third-party security assessment. Plan for that before a public launch; it is Google's process, not something code can skip.

## Not proven
- Any run against real Google (consent screen, real tokens, real Drive responses, Google's rate limits). The tests use a stand-in that follows Google's documented endpoints and error codes. Expect small differences; test with your own Google account in Testing mode first.
- Shared drives, shortcuts, and very large folders (listing is capped at 500 files, 25 MB each, three levels).
- Sheets export only the first sheet as CSV (Google's export limit); Slides export as text.
- The first import covers the files in the folder at the time you press Import, which can include files added after the review; later syncs include new files automatically. The consent text says so.

## Not built
Gmail and Calendar (same sign-in pattern; separate scopes and review), writing back to Drive, and a push-notification based live sync.
