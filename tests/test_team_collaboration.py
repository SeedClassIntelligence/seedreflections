import tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import auth_store
from tests.test_unified_runtime import UnifiedRuntime


class TeamCollaborationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.database=Path(self.temp.name)/"team.db"
        self.db_patch=patch.object(auth_store,"DB_PATH",self.database); self.db_patch.start()
        auth_store.initialize()

    def tearDown(self):
        self.db_patch.stop(); self.temp.cleanup()

    def test_invite_accept_switch_and_role_lifecycle(self):
        owner=auth_store.signup("Owner","owner@example.com","a-strong-password","hosted")
        member=auth_store.signup("Member","member@example.com","another-password","hosted")
        invitation=auth_store.create_invitation(owner["workspace_id"],"member@example.com","editor",owner["user"]["id"])
        accepted=auth_store.accept_invitation(invitation["token"],member["user"]["id"])
        self.assertEqual(accepted["role"],"editor")
        memberships=auth_store.list_workspaces(member["user"]["id"])
        self.assertEqual(len(memberships),2); self.assertTrue(any(item["active"] for item in memberships))
        auth_store.update_member_role(owner["workspace_id"],member["user"]["id"],"viewer")
        members=auth_store.list_members(owner["workspace_id"])
        self.assertEqual(next(item for item in members if item["email"]=="member@example.com")["role"],"viewer")
        removed=auth_store.remove_member(owner["workspace_id"],member["user"]["id"])
        self.assertTrue(removed["removed"])
        self.assertEqual(len(auth_store.list_workspaces(member["user"]["id"])),1)

    def test_invitation_cannot_be_accepted_by_another_email(self):
        owner=auth_store.signup("Owner","owner@example.com","a-strong-password","hosted")
        wrong=auth_store.signup("Wrong","wrong@example.com","another-password","hosted")
        invitation=auth_store.create_invitation(owner["workspace_id"],"member@example.com","viewer",owner["user"]["id"])
        with self.assertRaisesRegex(ValueError,"does not match"):
            auth_store.accept_invitation(invitation["token"],wrong["user"]["id"])

    def test_last_owner_cannot_be_demoted_or_removed(self):
        owner=auth_store.signup("Owner","owner@example.com","a-strong-password","hosted")
        user_id=owner["user"]["id"]
        with self.assertRaisesRegex(ValueError,"at least one owner"):
            auth_store.update_member_role(owner["workspace_id"],user_id,"editor")
        with self.assertRaisesRegex(ValueError,"last workspace owner"):
            auth_store.remove_member(owner["workspace_id"],user_id)


class TeamPermissionRuntimeTests(unittest.TestCase):
    def test_viewer_can_read_shared_workspace_but_cannot_mutate_it(self):
        runtime=UnifiedRuntime("hosted",{"SEED_REFLECTIONS_TEAM_ENABLED":"1"})
        try:
            status,owner=runtime.request("POST","/api/v2/auth/signup",{"name":"Owner","email":"owner@example.com","password":"owner-password-strong"})
            self.assertEqual(status,201); owner_token=owner["access_token"]
            status,member=runtime.request("POST","/api/v2/auth/signup",{"name":"Viewer","email":"viewer@example.com","password":"viewer-password-strong"})
            self.assertEqual(status,201); member_token=member["access_token"]
            status,invitation=runtime.request("POST","/api/v2/team/invitations",{"email":"viewer@example.com","role":"viewer"},owner_token)
            self.assertEqual(status,201)
            status,accepted=runtime.request("POST","/api/v2/team/invitations/accept",{"token":invitation["token"]},member_token)
            self.assertEqual(status,200); self.assertEqual(accepted["role"],"viewer")
            self.assertEqual(runtime.request("GET","/api/v2/workspace",token=member_token)[0],200)
            status,denied=runtime.request("POST","/api/v2/projects",{"name":"Viewer mutation"},member_token)
            self.assertEqual(status,403); self.assertEqual(denied["code"],"insufficient_role")
            status,team=runtime.request("GET","/api/v2/team",token=owner_token)
            self.assertEqual(status,200); self.assertEqual(len(team["members"]),2)
        finally:
            runtime.close()


if __name__=="__main__": unittest.main()
