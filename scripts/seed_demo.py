#!/usr/bin/env python3
"""Fill a LOCAL SeedReflections with made-up demo data so you can look at the screens.

    python server.py                       (in one window)
    python scripts/seed_demo.py            (in another; default http://127.0.0.1:8476)

It imports six invented conversations, runs the analysis, accepts some of the findings (and leaves some waiting, so the
"needs your attention" part has something in it), and saves two work products linked to ideas. Nothing real is used. It
refuses to run against anything but a loopback address, so it cannot put demo data into a real or hosted account.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = (next((a for a in sys.argv[1:] if not a.startswith("-")), "http://127.0.0.1:8476")).rstrip("/")
host = urllib.parse.urlsplit(BASE).hostname
if host not in ("127.0.0.1", "localhost", "::1"):
    sys.exit(f"Refusing to add demo data to {BASE}. This script only works on a local server (127.0.0.1).")

DEMO = [
    ("Pricing for the beta", [
        ("user", "We should launch a pricing page for the beta next month."),
        ("assistant", "Good idea. Which tiers do you want to offer?"),
        ("user", "I decided to go with three tiers: free, pro and team."),
        ("assistant", "That keeps the choice simple. What about refunds?"),
        ("user", "How will we handle refunds for annual plans?")]),
    ("Onboarding the first testers", [
        ("user", "How will we onboard the first twenty testers?"),
        ("assistant", "A checklist and one welcome email usually work."),
        ("user", "Let's draft the onboarding email and decide who sends it.")]),
    ("Hosting and backups", [
        ("user", "I want to run everything on one server with nightly backups."),
        ("assistant", "Make sure you can restore, not just back up."),
        ("user", "I decided to rehearse a restore before we invite anyone."),
        ("user", "We need to write down what happens if the server is lost.")]),
    ("Signing everything", [
        ("user", "Every platform should sign through Seed Signature."),
        ("assistant", "Keep the signing key on the authority only."),
        ("user", "Let's build the partner key flow next."),
        ("user", "Should the signing key ever leave the authority?")]),
    ("Browser extension idea", [
        ("user", "A one-click way to save the conversation I have open would help a lot."),
        ("assistant", "Only when the person clicks, and only that conversation."),
        ("user", "I decided it must never read pages in the background.")]),
    ("Launch checklist", [
        ("user", "We need a launch checklist covering terms, hosting, backups and support."),
        ("assistant", "Add a rollback plan for the first deploy."),
        ("user", "Let's write the checklist and review it with a lawyer.")]),
]


def call(method, path, body=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(); return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        sys.exit(f"{method} {path} failed: {exc.code} {exc.read()[:200]!r}")
    except OSError as exc:
        sys.exit(f"Could not reach {BASE}. Is `python server.py` running? ({exc})")


def main():
    if call("GET", "/api/v2/capabilities").get("mode") != "local":
        sys.exit("This server is not in local mode. Demo data is only for a local server.")
    data = [{"id": f"demo-{i}", "title": title, "messages": [{"id": f"m{j}", "role": role, "content": text} for j, (role, text) in enumerate(messages)]}
            for i, (title, messages) in enumerate(DEMO)]
    imported = call("POST", "/api/v2/imports", {"filename": "demo-history.json", "data": data})
    print(f"Imported {imported.get('conversations')} demo conversations.")
    call("POST", "/api/v2/analysis/run", {})
    pending = []
    for _ in range(60):
        time.sleep(1)
        pending = call("GET", "/api/v2/candidates?status=pending").get("candidates", [])
        if len(pending) >= 6:
            break
    keep_waiting = max(2, len(pending) // 3)
    for candidate in pending[:-keep_waiting]:
        call("POST", f"/api/v2/candidates/{candidate['id']}/review", {"action": "accept"})
    workspace = call("GET", "/api/v2/workspace")
    seeds = workspace.get("seeds", [])
    if seeds:
        call("POST", "/api/v2/artifacts", {"type": "plan", "title": "Beta pricing and launch plan", "status": "active", "seed_ids": [seeds[0]["seed_id"]],
                                            "content": "1. Publish the pricing page with three tiers.\n2. Write the refund policy for annual plans.\n3. Invite the first twenty testers."})
        call("POST", "/api/v2/artifacts", {"type": "task_set", "title": "Before launch: backups and restore", "status": "draft", "seed_ids": [s["seed_id"] for s in seeds[1:2]],
                                            "content": "- Rehearse a restore on a copy\n- Write the server-loss runbook\n- Confirm nightly backups are running"})
    overview = call("GET", "/api/v2/overview")
    print(f"Ideas: {len(seeds)}   findings still waiting for you: {overview.get('pending')}   work products: 2")
    print(f"\nOpen {BASE}/consumer and look at the Workspace, then click Continue on an idea and try its Sources, Outputs and Decisions tabs.")


if __name__ == "__main__":
    main()
