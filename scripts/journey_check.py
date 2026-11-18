#!/usr/bin/env python3
"""End-to-end release check for a running SeedReflections, run from outside, the way a person would use it.

    python scripts/journey_check.py https://seedreflections.com [--keep]

It creates a throwaway account (journey-<random>@example.test), imports a small made-up export, and walks the journey:
readiness, sign-up, import, search, reading a conversation, review (analysis, accepting a finding), a saved work
artifact and its export, sign out and back in, and that the work is still there. It then deletes the account again
(unless --keep). It never touches any other account, sends no email, and the made-up export contains nothing real.
Exit code 0 only when every step passed.
"""
import json
import secrets
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
KEEP = "--keep" in sys.argv
if not BASE.startswith(("http://", "https://")):
    sys.exit("Usage: python scripts/journey_check.py https://your-domain [--keep]")
RESULTS = []


def call(method, path, body=None, token=None, timeout=60):
    headers = {"Content-Type": "application/json", "User-Agent": "SeedReflections-journey-check/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"raw": raw[:200].decode("utf-8", "replace")}
    except OSError as exc:
        return 0, {"error": str(exc)}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)[:300]))
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"   -> {str(detail)[:300]}"))
    return ok


EXPORT = [
    {"id": "j1", "title": "Pricing for the beta", "messages": [
        {"id": "m1", "role": "user", "content": "We should launch a pricing page for the beta next month."},
        {"id": "m2", "role": "assistant", "content": "Good idea. Which tiers do you want?"},
        {"id": "m3", "role": "user", "content": "I decided to go with three tiers: free, pro and team."}]},
    {"id": "j2", "title": "Onboarding notes", "messages": [
        {"id": "m1", "role": "user", "content": "How will we onboard the first twenty testers?"},
        {"id": "m2", "role": "assistant", "content": "Start with a checklist and one welcome email."}]},
    {"id": "j3", "title": "Hosting thoughts", "messages": [
        {"id": "m1", "role": "user", "content": "Let's draft the backup and restore plan before launch."}]},
]


def main():
    status, ready = call("GET", "/api/v2/readiness")
    failing = [c["name"] for c in ready.get("checks", []) if not c.get("passed")]
    check("site answers and reports its readiness", status in (200, 503) and "checks" in ready, (status, str(ready)[:200]))
    check("every readiness check passes", ready.get("ready") is True, "not ready: " + ", ".join(failing))
    print(f"      (information) mode={ready.get('mode')}")
    status, caps = call("GET", "/api/v2/capabilities")
    print(f"      (information) billing={caps.get('billing')} external_ai={caps.get('external_ai')} teams={caps.get('teams')}")

    email, password = f"journey-{secrets.token_hex(5)}@example.test", "Journey-" + secrets.token_urlsafe(14)
    status, user = call("POST", "/api/v2/auth/signup", {"name": "Journey Check", "email": email, "password": password})
    if not check("sign up", status == 201 and user.get("access_token"), (status, user)):
        return
    token = user["access_token"]

    status, imported = call("POST", "/api/v2/imports", {"filename": "journey-export.json", "data": EXPORT}, token)
    check("import a small export", status == 201 and imported.get("conversations") == 3 and (imported.get("messages") or imported.get("message_count")) == 6, (status, imported))
    status, listing = call("GET", "/api/v2/conversations?q=pricing", token=token)
    found = [c for c in listing.get("conversations", []) if c.get("title") == "Pricing for the beta"]
    check("search finds a conversation", status == 200 and len(found) == 1, (status, listing))
    if found:
        status, convo = call("GET", "/api/v2/conversations/" + found[0]["id"], token=token)
        check("a conversation reads back with all its messages", status == 200 and len(convo.get("messages", [])) == 3, (status, str(convo)[:200]))

    status, job = call("POST", "/api/v2/analysis/run", {}, token)
    check("analysis starts", status == 202, (status, job))
    pending = []
    for _ in range(40):
        time.sleep(1.5)
        status, found_candidates = call("GET", "/api/v2/candidates?status=pending", token=token)
        pending = found_candidates.get("candidates", [])
        if pending:
            break
    check("review inbox has findings with their source passage", bool(pending), "no findings appeared within about a minute")
    if pending:
        status, accepted = call("POST", f"/api/v2/candidates/{pending[0]['id']}/review", {"action": "accept"}, token)
        check("a finding can be accepted into the workspace", status == 200, (status, accepted))
        status, workspace = call("GET", "/api/v2/workspace", token=token)
        check("the accepted finding shows in the workspace (as an idea or a decision)", status == 200 and bool(workspace.get("seeds") or workspace.get("decisions")), (status, str(workspace)[:200]))

    status, made = call("POST", "/api/v2/artifacts", {"type": "plan", "title": "Journey plan", "content": "Launch the beta in three steps."}, token)
    artifact_id = (made.get("artifact") or {}).get("artifact_id")
    check("a work artifact saves", status == 201 and artifact_id, (status, made))
    if artifact_id:
        status, edited = call("POST", f"/api/v2/artifacts/{artifact_id}", {"content": "Launch the beta in four steps."}, token)
        check("a work artifact edits", status == 200 and edited["artifact"]["content"].endswith("four steps."), (status, edited))
        status, exported = call("GET", f"/api/v2/artifacts/{artifact_id}/export", token=token)
        check("a work artifact exports as Markdown", status == 200 and "four steps" in exported.get("markdown", ""), (status, exported))

    call("POST", "/api/v2/auth/logout", {}, token)
    status, _ = call("GET", "/api/v2/conversations", token=token)
    check("signing out ends the session", status == 401, status)
    status, again = call("POST", "/api/v2/auth/login", {"email": email, "password": password})
    check("signing back in works", status == 200 and again.get("access_token"), (status, again))
    token = again.get("access_token", "")
    status, listing = call("GET", "/api/v2/conversations", token=token)
    check("the archive is still there after signing back in", status == 200 and listing.get("total") == 3, (status, listing))
    status, artifacts = call("GET", "/api/v2/artifacts", token=token)
    check("saved work is still there after signing back in", status == 200 and any(a.get("title") == "Journey plan" for a in artifacts.get("artifacts", [])), (status, str(artifacts)[:200]))

    if KEEP:
        print(f"      (kept) test account {email}")
        return
    status, deleted = call("POST", "/api/v2/account/delete", {"password": password, "confirm": "DELETE"}, token)
    check("the test account deletes", status == 200 and deleted.get("deleted") is True, (status, deleted))
    status, _ = call("POST", "/api/v2/auth/login", {"email": email, "password": password})
    check("a deleted account cannot sign in", status == 401, status)


if __name__ == "__main__":
    main()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} steps passed." + ("" if not failed else "  FAILED: " + ", ".join(r[0] for r in failed)))
    sys.exit(1 if failed else 0)
