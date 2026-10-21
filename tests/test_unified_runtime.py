import http.client, io, json, os, socket, subprocess, sys, tempfile, time, unittest, urllib.error, urllib.request, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def free_port():
    with socket.socket() as sock: sock.bind(("127.0.0.1",0)); return sock.getsockname()[1]

class UnifiedRuntime:
    def __init__(self,mode,extra_env=None):
        self.temp=tempfile.TemporaryDirectory(); self.port=free_port(); env=os.environ.copy()
        env.update({"SEED_REFLECTIONS_DATA_DIR":self.temp.name,"SEED_REFLECTIONS_PORT":str(self.port),
                    "SEED_REFLECTIONS_MODE":mode,"SEED_REFLECTIONS_PUBLIC_ORIGIN":"http://127.0.0.1:3000",
                    "PYTHONDONTWRITEBYTECODE":"1"})
        env.update(extra_env or {})
        self.process=subprocess.Popen([sys.executable,str(ROOT/"server.py")],cwd=ROOT,env=env,
                                      stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        for _ in range(100):
            try: self.request("GET","/api/v2/health"); break
            except Exception: time.sleep(.05)
        else: raise RuntimeError("unified runtime failed to start")
    def request(self,method,path,data=None,token=None):
        headers={"Content-Type":"application/json"}
        if token: headers["Authorization"]="Bearer "+token
        request=urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        try:
            with urllib.request.urlopen(request,timeout=5) as response: return response.status,json.loads(response.read())
        except urllib.error.HTTPError as exc: return exc.code,json.loads(exc.read())
    def upload(self,path,filename,content,token):
        boundary="seed-reflections-test-boundary"
        body=(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
              f"Content-Type: application/octet-stream\r\n\r\n").encode()+content+f"\r\n--{boundary}--\r\n".encode()
        connection=http.client.HTTPConnection("127.0.0.1",self.port,timeout=5)
        connection.request("POST",path,body=body,headers={"Authorization":"Bearer "+token,
            "Content-Type":f"multipart/form-data; boundary={boundary}","Content-Length":str(len(body))})
        response=connection.getresponse(); result=response.status,json.loads(response.read()); connection.close(); return result
    def download(self,path,token):
        request=urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",headers={"Authorization":"Bearer "+token})
        try:
            with urllib.request.urlopen(request,timeout=5) as response: return response.status,response.read()
        except urllib.error.HTTPError as exc: return exc.code,exc.read()
    def close(self): self.process.terminate(); self.process.wait(timeout=5); self.temp.cleanup()

class UnifiedRuntimeTests(unittest.TestCase):
    def test_local_connector_discovers_imports_and_incrementally_syncs_conversations(self):
        runtime=UnifiedRuntime("local")
        try:
            source=Path(runtime.temp.name)/"claude-project"; source.mkdir()
            history=source/"session.jsonl"
            history.write_text(json.dumps({"sessionId":"session-1","type":"user","uuid":"m1","timestamp":"2026-10-19T10:00:00Z",
                "message":{"role":"user","content":"We should build connected conversation sync for SeedReflections."}})+"\n",encoding="utf-8")
            status,available=runtime.request("GET","/api/v2/connectors"); self.assertEqual(status,200); self.assertFalse(available["desktop_bridge_required"])
            status,preview=runtime.request("POST","/api/v2/connectors/preview",{"provider":"claude_code","root_path":str(source)})
            self.assertEqual(status,200); self.assertEqual(len(preview["items"]),1)
            status,connected=runtime.request("POST","/api/v2/connectors/connect-preview",{"preview_id":preview["preview_id"],
                "selected_paths":["session.jsonl"],"include_new":True,"auto_sync":True})
            self.assertEqual(status,201); self.assertEqual(connected["sync"]["conversations"],1)
            self.assertEqual(connected["sync"]["reconciliation"]["added"],1)
            connector_id=connected["connector"]["id"]
            _,listing=runtime.request("GET","/api/v2/conversations"); self.assertEqual(listing["total"],1)
            history.write_text(history.read_text(encoding="utf-8")+json.dumps({"sessionId":"session-1","type":"assistant","uuid":"m2","parentUuid":"m1",
                "timestamp":"2026-10-19T10:01:00Z","message":{"role":"assistant","content":"The source can remain linked and update incrementally."}})+"\n",encoding="utf-8")
            status,synced=runtime.request("POST",f"/api/v2/connectors/{connector_id}/sync",{}); self.assertEqual(status,200); self.assertEqual(synced["files_changed"],1)
            status,health=runtime.request("GET",f"/api/v2/connectors/{connector_id}/health"); self.assertEqual(status,200); self.assertTrue(health["healthy"])
            _,listing=runtime.request("GET","/api/v2/conversations"); conversation_id=listing["conversations"][0]["id"]
            _,conversation=runtime.request("GET",f"/api/v2/conversations/{conversation_id}"); self.assertEqual(len(conversation["messages"]),2)
            status,_=runtime.request("POST",f"/api/v2/connectors/{connector_id}/disconnect",{}); self.assertEqual(status,200)
            self.assertEqual(runtime.request("GET","/api/v2/conversations")[1]["total"],1)
        finally: runtime.close()

    def test_generic_connected_folder_imports_documents_through_the_same_archive(self):
        runtime=UnifiedRuntime("local")
        try:
            source=Path(runtime.temp.name)/"work-folder"; source.mkdir()
            (source/"product-notes.md").write_text("# Product direction\n\nBuild a source-agnostic archive that preserves evidence and supports continued work.",encoding="utf-8")
            status,preview=runtime.request("POST","/api/v2/connectors/preview",{"provider":"folder","root_path":str(source)})
            self.assertEqual(status,200); self.assertEqual(preview["items"][0]["format"],"md")
            status,connected=runtime.request("POST","/api/v2/connectors/connect-preview",{"preview_id":preview["preview_id"],
                "selected_paths":["product-notes.md"],"include_new":False,"auto_sync":True})
            self.assertEqual(status,201); self.assertEqual(connected["sync"]["conversations"],1)
            status,listing=runtime.request("GET","/api/v2/conversations")
            self.assertEqual(status,200); self.assertEqual(listing["total"],1)
            self.assertIn("product-notes",listing["conversations"][0]["title"].lower())
        finally: runtime.close()

    def test_scoped_api_connection_delivers_conversations_and_can_be_revoked(self):
        runtime=UnifiedRuntime("local")
        try:
            status,created=runtime.request("POST","/api/v2/integrations",{"name":"External AI automation","provider":"other_ai"})
            self.assertEqual(status,201); self.assertTrue(created["token"].startswith("sr_live_"))
            token=created["token"]
            status,delivered=runtime.request("POST","/api/v2/integrations/import",{"id":"api-thread","title":"Delivered by API","messages":[
                {"id":"api-message-1","role":"user","content":"Preserve this externally delivered idea."}]},token=token)
            self.assertEqual(status,202); self.assertEqual(delivered["conversation_count"],1)
            status,listing=runtime.request("GET","/api/v2/integrations"); self.assertEqual(status,200)
            self.assertEqual(listing["integrations"][0]["delivery_count"],1); self.assertNotIn("token",listing["integrations"][0])
            status,_=runtime.request("POST",f"/api/v2/integrations/{created['id']}/revoke",{}); self.assertEqual(status,200)
            status,_=runtime.request("POST","/api/v2/integrations/import",{"messages":[{"role":"user","content":"blocked"}]},token=token)
            self.assertEqual(status,401)
        finally: runtime.close()

    def test_api_responses_include_baseline_security_headers(self):
        runtime=UnifiedRuntime("local")
        try:
            request=urllib.request.Request(f"http://127.0.0.1:{runtime.port}/api/v2/health")
            with urllib.request.urlopen(request,timeout=5) as response:
                self.assertEqual(response.headers.get("X-Content-Type-Options"),"nosniff")
                self.assertEqual(response.headers.get("X-Frame-Options"),"DENY")
                self.assertEqual(response.headers.get("Referrer-Policy"),"no-referrer")
                self.assertEqual(response.headers.get("Cache-Control"),"no-store")
                self.assertEqual(response.headers.get("Vary"),"Origin")
        finally: runtime.close()

    def test_unsafe_deployment_configuration_is_rejected_at_startup(self):
        env=os.environ.copy(); env.update({"SEED_REFLECTIONS_MODE":"hosted","SEED_REFLECTIONS_PORT":str(free_port()),
            "SEED_REFLECTIONS_DATA_DIR":tempfile.mkdtemp(),"PYTHONDONTWRITEBYTECODE":"1"}); env.pop("SEED_REFLECTIONS_PUBLIC_ORIGIN",None)
        result=subprocess.run([sys.executable,str(ROOT/"server.py")],cwd=ROOT,env=env,capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0); self.assertIn("PUBLIC_ORIGIN",result.stderr)
        env["SEED_REFLECTIONS_PUBLIC_ORIGIN"]="https://seed.example"; env["SEED_REFLECTIONS_AUTH_RATE_LIMIT"]="0"
        result=subprocess.run([sys.executable,str(ROOT/"server.py")],cwd=ROOT,env=env,capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0); self.assertIn("must be positive",result.stderr)

    def test_local_capabilities_come_from_active_runtime(self):
        runtime=UnifiedRuntime("local")
        try:
            status,data=runtime.request("GET","/api/v2/capabilities")
            self.assertEqual(status,200); self.assertEqual(data["runtime"],"unified")
            self.assertEqual(data["mode"],"local"); self.assertTrue(data["hosted_archive_ingestion"])
        finally: runtime.close()

    def test_hosted_archives_are_isolated_by_workspace(self):
        runtime=UnifiedRuntime("hosted")
        try:
            _,first=runtime.request("POST","/api/v2/auth/signup",{
                "name":"First Owner","email":"first@example.com","password":"strong-password-123"})
            _,second=runtime.request("POST","/api/v2/auth/signup",{
                "name":"Second Owner","email":"second@example.com","password":"strong-password-456"})
            archive=[{"id":"private-thread","title":"Private roadmap","messages":[
                {"id":"m1","role":"user","content":"We should build a private source-linked archive for our roadmap."},
                {"id":"m2","role":"assistant","content":"I can help organize that plan."}]}]
            status,imported=runtime.request("POST","/api/v2/imports",{
                "filename":"history.json","data":archive},token=first["access_token"])
            self.assertEqual(status,201); self.assertEqual(imported["conversations"],1)
            status,first_list=runtime.request("GET","/api/v2/conversations",token=first["access_token"])
            self.assertEqual(status,200); self.assertEqual(len(first_list["conversations"]),1)
            conversation_id=first_list["conversations"][0]["id"]
            status,second_list=runtime.request("GET","/api/v2/conversations",token=second["access_token"])
            self.assertEqual(status,200); self.assertEqual(second_list["conversations"],[])
            status,_=runtime.request("GET",f"/api/v2/conversations/{conversation_id}",token=second["access_token"])
            self.assertEqual(status,404)
            status,analysis=runtime.request("POST",f"/api/v2/conversations/{conversation_id}/analyze",{},token=first["access_token"])
            self.assertEqual(status,200); self.assertEqual(analysis["candidates_created"],1)
            _,first_candidates=runtime.request("GET","/api/v2/candidates",token=first["access_token"])
            _,second_candidates=runtime.request("GET","/api/v2/candidates",token=second["access_token"])
            self.assertEqual(len(first_candidates["candidates"]),1); self.assertEqual(second_candidates["candidates"],[])
            candidate_id=first_candidates["candidates"][0]["id"]
            status,_=runtime.request("POST",f"/api/v2/candidates/{candidate_id}/review",{"action":"accept"},token=second["access_token"])
            self.assertEqual(status,404)
            status,_=runtime.request("POST",f"/api/v2/candidates/{candidate_id}/review",{
                "action":"accept","project_id":"missing-project"},token=first["access_token"])
            self.assertEqual(status,400)
            _,still_pending=runtime.request("GET","/api/v2/candidates",token=first["access_token"])
            self.assertEqual([item["id"] for item in still_pending["candidates"]],[candidate_id])
            status,project=runtime.request("POST","/api/v2/projects",{"name":"Private Product","mission":"Turn recovered ideas into governed work."},token=first["access_token"])
            self.assertEqual(status,201)
            status,reviewed=runtime.request("POST",f"/api/v2/candidates/{candidate_id}/review",{
                "action":"accept","project_id":project["id"],"next_action":"Draft the archive map."},token=first["access_token"])
            self.assertEqual(status,200); self.assertEqual(reviewed["status"],"accepted"); self.assertTrue(reviewed["seed_id"])
            _,overview=runtime.request("GET","/api/v2/overview",token=first["access_token"])
            self.assertEqual(overview["seeds"],1); self.assertEqual(overview["projects"],1)
            _,recovery=runtime.request("GET","/api/v2/recovery",token=first["access_token"])
            self.assertEqual(len(recovery["recovery_candidates"]),1)
            seed_id=recovery["recovery_candidates"][0]["seed_id"]
            status,_=runtime.request("POST",f"/api/v2/seeds/{seed_id}/resume",{},token=second["access_token"])
            self.assertEqual(status,404)
            status,resumed=runtime.request("POST",f"/api/v2/seeds/{seed_id}/resume",{},token=first["access_token"])
            self.assertEqual(status,200); self.assertEqual(resumed["status"],"recovered")
            status,context=runtime.request("GET",f"/api/v2/projects/{project['id']}/context",token=first["access_token"])
            self.assertEqual(status,200); self.assertEqual(context["seed_count"],1); self.assertIn("Private Product",context["markdown"])
            status,_=runtime.request("GET",f"/api/v2/projects/{project['id']}/context",token=second["access_token"])
            self.assertEqual(status,404)
            status,_=runtime.request("GET","/api/v1/archive/conversations",token=first["access_token"])
            self.assertEqual(status,403)
        finally: runtime.close()

    def test_hosted_auth_and_tenant_overview_use_unified_database(self):
        runtime=UnifiedRuntime("hosted")
        try:
            status,_=runtime.request("GET","/api/v2/overview"); self.assertEqual(status,401)
            status,signup=runtime.request("POST","/api/v2/auth/signup",{
                "name":"Hosted Owner","email":"owner@example.com","password":"strong-password-123"})
            self.assertEqual(status,201); self.assertTrue(signup["access_token"])
            status,_=runtime.request("POST","/api/v2/auth/login",{"email":"owner@example.com","password":"wrong-password"})
            self.assertEqual(status,401)
            status,login=runtime.request("POST","/api/v2/auth/login",{
                "email":"owner@example.com","password":"strong-password-123"})
            self.assertEqual(status,200)
            status,overview=runtime.request("GET","/api/v2/overview",token=login["access_token"])
            self.assertEqual(status,200); self.assertEqual(overview["seeds"],0)
            status,_=runtime.request("POST","/api/v2/auth/logout",{},token=login["access_token"]); self.assertEqual(status,200)
            status,_=runtime.request("GET","/api/v2/overview",token=login["access_token"]); self.assertEqual(status,401)
        finally: runtime.close()

    def test_hosted_dashboard_workspace_actions_use_authenticated_v2_flow(self):
        runtime=UnifiedRuntime("hosted")
        try:
            _,owner=runtime.request("POST","/api/v2/auth/signup",{
                "name":"Workspace Owner","email":"workspace@example.com","password":"strong-password-123"})
            token=owner["access_token"]
            status,workspace=runtime.request("GET","/api/v2/workspace",token=token)
            self.assertEqual(status,200); self.assertEqual(workspace["seeds"],[])
            status,reflection=runtime.request("POST","/api/v2/reflections",{
                "transcript":"We should build a durable workspace that keeps every source conversation attached to its confirmed ideas."},token=token)
            self.assertEqual(status,201); self.assertGreaterEqual(reflection["candidates_created"],1)
            _,candidates=runtime.request("GET","/api/v2/candidates",token=token)
            self.assertGreaterEqual(len(candidates["candidates"]),1)
            status,project=runtime.request("POST","/api/v2/projects",{
                "name":"Continuity Workspace","mission":"Continue confirmed ideas with their source context."},token=token)
            self.assertEqual(status,201)
            candidate_id=candidates["candidates"][0]["id"]
            status,accepted=runtime.request("POST",f"/api/v2/candidates/{candidate_id}/review",{
                "action":"accept","project_id":project["id"],"next_action":"Draft the first source-linked workspace view."},token=token)
            self.assertEqual(status,200); self.assertTrue(accepted["seed_id"])
            status,lost=runtime.request("GET",f"/api/v2/analysis/lost-seeds?project_id={project['id']}",token=token)
            self.assertEqual(status,200); self.assertTrue(any(item["seed_id"]==accepted["seed_id"] for item in lost["lost_seeds"]))
            status,drift=runtime.request("GET",f"/api/v2/analysis/intent-drift?project_id={project['id']}",token=token)
            self.assertEqual(status,200); self.assertIn("mission_drift_index",drift)
            self.assertEqual(runtime.request("GET",f"/api/v2/analysis/lost-seeds?project_id={project['id']}")[0],401)
            status,chat=runtime.request("POST","/api/v2/chat",{
                "prompt":"What should I do next?","active_seed_id":accepted["seed_id"]},token=token)
            self.assertEqual(status,200); self.assertTrue(chat["grounded"])
            self.assertIn("Draft the first source-linked workspace view",chat["answer"])
            status,_=runtime.request("POST","/api/v2/chat",{"prompt":"What is here?"})
            self.assertEqual(status,401)
        finally: runtime.close()

    def test_hosted_secondary_workspace_controls_are_tenant_scoped(self):
        runtime=UnifiedRuntime("hosted")
        try:
            _,owner=runtime.request("POST","/api/v2/auth/signup",{"name":"Owner","email":"controls@example.com","password":"strong-password-123"})
            _,outsider=runtime.request("POST","/api/v2/auth/signup",{"name":"Other","email":"controls-other@example.com","password":"strong-password-456"})
            token=owner["access_token"]
            _,project=runtime.request("POST","/api/v2/projects",{"name":"Governed Work","mission":"Test workspace controls."},token=token)
            archive=[{"id":"controls","title":"Two ideas","messages":[
                {"role":"user","content":"We should preserve source evidence with every confirmed idea."},
                {"role":"user","content":"We should connect related confirmed ideas without losing their separate sources."}]}]
            runtime.request("POST","/api/v2/imports",{"data":archive},token=token)
            _,listing=runtime.request("GET","/api/v2/conversations",token=token); conversation_id=listing["conversations"][0]["id"]
            runtime.request("POST",f"/api/v2/conversations/{conversation_id}/analyze",{},token=token)
            _,candidates=runtime.request("GET","/api/v2/candidates",token=token)
            seed_ids=[]
            for candidate in candidates["candidates"]:
                _,accepted=runtime.request("POST",f"/api/v2/candidates/{candidate['id']}/review",{"action":"accept","project_id":project["id"]},token=token)
                seed_ids.append(accepted["seed_id"])
            self.assertGreaterEqual(len(seed_ids),2)
            status,_=runtime.request("POST","/api/v2/workspace/seeds/update",{"seed_id":seed_ids[0],"status":"completed"},token=token); self.assertEqual(status,200)
            status,_=runtime.request("POST","/api/v2/workspace/decisions",{"decision_statement":"Keep evidence attached.","project_id":project["id"]},token=token); self.assertEqual(status,201)
            status,_=runtime.request("POST","/api/v2/workspace/conflicts",{"subject":"Priority","seed_a":seed_ids[0],"seed_b":seed_ids[1],"project_id":project["id"]},token=token); self.assertEqual(status,201)
            status,_=runtime.request("POST","/api/v2/workspace/relationships/create",{"source_seed_id":seed_ids[0],"target_seed_id":seed_ids[1],"relationship_type":"Related","created_by":"user"},token=token); self.assertEqual(status,200)
            _,workspace=runtime.request("GET","/api/v2/workspace",token=token); relationship_id=workspace["relationships"][-1]["relationship_id"]
            self.assertEqual(runtime.request("POST","/api/v2/workspace/relationships/delete",{"relationship_id":relationship_id},token=outsider["access_token"])[0],404)
            status,package=runtime.request("GET",f"/api/v2/projects/{project['id']}/package",token=token); self.assertEqual(status,200)
            self.assertEqual(package["json_package"]["package_version"],"2.0.0")
            status,imported=runtime.request("POST","/api/v2/projects/import-package",{"json_package":package["json_package"]},token=outsider["access_token"])
            self.assertEqual(status,200); self.assertGreaterEqual(imported["imported"]["seeds"],2)
            self.assertEqual(runtime.request("GET",f"/api/v2/workspace/seeds/{seed_ids[0]}/export",token=outsider["access_token"])[0],200)
            self.assertEqual(runtime.request("POST","/api/v2/workspace/seeds/delete",{"seed_id":seed_ids[0]},token=token)[0],200)
        finally: runtime.close()

    def test_hosted_analysis_jobs_and_relationships_are_tenant_scoped(self):
        runtime=UnifiedRuntime("hosted")
        try:
            _,owner=runtime.request("POST","/api/v2/auth/signup",{"name":"Owner","email":"jobs@example.com","password":"strong-password-123"})
            _,outsider=runtime.request("POST","/api/v2/auth/signup",{"name":"Outsider","email":"outside@example.com","password":"strong-password-456"})
            archive=[
                {"id":"a","title":"Archive map","messages":[{"role":"user","content":"We should create a source-linked archive map for conversation history and project continuity."}]},
                {"id":"b","title":"Continue work","messages":[{"role":"user","content":"I want a source-linked archive map that preserves conversation history and project continuity."}]},
            ]
            status,_=runtime.request("POST","/api/v2/imports",{"filename":"history.json","data":archive},token=owner["access_token"])
            self.assertEqual(status,201)
            status,job=runtime.request("POST","/api/v2/analysis/run",{},token=owner["access_token"]); self.assertEqual(status,202)
            for _ in range(100):
                _,state=runtime.request("GET",f"/api/v2/analysis/jobs/{job['id']}",token=owner["access_token"])
                if state.get("status") in {"complete","failed"}: break
                time.sleep(.03)
            self.assertEqual(state["status"],"complete"); self.assertEqual(state["processed"],2)
            status,_=runtime.request("GET",f"/api/v2/analysis/jobs/{job['id']}",token=outsider["access_token"]); self.assertEqual(status,404)
            status,generated=runtime.request("POST","/api/v2/relationships/generate",{},token=owner["access_token"])
            self.assertEqual(status,200); self.assertEqual(generated["links_created"],1)
            _,links=runtime.request("GET","/api/v2/relationships",token=owner["access_token"])
            _,outside_links=runtime.request("GET","/api/v2/relationships",token=outsider["access_token"])
            self.assertEqual(len(links["links"]),1); self.assertEqual(outside_links["links"],[])
            link_id=links["links"][0]["id"]
            status,_=runtime.request("POST",f"/api/v2/relationships/{link_id}/review",{"action":"accept"},token=outsider["access_token"])
            self.assertEqual(status,404)
            status,reviewed=runtime.request("POST",f"/api/v2/relationships/{link_id}/review",{"action":"accept"},token=owner["access_token"])
            self.assertEqual(status,200); self.assertEqual(reviewed["status"],"accepted"); self.assertEqual(reviewed["relationships_created"],0)
            _,project=runtime.request("POST","/api/v2/projects",{"name":"Linked Work","mission":"Keep related ideas connected."},token=owner["access_token"])
            _,candidates=runtime.request("GET","/api/v2/candidates",token=owner["access_token"])
            materialized=0
            for candidate in candidates["candidates"]:
                status,result=runtime.request("POST",f"/api/v2/candidates/{candidate['id']}/review",{
                    "action":"accept","project_id":project["id"]},token=owner["access_token"])
                self.assertEqual(status,200); materialized += result["relationships_created"]
            self.assertEqual(materialized,1)
            _,context=runtime.request("GET",f"/api/v2/projects/{project['id']}/context",token=owner["access_token"])
            self.assertEqual(context["seed_count"],2)
        finally: runtime.close()

    def test_hosted_multipart_document_job_is_persistent_and_private(self):
        runtime=UnifiedRuntime("hosted")
        try:
            _,owner=runtime.request("POST","/api/v2/auth/signup",{"name":"Upload Owner","email":"upload@example.com","password":"strong-password-123"})
            _,outsider=runtime.request("POST","/api/v2/auth/signup",{"name":"Other Owner","email":"upload-other@example.com","password":"strong-password-456"})
            streamed=json.dumps({"conversations":[{"id":"streamed","title":"Planning notes","messages":[
                {"role":"user","content":"We should build a durable source-linked planning archive."},
                {"role":"assistant","content":"I can help map it."}]}]}).encode()
            status,accepted=runtime.upload("/api/v2/imports/upload","planning-notes.json",streamed,owner["access_token"])
            self.assertEqual(status,202)
            for _ in range(100):
                _,job=runtime.request("GET",f"/api/v2/imports/jobs/{accepted['job_id']}",token=owner["access_token"])
                if job.get("status") in {"complete","failed"}: break
                time.sleep(.03)
            self.assertEqual(job["status"],"complete"); self.assertEqual(job["result"]["conversations"],1); self.assertTrue(job["result"]["streamed"])
            status,_=runtime.request("GET",f"/api/v2/imports/jobs/{accepted['job_id']}",token=outsider["access_token"])
            self.assertEqual(status,404)
            _,owner_list=runtime.request("GET","/api/v2/conversations",token=owner["access_token"])
            _,outsider_list=runtime.request("GET","/api/v2/conversations",token=outsider["access_token"])
            self.assertEqual(len(owner_list["conversations"]),1); self.assertEqual(outsider_list["conversations"],[])
            _,sources=runtime.request("GET","/api/v2/sources",token=owner["access_token"])
            _,outside_sources=runtime.request("GET","/api/v2/sources",token=outsider["access_token"])
            self.assertEqual(len(sources["sources"]),1); self.assertEqual(outside_sources["sources"],[])
            source=sources["sources"][0]; self.assertEqual(source["sha256"],__import__("hashlib").sha256(streamed).hexdigest())
            self.assertEqual(source["coverage"]["status"],"complete"); self.assertEqual(source["byte_count"],len(streamed))
            status,_=runtime.request("GET",f"/api/v2/sources/{source['id']}",token=outsider["access_token"]); self.assertEqual(status,404)
            status,recovered=runtime.download(f"/api/v2/sources/{source['id']}/download",owner["access_token"])
            self.assertEqual(status,200); self.assertEqual(recovered,streamed)
            status,_=runtime.download(f"/api/v2/sources/{source['id']}/download",outsider["access_token"]); self.assertEqual(status,404)
            status,backup=runtime.request("GET","/api/v2/backup",token=owner["access_token"]); self.assertEqual(status,200)
            status,archive_bytes=runtime.download("/api/v2/backup/download",owner["access_token"]); self.assertEqual(status,200)
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                manifest=json.loads(archive.read("manifest.json")); self.assertEqual(manifest["payload"]["version"],2)
                self.assertTrue(any(name.startswith("sources/") for name in archive.namelist()))
            status,_=runtime.request("POST","/api/v2/restore",{"backup":backup},token=outsider["access_token"]); self.assertEqual(status,400)
            extra=[{"id":"extra","title":"Temporary","messages":[{"role":"user","content":"We should temporarily add another archive idea."}]}]
            self.assertEqual(runtime.request("POST","/api/v2/imports",{"data":extra},token=owner["access_token"])[0],201)
            self.assertEqual(len(runtime.request("GET","/api/v2/conversations",token=owner["access_token"])[1]["conversations"]),2)
            corrupt=json.loads(json.dumps(backup)); corrupt["payload"]["created_at"]="tampered"
            status,_=runtime.request("POST","/api/v2/restore",{"backup":corrupt},token=owner["access_token"]); self.assertEqual(status,400)
            self.assertEqual(len(runtime.request("GET","/api/v2/conversations",token=owner["access_token"])[1]["conversations"]),2)
            status,restored=runtime.upload("/api/v2/restore/upload","backup.zip",archive_bytes,owner["access_token"])
            self.assertEqual(status,200); self.assertEqual(restored["status"],"restored")
            self.assertEqual(len(runtime.request("GET","/api/v2/conversations",token=owner["access_token"])[1]["conversations"]),1)
            self.assertEqual(runtime.request("POST","/api/v2/imports",{"data":extra},token=owner["access_token"])[0],201)
            status,restored=runtime.request("POST","/api/v2/restore",{"backup":backup},token=owner["access_token"])
            self.assertEqual(status,200); self.assertEqual(restored["status"],"restored")
            self.assertEqual(len(runtime.request("GET","/api/v2/conversations",token=owner["access_token"])[1]["conversations"]),1)
            status,recovered=runtime.download(f"/api/v2/sources/{source['id']}/download",owner["access_token"])
            self.assertEqual(status,200); self.assertEqual(recovered,streamed)
        finally: runtime.close()

    def test_hosted_quotas_are_workspace_scoped_and_auth_is_throttled(self):
        runtime=UnifiedRuntime("hosted",{"SEED_REFLECTIONS_HOSTED_MAX_CONVERSATIONS":"1",
            "SEED_REFLECTIONS_HOSTED_MAX_ANALYSIS_JOBS":"1","SEED_REFLECTIONS_AUTH_RATE_LIMIT":"2",
            "SEED_REFLECTIONS_AUTH_RATE_WINDOW_SECONDS":"300"})
        try:
            _,first=runtime.request("POST","/api/v2/auth/signup",{"name":"Quota One","email":"quota1@example.com","password":"strong-password-123"})
            _,second=runtime.request("POST","/api/v2/auth/signup",{"name":"Quota Two","email":"quota2@example.com","password":"strong-password-456"})
            status,_=runtime.request("POST","/api/v2/auth/signup",{"name":"Blocked","email":"quota3@example.com","password":"strong-password-789"})
            self.assertEqual(status,429)
            one=[{"id":"one","title":"One","messages":[{"role":"user","content":"We should preserve this source-linked archive idea."}]}]
            two=[{"id":"two","title":"Two","messages":[{"role":"user","content":"We should preserve another source-linked archive idea."}]}]
            self.assertEqual(runtime.request("POST","/api/v2/imports",{"data":one},token=first["access_token"])[0],201)
            self.assertEqual(runtime.request("POST","/api/v2/imports",{"data":two},token=first["access_token"])[0],413)
            self.assertEqual(runtime.request("POST","/api/v2/imports",{"data":two},token=second["access_token"])[0],201)
            self.assertEqual(runtime.request("POST","/api/v2/analysis/run",{},token=first["access_token"])[0],202)
            self.assertEqual(runtime.request("POST","/api/v2/analysis/run",{},token=first["access_token"])[0],429)
            self.assertEqual(runtime.request("POST","/api/v2/analysis/run",{},token=second["access_token"])[0],202)
            self.assertEqual(runtime.request("POST","/api/v2/auth/login",{"email":"nobody@example.com","password":"wrong-password"})[0],401)
            self.assertEqual(runtime.request("POST","/api/v2/auth/login",{"email":"nobody@example.com","password":"wrong-password"})[0],401)
            self.assertEqual(runtime.request("POST","/api/v2/auth/login",{"email":"nobody@example.com","password":"wrong-password"})[0],429)
        finally: runtime.close()

if __name__=="__main__": unittest.main()
