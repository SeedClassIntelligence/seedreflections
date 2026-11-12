import glob
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))
import account_erasure
import agent_tokens
import archive_store
import auth_store
import secret_store
import tenant_archive_store
import work_sessions
from test_unified_runtime import UnifiedRuntime

PASSWORD = "strong-password-123"


def rows_for(data_dir, workspace_id):
    """Every row, in every table of every database file, that still names this workspace."""
    found = {}
    for path in glob.glob(os.path.join(data_dir, "*.db")):
        db = sqlite3.connect(path)
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            if "workspace_id" in [c[1] for c in db.execute(f'PRAGMA table_info("{table}")')]:
                count = db.execute(f'SELECT COUNT(*) FROM "{table}" WHERE workspace_id=?', (workspace_id,)).fetchone()[0]
                if count:
                    found[table] = count
        db.close()
    return found


class AccountDeletionHttpTests(unittest.TestCase):
    def test_deleting_an_account_erases_its_data_and_leaves_other_accounts_alone(self):
        runtime = UnifiedRuntime("hosted")
        try:
            people = {}
            for name in ("alpha", "beta"):
                _, signup = runtime.request("POST", "/api/v2/auth/signup", {"name": name, "email": f"{name}@example.com", "password": PASSWORD})
                token = signup["access_token"]
                runtime.request("POST", "/api/v2/imports", {"filename": "h.json", "data": [{"id": name, "title": f"{name} private plan",
                                "messages": [{"id": "m", "role": "user", "content": f"{name} secret roadmap"}]}]}, token=token)
                runtime.upload("/api/v2/imports/upload", "notes.txt", f"{name} notes".encode(), token)
                _, agent = runtime.request("POST", "/api/v2/agent-tokens", {"name": "agent"}, token=token)
                people[name] = {"token": token, "workspace": signup["workspace_id"], "agent": agent["token"]}
            alpha, beta = people["alpha"], people["beta"]
            self.assertTrue(rows_for(runtime.temp.name, alpha["workspace"]))

            self.assertEqual(runtime.request("POST", "/api/v2/account/delete", {"password": PASSWORD}, token=alpha["token"])[0], 400)         # no confirmation
            self.assertEqual(runtime.request("POST", "/api/v2/account/delete", {"password": "wrong-password", "confirm": "DELETE"}, token=alpha["token"])[0], 403)
            self.assertEqual(runtime.request("POST", "/api/v2/account/delete", {"password": PASSWORD, "confirm": "DELETE"})[0], 401)         # not signed in
            self.assertEqual(len(runtime.request("GET", "/api/v2/conversations", token=alpha["token"])[1]["conversations"]), 2)             # nothing lost yet

            status, done = runtime.request("POST", "/api/v2/account/delete", {"password": PASSWORD, "confirm": "DELETE"}, token=alpha["token"])
            self.assertEqual((status, done["deleted"], done["workspaces_erased"]), (200, True, 1))
            self.assertEqual(rows_for(runtime.temp.name, alpha["workspace"]), {})
            self.assertFalse((Path(runtime.temp.name) / "tenant_sources" / alpha["workspace"]).exists())
            self.assertEqual(runtime.request("POST", "/api/v2/auth/login", {"email": "alpha@example.com", "password": PASSWORD})[0], 401)
            self.assertEqual(runtime.request("GET", "/api/v2/conversations", token=alpha["token"])[0], 401)
            self.assertEqual(runtime.request("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, token=alpha["agent"])[0], 401)

            self.assertEqual(len(runtime.request("GET", "/api/v2/conversations", token=beta["token"])[1]["conversations"]), 2)
            self.assertTrue(rows_for(runtime.temp.name, beta["workspace"]))
            self.assertEqual(runtime.request("POST", "/api/v2/auth/login", {"email": "beta@example.com", "password": PASSWORD})[0], 200)
        finally:
            runtime.close()

    def test_local_mode_has_nothing_to_delete(self):
        runtime = UnifiedRuntime("local")
        try:
            self.assertEqual(runtime.request("POST", "/api/v2/account/delete", {"password": "x", "confirm": "DELETE"})[0], 409)
        finally:
            runtime.close()


class SharedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(module, "DB_PATH", root / (name + ".db")) for module, name in
                        ((auth_store, "archive"), (archive_store, "archive"), (tenant_archive_store, "archive"), (secret_store, "archive"),
                         (agent_tokens, "agent_tokens"), (work_sessions, "work_sessions"))]
        for item in self.patches:
            item.start()
        auth_store.initialize()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def signup(self, name):
        return auth_store.signup(name, f"{name}@example.com", PASSWORD, "hosted")

    def test_only_owner_must_hand_over_a_shared_workspace_but_a_member_may_leave(self):
        owner, member = self.signup("owner"), self.signup("member")
        invite = auth_store.create_invitation(owner["workspace_id"], "member@example.com", "editor", owner["user"]["id"])
        auth_store.accept_invitation(invite["token"], member["user"]["id"])
        with self.assertRaises(ValueError) as refused:
            auth_store.delete_account(owner["user"]["id"], PASSWORD)
        self.assertIn("only owner", str(refused.exception))
        self.assertTrue(auth_store.login("owner@example.com", PASSWORD))                          # still intact

        result = auth_store.delete_account(member["user"]["id"], PASSWORD)                       # a member can leave
        self.assertEqual((result["workspaces_left"], result["workspaces_erased"]), (1, 1))       # shared one left, own personal one erased
        self.assertEqual([m["email"] for m in auth_store.list_members(owner["workspace_id"])], ["owner@example.com"])
        self.assertTrue(auth_store.delete_account(owner["user"]["id"], PASSWORD)["deleted"])     # now the owner is alone and can delete

    def test_erasure_refuses_the_local_workspace_and_bad_ids(self):
        for bad in ("local", "", "../etc", "x"):
            with self.assertRaises(ValueError):
                account_erasure.erase_workspace_data(bad)


if __name__ == "__main__":
    unittest.main()
