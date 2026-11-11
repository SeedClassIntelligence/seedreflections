import os
import unittest

from tests.test_unified_runtime import UnifiedRuntime


class ReleaseReadinessTests(unittest.TestCase):
    def test_local_runtime_is_ready_without_live_services(self):
        runtime=UnifiedRuntime("local")
        try:
            status,result=runtime.request("GET","/api/v2/readiness")
            failing={item["name"] for item in result["checks"] if not item["passed"]}
            self.assertEqual(status,200); self.assertTrue(result["ready"]); self.assertEqual(failing,set())
            detail=next(item["detail"] for item in result["checks"] if item["name"]=="credential_storage")
            if os.name!="nt":
                # Without an OS keychain, saved keys are disabled and readiness must say so plainly.
                import secret_store
                self.assertEqual(detail,secret_store.local_backend_status()["detail"])
        finally: runtime.close()

    def test_hosted_runtime_fails_closed_without_https_origin(self):
        runtime=UnifiedRuntime("hosted")
        try:
            status,result=runtime.request("GET","/api/v2/readiness")
            self.assertEqual(status,503); self.assertFalse(result["ready"])
            self.assertFalse(next(item for item in result["checks"] if item["name"]=="public_origin")["passed"])
        finally: runtime.close()

    def test_enabled_billing_requires_complete_configuration(self):
        runtime=UnifiedRuntime("hosted",{"SEED_REFLECTIONS_PUBLIC_ORIGIN":"https://seed.example",
            "SEED_REFLECTIONS_BILLING_ENABLED":"1","STRIPE_SECRET_KEY":"sk_test_configured"})
        try:
            status,result=runtime.request("GET","/api/v2/readiness")
            self.assertEqual(status,503)
            self.assertFalse(next(item for item in result["checks"] if item["name"]=="billing")["passed"])
            self.assertNotIn("sk_test_configured",str(result))
        finally: runtime.close()


if __name__=="__main__": unittest.main()
