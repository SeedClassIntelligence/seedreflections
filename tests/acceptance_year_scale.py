"""Non-destructive year-scale acceptance run against an isolated hosted runtime."""
import json, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_unified_runtime import UnifiedRuntime

CONVERSATIONS=2500
MESSAGES_PER_CONVERSATION=12

def build_archive():
    archive=[]
    for index in range(CONVERSATIONS):
        messages=[]
        for ordinal in range(MESSAGES_PER_CONVERSATION):
            role="user" if ordinal%2==0 else "assistant"
            content=(f"Conversation {index}, message {ordinal}. " +
                ("We should build a source-linked continuity workspace for this project and preserve the original evidence. " if role=="user" else
                 "The plan records the evidence, identifies the decision, and keeps the next action connected. ")+
                "This deliberately varied acceptance text validates complete history ingestion without relying on production data.")
            messages.append({"id":f"m-{index}-{ordinal}","role":role,"content":content,"create_time":1700000000+index*20+ordinal})
        archive.append({"id":f"conversation-{index}","title":f"Year-scale project conversation {index}","messages":messages,
                        "create_time":1700000000+index*20,"update_time":1700000012+index*20})
    return {"conversations":archive}

def require(condition,message):
    if not condition: raise AssertionError(message)

def main():
    runtime=UnifiedRuntime("hosted",{"SEED_REFLECTIONS_AUTH_RATE_LIMIT":"100"}); started=time.perf_counter()
    try:
        status,owner=runtime.request("POST","/api/v2/auth/signup",{"name":"Scale Owner","email":"scale@example.com","password":"strong-password-123"})
        require(status==201,"signup failed"); token=owner["access_token"]
        encoded=json.dumps(build_archive(),separators=(",",":")).encode(); upload_started=time.perf_counter()
        status,accepted=runtime.upload("/api/v2/imports/upload","chatgpt-year-export.json",encoded,token); require(status==202,"upload was not accepted")
        for _ in range(2400):
            _,job=runtime.request("GET",f"/api/v2/imports/jobs/{accepted['job_id']}",token=token)
            if job.get("status") in {"complete","failed"}: break
            time.sleep(.05)
        require(job.get("status")=="complete",f"import failed: {job}"); import_seconds=time.perf_counter()-upload_started
        result=job["result"]; expected_messages=CONVERSATIONS*MESSAGES_PER_CONVERSATION
        require(result["conversations"]==CONVERSATIONS,f"conversation loss: {result}")
        require(result["messages"]==expected_messages,f"message loss: {result}")
        status,overview=runtime.request("GET","/api/v2/overview",token=token); require(status==200,"overview failed")
        require(overview["conversations"]==CONVERSATIONS and overview["messages"]==expected_messages,f"overview mismatch: {overview}")
        listed=[]; offset=0
        while True:
            _,page=runtime.request("GET",f"/api/v2/conversations?limit=500&offset={offset}",token=token); listed.extend(page["conversations"])
            require(page["total"]==CONVERSATIONS,"pagination total mismatch")
            if not page["has_more"]: break
            offset+=len(page["conversations"])
        require(len(listed)==CONVERSATIONS and len({item['id'] for item in listed})==CONVERSATIONS,"paginated archive listing mismatch")
        first=listed[0]; _,detail=runtime.request("GET",f"/api/v2/conversations/{first['id']}",token=token)
        require(len(detail["messages"])==MESSAGES_PER_CONVERSATION,"conversation detail lost messages")
        status,analysis=runtime.request("POST",f"/api/v2/conversations/{first['id']}/analyze",{},token=token); require(status==200 and analysis["candidates_created"]>0,"analysis produced no reviewable idea")
        _,candidates=runtime.request("GET","/api/v2/candidates",token=token); candidate=candidates["candidates"][0]
        status,project=runtime.request("POST","/api/v2/projects",{"name":"Scale Continuity","mission":"Continue verified work from its source history."},token=token); require(status==201,"project creation failed")
        status,review=runtime.request("POST",f"/api/v2/candidates/{candidate['id']}/review",{"action":"accept","project_id":project["id"],"next_action":"Continue the verified plan."},token=token)
        require(status==200 and review.get("seed_id"),"candidate did not enter workspace")
        status,context=runtime.request("GET",f"/api/v2/projects/{project['id']}/context",token=token); require(status==200 and context["seed_count"]==1,"workspace context failed")
        status,backup=runtime.download("/api/v2/backup/download",token); require(status==200 and backup[:2]==b"PK","ZIP backup failed")
        status,_=runtime.request("POST","/api/v2/imports",{"data":[{"id":"post-backup","title":"Mutation","messages":[{"role":"user","content":"Temporary mutation after backup."}]}]},token=token); require(status==201,"post-backup mutation failed")
        status,restored=runtime.upload("/api/v2/restore/upload","complete-backup.zip",backup,token); require(status==200 and restored["status"]=="restored","ZIP restore failed")
        _,final_overview=runtime.request("GET","/api/v2/overview",token=token)
        require(final_overview["conversations"]==CONVERSATIONS and final_overview["messages"]==expected_messages,"restore did not return exact counts")
        print(json.dumps({"status":"passed","archive_bytes":len(encoded),"backup_bytes":len(backup),"conversations":CONVERSATIONS,
            "messages":expected_messages,"import_seconds":round(import_seconds,3),"total_seconds":round(time.perf_counter()-started,3),
            "source_coverage":result.get("coverage"),"final_overview":final_overview},indent=2))
    finally: runtime.close()

if __name__=="__main__": main()
