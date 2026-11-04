import unittest

from tests.test_unified_runtime import UnifiedRuntime


class WorkArtifactTests(unittest.TestCase):
    def test_artifact_lifecycle_preserves_sources_and_versions(self):
        runtime=UnifiedRuntime("local")
        try:
            status,created=runtime.request("POST","/api/v2/artifacts",{"type":"plan","title":"SeedBridge release plan",
                "content":"1. Package the bridge.\n2. Verify synchronization.","conversation_ids":["conversation-1"],"seed_ids":["seed-1"]})
            self.assertEqual(status,201); artifact=created["artifact"]
            self.assertEqual(artifact["conversation_ids"],["conversation-1"])
            status,updated=runtime.request("POST",f"/api/v2/artifacts/{artifact['artifact_id']}",{
                "status":"active","content":artifact["content"]+"\n3. Publish the verified build."})
            self.assertEqual(status,200); self.assertEqual(updated["artifact"]["status"],"active")
            self.assertEqual(len(updated["artifact"]["versions"]),1)
            status,listing=runtime.request("GET","/api/v2/artifacts")
            self.assertEqual(status,200); self.assertEqual(listing["total"],1)
            status,exported=runtime.request("GET",f"/api/v2/artifacts/{artifact['artifact_id']}/export")
            self.assertEqual(status,200); self.assertIn("Publish the verified build",exported["markdown"])
            status,deleted=runtime.request("POST",f"/api/v2/artifacts/{artifact['artifact_id']}",{"action":"delete"})
            self.assertEqual(status,200); self.assertTrue(deleted["deleted"])
            self.assertEqual(runtime.request("GET","/api/v2/artifacts")[1]["total"],0)
        finally: runtime.close()

    def test_artifact_validation_rejects_unknown_type(self):
        runtime=UnifiedRuntime("local")
        try:
            status,_=runtime.request("POST","/api/v2/artifacts",{"type":"unknown","title":"No","content":"No"})
            self.assertEqual(status,400)
        finally: runtime.close()


if __name__=="__main__": unittest.main()
