import urllib.request
import urllib.parse
import json
import http.client

BASE = "http://127.0.0.1:8476"

def test_endpoint(name, method, path, payload=None, headers=None, expected_status=200):
    url = f"{BASE}{path}"
    headers = headers or {}
    data = None
    if payload is not None:
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        elif isinstance(payload, bytes):
            data = payload

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            code = resp.getcode()
            body = resp.read()
            passed = (code == expected_status)
            res_str = f"PASS" if passed else f"FAIL (got {code}, expected {expected_status})"
            print(f"[{res_str}] {name} -> {method} {path} => {code}")
            return code, body, resp.info()
    except urllib.error.HTTPError as e:
        passed = (e.code == expected_status)
        res_str = f"PASS" if passed else f"FAIL (got {e.code}, expected {expected_status})"
        print(f"[{res_str}] {name} -> {method} {path} => {e.code}")
        return e.code, e.read(), e.headers
    except Exception as e:
        print(f"[ERROR] {name} -> {method} {path} => Exception: {e}")
        return None, None, None

print("=== 1. Core Pages & Static Serving ===")
test_endpoint("Landing Page", "GET", "/index.html", expected_status=200)
test_endpoint("Consumer Workspace (/consumer)", "GET", "/consumer", expected_status=200)
test_endpoint("Legacy Dashboard Redirect (/dashboard.html)", "GET", "/dashboard.html", expected_status=200) # Note: urlopen follows 301 to /consumer -> 200
test_endpoint("Seed Signature Widget SDK", "GET", "/sdk/seed-signature-widget.js", expected_status=200)

print("\n=== 2. Health & Context APIs ===")
test_endpoint("API Health Probe", "GET", "/api/v1/health", expected_status=200)
test_endpoint("Seeds List", "GET", "/api/v1/seeds", expected_status=200)
test_endpoint("Seeds Stats", "GET", "/api/v1/seeds/stats", expected_status=200)
test_endpoint("SCIA Context Adapter", "GET", "/api/v1/scia/context?project_id=default_project", expected_status=200)
test_endpoint("Export Context Package", "GET", "/api/v1/projects/export-package?project_id=default_project", expected_status=200)
test_endpoint("Trust & Provenance Status", "GET", "/trust-status", expected_status=200)

print("\n=== 3. Commercial Tier Limits & Tenant Metadata ===")
test_endpoint("Consumer Identity & Quotas", "GET", "/api/v1/users/me", expected_status=200)
test_endpoint("Consumer Dashboard Summary", "GET", "/api/v1/users/me/consumer-dashboard", expected_status=200)

print("\n=== 4. Admin Master Control Endpoints ===")
test_endpoint("Admin Master Overview", "GET", "/api/v1/admin/overview", expected_status=200)
test_endpoint("Database Backup Snapshot", "GET", "/api/v1/admin/backup", expected_status=200)
test_endpoint("Clean Orphan Transcripts", "POST", "/api/v1/admin/transcripts/clean", payload={}, expected_status=200)

print("\n=== 5. Stripe Webhook Ingestion ===")
mock_webhook_payload = {
    "id": "evt_live_audit_test",
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "customer_email": "audit_test@company.com",
            "amount_total": 900
        }
    }
}
test_endpoint("Stripe Webhook Ingestion", "POST", "/api/v1/stripe/webhook", payload=mock_webhook_payload, expected_status=200)

print("\n=== 6. AI Killswitch & Guardrails ===")
# Engage killswitch
test_endpoint("Engage AI Killswitch", "POST", "/api/v1/admin/ai/killswitch", payload={"killswitch_enabled": True}, expected_status=200)
# Verify LLM test call is blocked while killswitch active
test_endpoint("Test LLM Call Blocked by Killswitch", "POST", "/api/v1/admin/test-llm", payload={"prompt": "hi"}, expected_status=400)
# Disengage killswitch
test_endpoint("Disengage AI Killswitch", "POST", "/api/v1/admin/ai/killswitch", payload={"killswitch_enabled": False}, expected_status=200)

print("\n=== 7. Tenant CRUD Lifecycle ===")
# Create
create_acc_payload = {
    "name": "Audit Verification Tenant",
    "email": "audit_verif@tenant.com",
    "role": "consumer",
    "plan": "free",
    "password": "PasswordAudit999!"
}
code, body, _ = test_endpoint("Create Tenant Account", "POST", "/api/v1/admin/users/create", payload=create_acc_payload, expected_status=201)
created_id = None
if body:
    try:
        created_id = json.loads(body.decode("utf-8")).get("account", {}).get("id")
    except Exception:
        pass

if created_id:
    # Update plan
    test_endpoint("Update Tenant Plan to Pro", "POST", "/api/v1/admin/users/update", payload={"user_id": created_id, "plan": "pro"}, expected_status=200)
    # Reset password
    test_endpoint("Reset Tenant Password", "POST", "/api/v1/admin/users/reset-password", payload={"user_id": created_id, "password": "NewSecretPassword!"}, expected_status=200)
    # Delete created tenant
    test_endpoint("Delete Tenant Account", "POST", "/api/v1/admin/users/delete", payload={"user_id": created_id}, expected_status=200)

# Verify root admin deletion is strictly blocked
test_endpoint("Root Admin Self-Deletion Block Guard", "POST", "/api/v1/admin/users/delete", payload={"user_id": "usr_admin_master"}, expected_status=403)

print("\n=== Full Server Audit Click-Around Complete ===")
