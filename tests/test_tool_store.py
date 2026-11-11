import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import archive_store, secret_store, tool_store


class ToolStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.db=Path(self.temp.name)/"tools.db"
        self.patches=[patch.object(archive_store,"DB_PATH",self.db),patch.object(secret_store,"DB_PATH",self.db)]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def test_catalog_separates_support_configuration_and_connection(self):
        with patch.dict(os.environ,{},clear=True):
            tools=tool_store.list_tools("workspace")
        self.assertEqual(next(item for item in tools if item["id"]=="files")["state"],"ready")
        gmail=next(item for item in tools if item["id"]=="gmail")
        self.assertEqual(gmail["state"],"configuration_required")
        self.assertFalse(gmail["connected"])

    def test_configured_provider_is_not_claimed_as_connected(self):
        with patch.dict(os.environ,{"SEED_REFLECTIONS_GOOGLE_CLIENT_ID":"client","SEED_REFLECTIONS_GOOGLE_CLIENT_SECRET":"secret"},clear=True):
            gmail=next(item for item in tool_store.list_tools("workspace") if item["id"]=="gmail")
        self.assertEqual(gmail["state"],"authorization_required")
        self.assertFalse(gmail["connected"])


if __name__=="__main__": unittest.main()
