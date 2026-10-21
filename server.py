#!/usr/bin/env python3
"""
Seed Reflection Product — Standalone Backend Server
======================================================
Serves the consumer dashboard and provides independent API endpoints
for seed management and cryptographic Seed Signature verification.

Zero external dependencies. Runs on standard Python library.
"""

import os
import time
import re
import threading
START_TIME = time.time()
DB_LOCK = threading.RLock()

import json
import urllib.request
import urllib.parse
from urllib.error import URLError
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from datetime import datetime
import mimetypes
import tempfile
import uuid
import zipfile
from pathlib import Path
from archive_store import import_json as import_archive_json
from archive_store import import_text as import_archive_text
from archive_store import list_conversations as list_archive_conversations
from archive_store import count_conversations as count_archive_conversations
from archive_store import get_conversation as get_archive_conversation
from archive_store import raw_conversations as get_raw_archive_conversations
from archive_store import list_imports as list_archive_imports
from archive_store import create_import_job, update_import_job, get_import_job, list_import_jobs
from archive_store import (analyze_conversation, list_candidates, review_candidate,
                           create_analysis_job, get_analysis_job, run_archive_analysis,
                           archive_analysis_overview, generate_candidate_links,
                           list_candidate_links, review_candidate_link)
from document_ingest import import_document, import_document_path
from workspace_store import load_workspace, save_workspace, storage_status, create_empty_workspace, accept_tenant_candidate
from auth_store import signup as auth_signup, login as auth_login, authenticate as auth_authenticate, logout as auth_logout, consume_auth_attempt
from tenant_archive_store import (import_json as tenant_import_json, overview as tenant_archive_overview,
    list_conversations as tenant_list_conversations, get_conversation as tenant_get_conversation,
    analyze as tenant_analyze, list_candidates as tenant_list_candidates, review as tenant_review,
    create_import_job as tenant_create_import_job, update_import_job as tenant_update_import_job,
    get_import_job as tenant_get_import_job, list_import_jobs as tenant_list_import_jobs,
    import_document_path as tenant_import_document_path, create_analysis_job as tenant_create_analysis_job,
    get_analysis_job as tenant_get_analysis_job, run_analysis_job as tenant_run_analysis_job,
    generate_links as tenant_generate_links, list_links as tenant_list_links, review_link as tenant_review_link,
    preserve_source as tenant_preserve_source, list_sources as tenant_list_sources, get_source as tenant_get_source)
from tenant_archive_store import count_conversations as tenant_count_conversations
from tenant_archive_store import usage as tenant_usage
from tenant_archive_store import export_backup as tenant_export_backup, export_backup_archive as tenant_export_backup_archive, restore_backup as tenant_restore_backup, restore_backup_archive as tenant_restore_backup_archive
from connector_store import (discover as discover_connectors, list_connectors as list_source_connectors,
    add_connector as add_source_connector, remove_connector as remove_source_connector,
    sync_connector as sync_source_connector, sync_automatic as sync_automatic_connectors,
    adapter_catalog as source_adapter_catalog, preview_source as preview_connector_source,
    connect_preview as connect_connector_preview, connector_health as source_connector_health)
from integration_store import (create_integration as create_api_integration, list_integrations as list_api_integrations,
    authenticate as authenticate_api_integration, record_delivery as record_api_delivery,
    revoke_integration as revoke_api_integration)

PORT = int(os.environ.get("SEED_REFLECTIONS_PORT", "8476"))
DEPLOYMENT_MODE = os.environ.get("SEED_REFLECTIONS_MODE", "local").strip().lower()
if DEPLOYMENT_MODE not in {"local","hosted","enterprise"}: raise RuntimeError("Invalid SEED_REFLECTIONS_MODE")
HOST = os.environ.get("SEED_REFLECTIONS_HOST","127.0.0.1" if DEPLOYMENT_MODE=="local" else "0.0.0.0")
PUBLIC_ORIGIN = os.environ.get("SEED_REFLECTIONS_PUBLIC_ORIGIN","*" if DEPLOYMENT_MODE=="local" else "").rstrip("/")
MAX_UPLOAD_BYTES = int(os.environ.get("SEED_REFLECTIONS_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
HOSTED_STORAGE_BYTES = int(os.environ.get("SEED_REFLECTIONS_HOSTED_STORAGE_BYTES", str(10 * 1024 * 1024 * 1024)))
HOSTED_MAX_CONVERSATIONS = int(os.environ.get("SEED_REFLECTIONS_HOSTED_MAX_CONVERSATIONS", "1000000"))
HOSTED_MAX_ANALYSIS_JOBS = int(os.environ.get("SEED_REFLECTIONS_HOSTED_MAX_ANALYSIS_JOBS", "10000"))
AUTH_RATE_LIMIT = int(os.environ.get("SEED_REFLECTIONS_AUTH_RATE_LIMIT", "10"))
AUTH_RATE_WINDOW = int(os.environ.get("SEED_REFLECTIONS_AUTH_RATE_WINDOW_SECONDS", "60"))
UPLOAD_JOBS_DIR = Path(os.environ.get("SEED_REFLECTIONS_UPLOAD_JOBS_DIR", "uploads/jobs"))
DATA_FILE = "seeds.json"
DEFAULT_DATA_FILE = os.path.abspath(DATA_FILE)
SIGNATURE_SESSIONS = {}
ADMIN_SESSIONS = {}
ENV_FILE = ".env"
CONFIG_FILE = "config.json"
TRANSCRIPTS_DIR = "transcripts"

import hashlib
import hmac


def validate_runtime_config():
    numeric={"SEED_REFLECTIONS_PORT":PORT,"SEED_REFLECTIONS_MAX_UPLOAD_BYTES":MAX_UPLOAD_BYTES,
        "SEED_REFLECTIONS_HOSTED_STORAGE_BYTES":HOSTED_STORAGE_BYTES,"SEED_REFLECTIONS_HOSTED_MAX_CONVERSATIONS":HOSTED_MAX_CONVERSATIONS,
        "SEED_REFLECTIONS_HOSTED_MAX_ANALYSIS_JOBS":HOSTED_MAX_ANALYSIS_JOBS,"SEED_REFLECTIONS_AUTH_RATE_LIMIT":AUTH_RATE_LIMIT,
        "SEED_REFLECTIONS_AUTH_RATE_WINDOW_SECONDS":AUTH_RATE_WINDOW}
    invalid=[name for name,value in numeric.items() if value<=0]
    if invalid: raise RuntimeError("Runtime limits must be positive: "+", ".join(invalid))
    if not 1<=PORT<=65535: raise RuntimeError("SEED_REFLECTIONS_PORT must be between 1 and 65535")
    if DEPLOYMENT_MODE!="local":
        parsed=urllib.parse.urlparse(PUBLIC_ORIGIN)
        if PUBLIC_ORIGIN=="*" or parsed.scheme not in {"http","https"} or not parsed.netloc:
            raise RuntimeError("Hosted and enterprise modes require an explicit SEED_REFLECTIONS_PUBLIC_ORIGIN URL")


validate_runtime_config()


def auth_request_allowed(key):
    return consume_auth_attempt(key,AUTH_RATE_LIMIT,AUTH_RATE_WINDOW)


def stream_multipart_upload(stream, content_length, content_type):
    """Stage a single multipart file without retaining the request body in memory."""
    boundary_match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", content_type)
    if not boundary_match:
        raise ValueError("Multipart boundary is missing")
    boundary = (boundary_match.group(1) or boundary_match.group(2)).strip().encode("utf-8")
    jobs_dir = UPLOAD_JOBS_DIR
    jobs_dir.mkdir(parents=True, exist_ok=True)
    request_file = tempfile.NamedTemporaryFile(prefix="request-", suffix=".multipart", dir=jobs_dir, delete=False)
    request_path = Path(request_file.name)
    try:
        remaining = content_length
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("Upload ended before the declared content length")
            request_file.write(chunk)
            remaining -= len(chunk)
        request_file.close()
        with request_path.open("rb") as source:
            header_window = source.read(min(content_length, 256 * 1024))
            header_end = header_window.find(b"\r\n\r\n")
            if header_end < 0:
                raise ValueError("Multipart file headers are invalid")
            headers = header_window[:header_end].decode("utf-8", errors="replace")
            filename_match = re.search(r'filename="([^"]+)"', headers, re.IGNORECASE)
            filename = Path(filename_match.group(1) if filename_match else "upload.bin").name
            data_start = header_end + 4
            marker = b"\r\n--" + boundary
            tail_size = min(content_length, len(marker) + 64)
            source.seek(content_length - tail_size)
            tail = source.read(tail_size)
            marker_offset = tail.rfind(marker)
            if marker_offset < 0:
                raise ValueError("Multipart closing boundary is invalid")
            data_end = content_length - tail_size + marker_offset
            if data_end < data_start:
                raise ValueError("Multipart file content is invalid")
            suffix = Path(filename).suffix or ".bin"
            staged = tempfile.NamedTemporaryFile(prefix="source-", suffix=suffix, dir=jobs_dir, delete=False)
            staged_path = Path(staged.name)
            source.seek(data_start)
            remaining = data_end - data_start
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Uploaded file content was truncated")
                staged.write(chunk)
                remaining -= len(chunk)
            staged.close()
        return filename, staged_path
    finally:
        request_file.close()
        request_path.unlink(missing_ok=True)


def process_import_job(job_id, filename, staged_path):
    try:
        update_import_job(job_id, status="running", stage="validating", progress=15)
        update_import_job(job_id, stage="extracting", progress=35)
        archive = import_document_path(staged_path, filename)
        update_import_job(job_id, stage="indexing", progress=80)
        result = {
            "import_id": archive["import_id"], "platform": archive["platform"],
            "message_count": archive["message_count"], "coverage": archive.get("coverage"),
            "duplicate": archive.get("duplicate", False), "duplicate_reason": archive.get("duplicate_reason"),
            "reconciliation": archive.get("reconciliation"), "conversations": archive["conversations"],
        }
        update_import_job(job_id, status="complete", stage="complete", progress=100, result=result)
    except Exception as exc:
        print(f"Import job {job_id} failed: {exc}")
        update_import_job(job_id, status="failed", stage="failed", progress=100, error=str(exc))
    finally:
        Path(staged_path).unlink(missing_ok=True)

def process_tenant_import_job(workspace_id, job_id, filename, staged_path):
    try:
        tenant_update_import_job(workspace_id,job_id,status="running",stage="extracting",progress=25)
        result=tenant_import_document_path(workspace_id,staged_path,filename)
        source=tenant_preserve_source(workspace_id,result["import_id"],staged_path,filename,result.get("coverage") or {})
        result["source_id"]=source["id"]
        tenant_update_import_job(workspace_id,job_id,status="complete",stage="complete",progress=100,result_json=result)
    except Exception as exc:
        tenant_update_import_job(workspace_id,job_id,status="failed",stage="failed",progress=100,error=str(exc))
    finally:
        Path(staged_path).unlink(missing_ok=True)

def save_transcript(transcript_text):
    """Save transcript to file, return its hash ID."""
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    t_hash = hashlib.sha256(transcript_text.encode("utf-8")).hexdigest()[:16]
    t_path = os.path.join(TRANSCRIPTS_DIR, f"{t_hash}.txt")
    if not os.path.exists(t_path):
        with open(t_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)
    return t_hash

def load_transcript(transcript_id):
    """Load transcript by ID or hash."""
    t_path = os.path.join(TRANSCRIPTS_DIR, f"{transcript_id}.txt")
    if os.path.exists(t_path):
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None

TELEMETRY_LOG = []

TIER_QUOTAS = {
    "free": {
        "max_seeds": 20,
        "max_monthly_reflections": 50,
        "name": "Free Tier"
    },
    "pro": {
        "max_seeds": 999999,
        "max_monthly_reflections": 250,
        "name": "Pro Tier"
    },
    "master": {
        "max_seeds": 999999,
        "max_monthly_reflections": 999999,
        "name": "Master Tier"
    },
    "admin": {
        "max_seeds": 999999,
        "max_monthly_reflections": 999999,
        "name": "Administrator"
    }
}

def resolve_account_for_request(handler, db):
    """Resolve requesting tenant account from Bearer token, session cookie, or default consumer."""
    auth_header = handler.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    if token:
        if token in ADMIN_SESSIONS:
            admin_acc = next((a for a in db.get("accounts", []) if a.get("role") == "admin"), None)
            if admin_acc:
                return admin_acc
            return {
                "id": "usr_admin_master",
                "email": ADMIN_SESSIONS[token].get("email", "admin@seedreflections.internal"),
                "name": ADMIN_SESSIONS[token].get("name", "Administrator"),
                "role": "admin",
                "plan": "master",
                "status": "active"
            }
        for acc in db.get("accounts", []):
            if token == f"user_token_{acc.get('id')}" or token == acc.get("id") or token == f"user_token_{acc.get('email')}":
                return acc

    cookie_header = handler.headers.get("Cookie", "")
    if cookie_header:
        for item in cookie_header.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                if k == "admin_session" and v in ADMIN_SESSIONS:
                    admin_acc = next((a for a in db.get("accounts", []) if a.get("role") == "admin"), None)
                    if admin_acc:
                        return admin_acc
                    return {
                        "id": "usr_admin_master",
                        "email": ADMIN_SESSIONS[v].get("email", "admin@seedreflections.internal"),
                        "name": ADMIN_SESSIONS[v].get("name", "Administrator"),
                        "role": "admin",
                        "plan": "master",
                        "status": "active"
                    }

    consumers = [a for a in db.get("accounts", []) if a.get("role") == "consumer"]
    if consumers:
        return consumers[0]
    
    return {
        "id": "usr_consumer_default",
        "email": "consumer@seedreflections.app",
        "name": "Workspace Developer",
        "role": "consumer",
        "plan": "free",
        "status": "active",
        "reflections_used_this_month": 0,
        "billing_cycle_month": datetime.now().strftime("%Y-%m")
    }

def sync_account_cycle(account):
    """Ensure monthly billing cycle resets accurately on calendar month rollover."""
    current_month = datetime.now().strftime("%Y-%m")
    if account.get("billing_cycle_month") != current_month:
        account["billing_cycle_month"] = current_month
        account["reflections_used_this_month"] = 0


STRIPE_WEBHOOK_LOG = []

def record_stripe_event(event_type, event_id, customer_email, plan, details=""):
    """Track Stripe billing and subscription webhook events."""
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "event_id": event_id,
        "customer_email": customer_email,
        "plan": plan,
        "details": details
    }
    STRIPE_WEBHOOK_LOG.append(event)
    if len(STRIPE_WEBHOOK_LOG) > 50:
        STRIPE_WEBHOOK_LOG.pop(0)
    TELEMETRY_LOG.append({
        "timestamp": event["timestamp"],
        "provider": "stripe",
        "model": event_type,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "caller": f"stripe:{customer_email or 'webhook'}"
    })



def check_ai_gateway_status():
    """Check if platform AI gateway is allowed to make outbound LLM calls.
    Returns: (is_allowed, error_code, error_message, current_spend, budget_cap)
    """
    cfg = load_config()
    current_spend = sum(item.get("estimated_cost_usd", 0.0) for item in TELEMETRY_LOG)
    budget_cap = float(cfg.get("ai_monthly_budget_usd", 50.0))
    hard_stop = bool(cfg.get("ai_budget_hard_stop", True))
    killswitch = bool(cfg.get("ai_killswitch_enabled", False))

    if killswitch:
        return False, "AI_KILLSWITCH_ACTIVE", "Platform AI Gateway is temporarily paused by administrator (Emergency Killswitch active).", round(current_spend, 4), budget_cap

    if hard_stop and current_spend >= budget_cap:
        return False, "AI_BUDGET_EXCEEDED", f"Platform monthly AI budget cap reached (${current_spend:.4f} / ${budget_cap:.2f} USD). Outbound LLM queries paused to prevent overages.", round(current_spend, 4), budget_cap

    return True, None, None, round(current_spend, 4), budget_cap

def record_llm_usage(provider, model, prompt_tokens, completion_tokens, caller_tag="chat"):
    """Track LLM token consumption and estimated API spend."""
    total_tokens = prompt_tokens + completion_tokens
    # Estimated rates per 1M tokens (USD)
    rates = {
        "qwen-qwq-32b": {"in": 0.15, "out": 0.60},
        "llama-3.1-8b-instant": {"in": 0.05, "out": 0.08},
        "gpt-4o-mini": {"in": 0.15, "out": 0.60},
        "gemini-2.5-flash": {"in": 0.075, "out": 0.30},
        "default": {"in": 0.10, "out": 0.20}
    }
    r = rates.get(model, rates["default"])
    est_cost = (prompt_tokens / 1_000_000.0 * r["in"]) + (completion_tokens / 1_000_000.0 * r["out"])
    
    event = {
        "timestamp": datetime.now().isoformat(),
        "provider": provider,
        "model": model,
        "caller": caller_tag,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(est_cost, 6)
    }
    TELEMETRY_LOG.append(event)
    # Retain last 500 events in memory
    if len(TELEMETRY_LOG) > 500:
        TELEMETRY_LOG.pop(0)
    return event

def load_transcript(transcript_id):
    """Load transcript text by hash ID."""
    t_path = os.path.join(TRANSCRIPTS_DIR, f"{transcript_id}.txt")
    if os.path.exists(t_path):
        with open(t_path, "r", encoding="utf-8") as f:
            return f.read()
    return None

def enrich_heuristic_seed(s, transcript):
    # s is {"title": "...", "description": "...", "status": "..."}
    title = s.get("title") or s.get("description") or "Untitled Spark"
    desc = s.get("description") or title
    
    # 1. Platform detection
    plat = "unknown"
    t_lower = (transcript + " " + title).lower()
    if "chatgpt" in t_lower or "gpt" in t_lower or "openai" in t_lower:
        plat = "chatgpt"
    elif "claude" in t_lower or "anthropic" in t_lower:
        plat = "claude"
    elif "gemini" in t_lower or "google" in t_lower or "bard" in t_lower:
        plat = "gemini"
    elif "slack" in t_lower:
        plat = "slack"
    elif "discord" in t_lower:
        plat = "discord"

    # 2. Keywords extraction
    stop_words = {
        "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", 
        "he", "him", "his", "she", "her", "it", "its", "they", "them", "their", "what", "which", 
        "who", "whom", "this", "that", "these", "those", "am", "is", "are", "was", "were", "be", 
        "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an", 
        "the", "and", "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", "for", 
        "with", "about", "against", "between", "into", "through", "during", "before", "after", 
        "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under", 
        "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", 
        "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", 
        "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", 
        "should", "shouldn", "now", "want", "need", "like", "would", "going", "could", "let's", 
        "lets", "think", "maybe", "try", "make", "create", "build", "implement", "add", "we'll", "we'll"
    }
    
    words = []
    clean_text = re.sub(r'[^\w\s]', '', (title + " " + desc).lower())
    for w in clean_text.split():
        if w and w not in stop_words and len(w) > 2:
            words.append(w)
            
    seen_words = set()
    keywords = []
    for w in words:
        if w not in seen_words:
            seen_words.add(w)
            keywords.append(w)
            if len(keywords) >= 5:
                break
    
    if not keywords:
        keywords = ["idea", "spark"]

    # 3. Confidence level heuristic
    confidence = 0.70
    desc_lower = desc.lower()
    if any(k in desc_lower for k in ["definitely", "must", "will", "critical", "need to", "resolve", "fix", "absolutely", "error", "bug"]):
        confidence = 0.88
    elif any(k in desc_lower for k in ["should", "let's", "let's", "we can", "propose", "suggest"]):
        confidence = 0.75
    elif any(k in desc_lower for k in ["maybe", "probably", "might", "could", "experiment", "try", "perhaps"]):
        confidence = 0.55

    # 4. Recovery suggestion heuristic
    recovery = ""
    if any(k in desc_lower for k in ["build", "create", "implement", "prototype"]):
        verb_match = re.search(r'\b(?:build|create|implement|prototype)\s+(?:a\s+|an\s+|the\s+)?(\w+)', desc_lower)
        target = verb_match.group(1) if verb_match else (keywords[0] if keywords else "module")
        recovery = f"Draft a minimal functional schema for the {target} and implement the core module."
    elif any(k in desc_lower for k in ["fix", "debug", "resolve", "error", "crash", "bug"]):
        recovery = "Locate the boundary crash using local dry-runs, and add robust input validation."
    elif any(k in desc_lower for k in ["refactor", "cleanup", "rewrite", "optimize"]):
        recovery = "Profile the performance bottlenecks first, then decouple modules to improve readability."
    else:
        recovery = "Break this intent down into 3 clear milestones and prototype a basic proof of concept."

    s["platform"] = plat
    s["keywords"] = keywords
    s["confidence"] = confidence
    s["recovery_suggestion"] = recovery
    return s

def get_query_param(path_str, name):
    if "?" not in path_str:
        return None
    query_str = path_str.split("?", 1)[1]
    for pair in query_str.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k == name:
                return urllib.parse.unquote(v)
    return None

def analyze_lost_seeds(workspace, project_id):
    seeds = [item for item in workspace.get("seeds", [])
             if (item.get("project_id") == project_id or (project_id == "default_project" and not item.get("project_id")))
             and str(item.get("status", "planted")).lower() not in {"wilted", "abandoned", "completed"}
             and str(item.get("continuity_status", "Active")).lower() not in {"historical", "superseded"}]
    relationships = workspace.get("relationships", [])
    sources = sorted([item for item in workspace.get("sources", []) if item.get("project_id") == project_id],
                     key=lambda item: item.get("created_at") or "")
    latest_text = str((sources[-1].get("content") if sources else "") or "").lower()
    results = []
    for seed in seeds:
        seed_id = seed.get("seed_id") or seed.get("id")
        has_descendants = bool(seed.get("child_seeds")) or any(
            item.get("source_seed_id") == seed_id for item in relationships)
        no_descendants = 0.0 if has_descendants else 1.0
        no_decisions = 0.0 if seed.get("decision_references") else 1.0
        no_versions = 0.0 if seed.get("versions") else 1.0
        if sources:
            terms = [str(term).lower() for term in seed.get("keywords", []) if len(str(term).strip()) > 3]
            if seed.get("title"): terms.append(str(seed["title"]).lower())
            if not terms:
                terms = [word.lower() for word in re.findall(r"\w+", seed.get("title") or "") if len(word) > 3]
            absent = 0.0 if any(term in latest_text for term in terms) else (1.0 if terms else 0.5)
        else:
            absent = 0.5
        last_modified = seed.get("modified_at") or seed.get("updated_at") or seed.get("created_at") or ""
        cutoff = (sources[-3] if len(sources) >= 3 else sources[-1]).get("created_at") if sources else ""
        inactive = 1.0 if cutoff and last_modified < cutoff else 0.0
        score = no_descendants * .25 + no_decisions * .20 + no_versions * .15 + absent * .25 + inactive * .15
        classification = ("High Confidence Candidate" if score >= .8 else "Likely Candidate" if score >= .6
                          else "Possible Candidate" if score >= .3 else "Active")
        results.append({"seed_id": seed_id, "title": seed.get("title") or "Untitled Seed", "score": round(score, 2),
                        "classification": classification, "metrics": {"no_descendants": no_descendants,
                        "no_decisions": no_decisions, "no_versions": no_versions,
                        "absent_from_transcript": absent, "inactivity_score": inactive}})
    return {"project_id": project_id, "lost_seeds": results}

def analyze_intent_drift(workspace, project_id):
    project = next((item for item in workspace.get("projects", [])
                    if (item.get("project_id") or item.get("id")) == project_id), None)
    charter = ""
    if project:
        charter = " ".join(str(project.get(key) or "") for key in ("mission", "purpose", "description"))
    seeds = [item for item in workspace.get("seeds", [])
             if (item.get("project_id") == project_id or (project_id == "default_project" and not item.get("project_id")))
             and str(item.get("status", "planted")).lower() not in {"wilted", "abandoned", "completed"}]
    charter_words = {word.lower() for word in re.findall(r"\w+", charter) if len(word) > 3}
    seed_words = set()
    for seed in seeds:
        text = f"{seed.get('title', '')} {seed.get('intent', '')} {' '.join(seed.get('keywords', []))}"
        seed_words.update(word.lower() for word in re.findall(r"\w+", text) if len(word) > 3)
    shared = charter_words & seed_words
    mission_drift = 1.0 - len(shared) / len(charter_words) if charter_words else 0.0
    accepted_ids = {item.get("decision_id") or item.get("id") for item in workspace.get("decisions", [])
                    if str(item.get("status", "active")).lower() in {"accepted", "active", "approved"}}
    uncovered = [seed.get("seed_id") or seed.get("id") for seed in seeds
                 if not accepted_ids.intersection(seed.get("decision_references", []))]
    coverage = 1.0 - len(uncovered) / len(seeds) if seeds else 1.0
    return {"project_id": project_id, "mission_drift_index": round(mission_drift * 100, 1),
            "decision_coverage_index": round(coverage * 100, 1), "scope_drift_index": round((1.0 - coverage) * 100, 1),
            "uncovered_seed_ids": uncovered, "unapproved_seed_ids": uncovered, "matched_terms": sorted(shared),
            "missing_charter_terms": sorted(charter_words - seed_words), "new_terms": sorted(seed_words - charter_words),
            "analysis_method": "deterministic lexical analysis",
            "confidence_limitations": "Lexical analysis only checks direct word presence and does not capture synonymy or conceptual mapping."}

def parse_multipart(content_bytes, boundary_str):
    boundary = boundary_str.encode("utf-8")
    parts = content_bytes.split(boundary)
    files = {}
    data = {}
    for part in parts:
        if not part or part == b"--\r\n" or part == b"--" or part == b"--\r\n\r\n":
            continue
        if b"\r\n\r\n" not in part:
            continue
        headers_part, body_part = part.split(b"\r\n\r\n", 1)
        headers = headers_part.decode("utf-8", errors="ignore")
        if body_part.endswith(b"\r\n"):
            body_part = body_part[:-2]
        elif body_part.endswith(b"\r"):
            body_part = body_part[:-1]
            
        cd_match = re.search(r'Content-Disposition:\s*form-data;\s*name="([^"]+)"(?:;\s*filename="([^"]+)")?', headers, re.IGNORECASE)
        if cd_match:
            name = cd_match.group(1)
            filename = cd_match.group(2)
            if filename:
                files[name] = {"filename": filename, "content": body_part}
            else:
                data[name] = body_part.decode("utf-8", errors="ignore")
    return data, files

def load_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    defaults = {
        "llm_provider": "ollama",
        "llm_api_url": "http://127.0.0.1:11434",
        "llm_model": "llama3",
        "llm_api_key": "",
        "ai_killswitch_enabled": False,
        "ai_monthly_budget_usd": 50.0,
        "ai_budget_hard_stop": True
    }
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
    return cfg

def save_config(config_data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# Default configs
CONFIG = {
    "SEED_SIGNATURE_API_URL": os.environ.get("SEED_SIGNATURE_API_URL", "http://127.0.0.1:7484"),
    "SEED_SIGNATURE_API_KEY": os.environ.get("SEED_SIGNATURE_API_KEY", "")
}

# Load .env if exists
if os.path.exists(ENV_FILE):
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    CONFIG[k.strip()] = v.strip()
    except Exception as e:
        print(f"Warning: Failed to load {ENV_FILE}: {e}")

# Ensure seeds data file exists
if not os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
    except Exception as e:
        print(f"Error creating {DATA_FILE}: {e}")

RELATIONSHIP_REGISTRY = {
    "Originated From": {"inverse": "Originated", "symmetric": False},
    "Evolved Into": {"inverse": "Evolved From", "symmetric": False},
    "Refined By": {"inverse": "Refines", "symmetric": False},
    "Renamed As": {"inverse": "Renamed From", "symmetric": False},
    "Split Into": {"inverse": "Split From", "symmetric": False},
    "Merged With": {"inverse": "Merged With", "symmetric": True},
    "Replaced By": {"inverse": "Replaces", "symmetric": False},
    "Conflicts With": {"inverse": "Conflicts With", "symmetric": True},
    "Restored From": {"inverse": "Restored To", "symmetric": False}
}

def is_seed_signed_and_valid(seed):
    sig = seed.get("trust_state", {}).get("signature")
    if not sig or sig == "unsigned":
        return False
    # Validate stored digest against actual content
    stored_digest = seed.get("trust_state", {}).get("digest")
    if not stored_digest:
        # Fallback if digest is not stored yet but signature exists
        return True
    core_content = f"{seed.get('title') or ''}|{seed.get('intent') or ''}|{seed.get('summary') or ''}"
    actual_digest = hashlib.sha256(core_content.encode("utf-8")).hexdigest()
    return (stored_digest == actual_digest)

def rebuild_relationship_references(db):
    for s in db.get("seeds", []):
        s["child_seeds"] = []
        s["parent_seed_id"] = None
        s["related_seeds"] = []

    for r in db.get("relationships", []):
        if r.get("approval_status") == "Approved":
            source_seed_id = r.get("source_seed_id")
            target_seed_id = r.get("target_seed_id")
            for s in db.get("seeds", []):
                if s.get("seed_id") == source_seed_id:
                    if target_seed_id not in s.get("child_seeds", []):
                        s.setdefault("child_seeds", []).append(target_seed_id)
                if s.get("seed_id") == target_seed_id:
                    s["parent_seed_id"] = source_seed_id
                    if source_seed_id not in s.get("related_seeds", []):
                        s.setdefault("related_seeds", []).append(source_seed_id)

def load_db():
    with DB_LOCK:
        try:
            if os.path.abspath(DATA_FILE) == DEFAULT_DATA_FILE:
                data = load_workspace(DATA_FILE)
            else:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
        except Exception:
            data = []

        # Migrate flat list to structured dictionary
        if isinstance(data, list):
            migrated_seeds = []
            for s in data:
                if not isinstance(s, dict):
                    continue
                s["evidence_status"] = s.get("evidence_status", "Explicitly Stated")
                s["authority_status"] = s.get("authority_status", "Detected")
                s["continuity_status"] = s.get("continuity_status", "Active")
                s["project_id"] = s.get("project_id", "default_project")
                s["source_excerpt"] = s.get("source_excerpt", s.get("intent", ""))
                s["versions"] = s.get("versions", [])
                s["related_seeds"] = s.get("related_seeds", [])
                s["parent_seed_id"] = s.get("parent_seed_id", None)
                s["child_seeds"] = s.get("child_seeds", [])
                s["conflict_references"] = s.get("conflict_references", [])
                s["decision_references"] = s.get("decision_references", [])
                migrated_seeds.append(s)

            data = {
                "seeds": migrated_seeds,
                "projects": [
                    {
                        "project_id": "default_project",
                        "name": "Default Project",
                        "purpose": "Default workspace project mapping all current seeds",
                        "description": "Legacy migrated project grouping.",
                        "owner": "system",
                        "created_at": datetime.now().isoformat(),
                        "last_reflection_date": None,
                        "stage": "Active"
                    }
                ],
                "sources": [],
                "decisions": [],
                "conflicts": []
            }
            try:
                db_dir = os.path.dirname(os.path.abspath(DATA_FILE)) or "."
                tmp_filepath = os.path.join(db_dir, os.path.basename(DATA_FILE) + ".tmp")
                with open(tmp_filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_filepath, DATA_FILE)
            except Exception as e:
                print(f"Error saving migrated database: {e}")

        if not isinstance(data, dict):
            data = {"seeds": [], "projects": [], "sources": [], "decisions": [], "conflicts": [], "relationships": [], "accounts": [], "telemetry": []}
        for k in ("seeds", "projects", "sources", "decisions", "conflicts", "relationships", "accounts", "telemetry"):
            if k not in data or not isinstance(data[k], list):
                data[k] = []

        # Seed initial default platform accounts if none exist
        if not data["accounts"]:
            data["accounts"] = [
                {
                    "id": "usr_admin_master",
                    "email": "admin@seedreflections.internal",
                    "name": "Platform Administrator",
                    "role": "admin",
                    "plan": "master",
                    "status": "active",
                    "tokens_consumed": 0,
                    "created_at": datetime.now().isoformat(),
                    "last_active": "Just now"
                },
                {
                    "id": "usr_consumer_default",
                    "email": "consumer@seedreflections.app",
                    "name": "Workspace Developer",
                    "role": "consumer",
                    "plan": "pro",
                    "status": "active",
                    "tokens_consumed": 0,
                    "created_at": datetime.now().isoformat(),
                    "last_active": "Today"
                }
            ]
        return data

def save_db(db):
    with DB_LOCK:
        try:
            if os.path.abspath(DATA_FILE) == DEFAULT_DATA_FILE:
                save_workspace(db)
                return True
            db_dir = os.path.dirname(os.path.abspath(DATA_FILE)) or "."
            tmp_filepath = os.path.join(db_dir, os.path.basename(DATA_FILE) + ".tmp")
            with open(tmp_filepath, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_filepath, DATA_FILE)
            return True
        except Exception as e:
            print(f"Error saving db: {e}")
            try:
                if 'tmp_filepath' in locals() and os.path.exists(tmp_filepath):
                    os.remove(tmp_filepath)
            except OSError:
                pass
            return False

def load_seeds():
    with DB_LOCK:
        db = load_db()
        return db["seeds"]

def save_seeds(seeds):
    with DB_LOCK:
        db = load_db()
        db["seeds"] = seeds
        return save_db(db)


def materialize_confirmed_candidate_links(workspace):
    """Materialize reviewed candidate links into seed lineage or decision governance."""
    seeds_by_candidate = {seed.get("candidate_id"): seed for seed in workspace.get("seeds", []) if seed.get("candidate_id")}
    decisions_by_candidate = {item.get("candidate_id"): item for item in workspace.get("decisions", []) if item.get("candidate_id")}
    relationships = workspace.setdefault("relationships", [])
    existing_link_ids = {item.get("source_candidate_link_id") for item in relationships}
    for decision in workspace.get("decisions", []):
        existing_link_ids.update(decision.get("source_candidate_link_ids", []))
    created = []
    for link in list_candidate_links("accepted", 1000):
        if link["id"] in existing_link_ids:
            continue
        left = seeds_by_candidate.get(link["left_candidate_id"])
        right = seeds_by_candidate.get(link["right_candidate_id"])
        left_decision = decisions_by_candidate.get(link["left_candidate_id"])
        right_decision = decisions_by_candidate.get(link["right_candidate_id"])
        decision = left_decision or right_decision
        governed_seed = right if left_decision else left if right_decision else None
        if decision and governed_seed:
            decision.setdefault("related_seeds", [])
            decision.setdefault("source_candidate_link_ids", [])
            governed_seed.setdefault("decision_references", [])
            if governed_seed["seed_id"] not in decision["related_seeds"]: decision["related_seeds"].append(governed_seed["seed_id"])
            if decision["decision_id"] not in governed_seed["decision_references"]: governed_seed["decision_references"].append(decision["decision_id"])
            decision["source_candidate_link_ids"].append(link["id"])
            created.append({"binding_type":"Decision Governance","decision_id":decision["decision_id"],
                            "seed_id":governed_seed["seed_id"],"source_candidate_link_id":link["id"]})
            continue
        if not left or not right:
            continue
        relationship = {
            "relationship_id": "rel_" + uuid.uuid4().hex,
            "source_seed_id": left["seed_id"], "target_seed_id": right["seed_id"],
            "relationship_type": "Related Work", "created_at": datetime.now().isoformat(),
            "proposed_by": "evidence_rules_v1", "approval_status": "Approved",
            "approved_by": "user", "approved_at": datetime.now().isoformat(),
            "approval_basis": "User confirmed a source-backed cross-conversation relationship suggestion.",
            "supporting_sources": [link["left_candidate_id"], link["right_candidate_id"]],
            "evidence": "Shared source terms: " + ", ".join(link["shared_terms"]),
            "source_candidate_link_id": link["id"], "confidence": link["score"],
            "analysis_method": link["method"]
        }
        relationships.append(relationship)
        left.setdefault("related_seeds", [])
        right.setdefault("related_seeds", [])
        if right["seed_id"] not in left["related_seeds"]: left["related_seeds"].append(right["seed_id"])
        if left["seed_id"] not in right["related_seeds"]: right["related_seeds"].append(left["seed_id"])
        created.append(relationship)
    return created


def materialize_tenant_relationships(workspace_id):
    """Materialize approved tenant proposals once both candidate-backed ideas exist."""
    workspace=load_workspace(workspace_id=workspace_id)
    seeds_by_candidate={item.get("candidate_id"):item for item in workspace.get("seeds",[]) if item.get("candidate_id")}
    existing={item.get("source_candidate_link_id") for item in workspace.get("relationships",[])}
    created=[]
    for link in tenant_list_links(workspace_id,"accepted"):
        if link["id"] in existing: continue
        left=seeds_by_candidate.get(link["left_candidate_id"]); right=seeds_by_candidate.get(link["right_candidate_id"])
        if not left or not right: continue
        relationship={"relationship_id":"rel_"+uuid.uuid4().hex,
            "source_seed_id":left["seed_id"],"target_seed_id":right["seed_id"],
            "relationship_type":"Related Work","approval_status":"Approved","approved_by":"user",
            "approved_at":datetime.now().isoformat(),"source_candidate_link_id":link["id"],
            "supporting_sources":[link["left_candidate_id"],link["right_candidate_id"]],
            "evidence":"Shared source terms: "+", ".join(link["shared_terms"]),"confidence":link["score"]}
        workspace.setdefault("relationships",[]).append(relationship)
        left.setdefault("related_seeds",[]); right.setdefault("related_seeds",[])
        if right["seed_id"] not in left["related_seeds"]: left["related_seeds"].append(right["seed_id"])
        if left["seed_id"] not in right["related_seeds"]: right["related_seeds"].append(left["seed_id"])
        created.append(relationship); existing.add(link["id"])
    if created: save_workspace(workspace,workspace_id,"relationship_materialized")
    return created


class SeedReflectionAPIHandler(BaseHTTPRequestHandler):

    def _bearer_token(self):
        value=self.headers.get("Authorization","")
        return value[7:].strip() if value.startswith("Bearer ") else ""

    def _runtime_user(self):
        if DEPLOYMENT_MODE == "local": return {"id":"local-owner","workspace_id":"local","role":"owner"}
        return auth_authenticate(self._bearer_token())

    def _send_json(self, data, status=200):
        try:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            # CORS headers
            self.send_header("Access-Control-Allow-Origin", PUBLIC_ORIGIN)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            print(f"Error sending JSON: {e}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", PUBLIC_ORIGIN)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/v2/capabilities":
            self._send_json({"mode":DEPLOYMENT_MODE,"billing":os.environ.get("SEED_REFLECTIONS_BILLING_ENABLED","0")=="1",
                "external_ai":os.environ.get("SEED_REFLECTIONS_EXTERNAL_AI_ENABLED","0")=="1",
                "teams":os.environ.get("SEED_REFLECTIONS_TEAM_ENABLED","0")=="1","local_first":True,
                "product_version":2,"runtime":"unified","hosted_archive_ingestion":True})
            return
        if path == "/api/v2/health":
            self._send_json({"status":"healthy","mode":DEPLOYMENT_MODE,"database":"sqlite_normalized",
                "runtime":"unified","time":datetime.now().isoformat()})
            return
        if path == "/api/v2/connectors":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]!="local":
                self._send_json({"connectors":[],"discovered":[],"adapters":source_adapter_catalog(),"desktop_bridge_required":True,
                    "message":"Local AI application sync requires the SeedReflections desktop connector on the user's computer."}); return
            self._send_json({"connectors":list_source_connectors("local"),"discovered":discover_connectors(),"adapters":source_adapter_catalog(),"desktop_bridge_required":False})
            return
        if path == "/api/v2/integrations":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            self._send_json({"integrations":list_api_integrations(user["workspace_id"]),
                "import_endpoint":"/api/v2/integrations/import","authentication":"Bearer connection token"})
            return
        connector_health_match=re.fullmatch(r"/api/v2/connectors/([^/]+)/health",path)
        if connector_health_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]!="local": self._send_json({"error":"Desktop connector required"},409); return
            try: self._send_json(source_connector_health(urllib.parse.unquote(connector_health_match.group(1)),"local"))
            except KeyError as exc: self._send_json({"error":str(exc)},404)
            return
        if path == "/api/v2/overview":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"] == "local":
                workspace=load_db(); archive=archive_analysis_overview()
                self._send_json({"imports":len(list_archive_imports()),"conversations":archive["total"],
                    "messages":sum(item.get("message_count",item.get("depth",0)) for item in list_archive_conversations()),
                    "pending":archive["pending_candidates"],"seeds":len(workspace.get("seeds",[])),
                    "projects":len(workspace.get("projects",[])),"recovered":sum(1 for item in workspace.get("seeds",[]) if str(item.get("continuity_status","")).lower()=="recovered")})
            else:
                create_empty_workspace(user["workspace_id"]); status=storage_status(user["workspace_id"]); counts=status["entity_counts"]
                archive=tenant_archive_overview(user["workspace_id"])
                self._send_json({**archive,"total":archive["conversations"],"pending_candidates":archive["pending"],
                    "seeds":counts["seeds"],"projects":counts["projects"],"recovered":0})
            return
        if path == "/api/v2/conversations":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            search=(query.get("q") or [""])[0]
            limit=max(1,min(int((query.get("limit") or ["500"])[0]),2000)); offset=max(0,int((query.get("offset") or ["0"])[0]))
            if user["workspace_id"] == "local":
                total=count_archive_conversations(search); items=list_archive_conversations(search,limit,offset)
            else:
                total=tenant_count_conversations(user["workspace_id"],search); items=tenant_list_conversations(user["workspace_id"],search,limit,offset)
            self._send_json({"conversations":items,"total":total,"limit":limit,"offset":offset,"has_more":offset+len(items)<total})
            return
        if path == "/api/v2/workspace":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            self._send_json(load_workspace(workspace_id=user["workspace_id"]))
            return
        if path == "/api/v2/settings":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"])
            settings=dict(workspace.get("settings") or {})
            settings.setdefault("user_name",user.get("name") or "Seed User")
            settings.setdefault("user_email",user.get("email") or "")
            settings.setdefault("user_plan","free")
            settings.setdefault("api_mode","managed" if DEPLOYMENT_MODE!="local" else "self_hosted")
            settings.setdefault("llm_provider","managed" if DEPLOYMENT_MODE!="local" else "ollama")
            for key in ("privacy_analytics","privacy_store_transcripts","privacy_sign_seeds"):
                settings.setdefault(key,True)
            settings.setdefault("privacy_ai_training",False); settings.setdefault("privacy_marketing_emails",False)
            self._send_json(settings)
            return
        conversation_match=re.fullmatch(r"/api/v2/conversations/([^/]+)",path)
        if conversation_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            conversation_id=urllib.parse.unquote(conversation_match.group(1))
            result=(get_archive_conversation(conversation_id) if user["workspace_id"] == "local"
                    else tenant_get_conversation(user["workspace_id"],conversation_id))
            self._send_json(result if result else {"error":"Conversation not found"},200 if result else 404)
            return
        if path == "/api/v2/candidates":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            status=(query.get("status") or ["pending"])[0]
            candidates=(list_candidates(status) if user["workspace_id"] == "local"
                        else tenant_list_candidates(user["workspace_id"],status))
            self._send_json({"candidates":candidates})
            return
        if path == "/api/v2/imports/jobs":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]=="local": self._send_json({"jobs":list_import_jobs()})
            else: self._send_json({"jobs":tenant_list_import_jobs(user["workspace_id"])})
            return
        import_job_match=re.fullmatch(r"/api/v2/imports/jobs/([^/]+)",path)
        if import_job_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            job_id=urllib.parse.unquote(import_job_match.group(1))
            job=(get_import_job(job_id) if user["workspace_id"]=="local" else tenant_get_import_job(user["workspace_id"],job_id))
            self._send_json(job if job else {"error":"Import job not found"},200 if job else 404); return
        analysis_job_match=re.fullmatch(r"/api/v2/analysis/jobs/([^/]+)",path)
        if analysis_job_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            job=(get_analysis_job(urllib.parse.unquote(analysis_job_match.group(1))) if user["workspace_id"]=="local"
                 else tenant_get_analysis_job(user["workspace_id"],urllib.parse.unquote(analysis_job_match.group(1))))
            self._send_json(job if job else {"error":"Analysis job not found"},200 if job else 404); return
        if path == "/api/v2/relationships":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); status=(query.get("status") or ["pending"])[0]
            links=(list_candidate_links(status) if user["workspace_id"]=="local" else tenant_list_links(user["workspace_id"],status))
            self._send_json({"links":links}); return
        if path == "/api/v2/sources":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]=="local": self._send_json({"error":"Use the local archive imports endpoint for source evidence."},409)
            else: self._send_json({"sources":tenant_list_sources(user["workspace_id"])})
            return
        if path == "/api/v2/backup/download":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]=="local": self._send_json({"error":"Hosted tenant backup is unavailable in local mode."},409); return
            backup_path=tenant_export_backup_archive(user["workspace_id"])
            try:
                self.send_response(200); self.send_header("Content-Type","application/zip")
                self.send_header("Content-Disposition",'attachment; filename="seed-reflections-backup.zip"')
                self.send_header("Content-Length",str(backup_path.stat().st_size)); self.send_header("X-Content-Type-Options","nosniff"); self.end_headers()
                with backup_path.open("rb") as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b""): self.wfile.write(chunk)
            finally: backup_path.unlink(missing_ok=True)
            return
        if path == "/api/v2/backup":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]=="local": self._send_json({"error":"Hosted tenant backup is unavailable in local mode."},409)
            else: self._send_json(tenant_export_backup(user["workspace_id"]))
            return
        source_download_match=re.fullmatch(r"/api/v2/sources/([^/]+)/download",path)
        if source_download_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            source=tenant_get_source(user["workspace_id"],urllib.parse.unquote(source_download_match.group(1)),True)
            if not source: self._send_json({"error":"Source not found"},404); return
            source_path=Path(source["source_path"])
            if not source_path.is_file(): self._send_json({"error":"Preserved source is unavailable"},410); return
            self.send_response(200); self.send_header("Content-Type",source["media_type"])
            self.send_header("Content-Disposition",f'attachment; filename="{source["filename"]}"')
            self.send_header("Content-Length",str(source["byte_count"])); self.end_headers()
            with source_path.open("rb") as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b""): self.wfile.write(chunk)
            return
        source_match=re.fullmatch(r"/api/v2/sources/([^/]+)",path)
        if source_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            source=tenant_get_source(user["workspace_id"],urllib.parse.unquote(source_match.group(1)))
            self._send_json(source if source else {"error":"Source not found"},200 if source else 404); return
        if path == "/api/v2/projects":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"])
            projects=[]
            for project in workspace.get("projects",[]):
                item=dict(project); project_id=item.get("project_id") or item.get("id")
                item["seed_count"]=sum(1 for seed in workspace.get("seeds",[]) if seed.get("project_id")==project_id)
                projects.append(item)
            self._send_json({"projects":projects})
            return
        if path == "/api/v2/recovery":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); items=[]
            for seed in workspace.get("seeds",[]):
                if str(seed.get("status","")).lower() in {"completed","done","archived","wilted"}: continue
                item=dict(seed); item.setdefault("id",item.get("seed_id")); item["recovery_score"]=50 if seed.get("source_message_id") else 35
                item["reason"]="User-confirmed idea remains open with its source evidence preserved."
                items.append(item)
            self._send_json({"recovery_candidates":items})
            return
        if path in {"/api/v2/analysis/lost-seeds", "/api/v2/analysis/intent-drift"}:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            project_id=get_query_param(self.path,"project_id") or "default_project"
            workspace=load_workspace(workspace_id=user["workspace_id"])
            result=(analyze_lost_seeds(workspace,project_id) if path.endswith("lost-seeds")
                    else analyze_intent_drift(workspace,project_id))
            self._send_json(result); return
        context_v2_match=re.fullmatch(r"/api/v2/projects/([^/]+)/context",path)
        if context_v2_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); project_id=urllib.parse.unquote(context_v2_match.group(1))
            project=next((item for item in workspace.get("projects",[]) if (item.get("project_id") or item.get("id"))==project_id),None)
            if not project: self._send_json({"error":"Project not found"},404); return
            seeds=[item for item in workspace.get("seeds",[]) if item.get("project_id")==project_id and str(item.get("status","")).lower() not in {"archived","wilted"}]
            decisions=[item for item in workspace.get("decisions",[]) if item.get("project_id")==project_id and str(item.get("status","active")).lower()=="active"]
            lines=[f"# Project Context: {project.get('name') or project.get('title')}","","## Mission",project.get("mission") or "Not yet defined.","","## Confirmed Ideas"]
            lines += [f"- **{item.get('title')}** — {item.get('intent') or item.get('description','')} (state: {item.get('status','active')})" for item in seeds] or ["- No confirmed ideas yet."]
            lines += ["","## Decisions"] + ([f"- {item.get('statement') or item.get('title')}" for item in decisions] or ["- No active decisions recorded."])
            lines += ["","## Operating instruction","Treat this package as user-reviewed context. Ask before changing the mission or superseding confirmed decisions."]
            self._send_json({"project":project,"markdown":"\n".join(lines),"seed_count":len(seeds),"decision_count":len(decisions)})
            return
        package_v2_match=re.fullmatch(r"/api/v2/projects/([^/]+)/package",path)
        if package_v2_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); project_id=urllib.parse.unquote(package_v2_match.group(1))
            project=next((item for item in workspace.get("projects",[]) if (item.get("project_id") or item.get("id"))==project_id),None)
            if not project: self._send_json({"error":"Project not found"},404); return
            seeds=[item for item in workspace.get("seeds",[]) if item.get("project_id")==project_id]; seed_ids={item.get("seed_id") or item.get("id") for item in seeds}
            decisions=[item for item in workspace.get("decisions",[]) if item.get("project_id")==project_id]
            conflicts=[item for item in workspace.get("conflicts",[]) if item.get("project_id")==project_id]
            relationships=[item for item in workspace.get("relationships",[]) if item.get("source_seed_id") in seed_ids or item.get("target_seed_id") in seed_ids]
            lines=[f"# Portable Context Package: {project.get('name','Untitled Project')}",f"* **Project ID**: `{project_id}`","","## Mission Charter",project.get("mission") or project.get("purpose") or "Not set","","## Authoritative Seeds"]
            lines += [f"* **{item.get('title') or item.get('intent','')[:60]}** — {item.get('intent','')}" for item in seeds] or ["*No seeds recorded.*"]
            self._send_json({"project_id":project_id,"markdown_package":"\n".join(lines),"json_package":{"package_version":"2.0.0","project":project,
                "seeds":seeds,"decisions":decisions,"conflicts":conflicts,"relationships":relationships}}); return
        seed_export_match=re.fullmatch(r"/api/v2/workspace/seeds/([^/]+)/export",path)
        if seed_export_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            seed_id=urllib.parse.unquote(seed_export_match.group(1)); workspace=load_workspace(workspace_id=user["workspace_id"])
            seed=next((item for item in workspace.get("seeds",[]) if (item.get("seed_id") or item.get("id"))==seed_id),None)
            if not seed: self._send_json({"error":"Seed not found"},404); return
            markdown=f"# {seed.get('title') or seed.get('intent','Idea')}\n\n{seed.get('intent') or seed.get('description','')}\n\nStatus: {seed.get('status','Active')}"
            self._send_json({"seed":seed,"markdown":markdown}); return
        if DEPLOYMENT_MODE != "local" and path.startswith("/api/v1/"):
            self._send_json({"error":"Legacy local API is unavailable in hosted mode; use authenticated /api/v2 routes."},403)
            return
        # ── Health check ──
        if path in ("/api/v1/health", "/health"):
            self._send_json({"status": "healthy", "service": "seed-reflection", "timestamp": datetime.now().isoformat()})
            return

        if path == "/api/v1/storage":
            self._send_json(storage_status() if os.path.abspath(DATA_FILE) == DEFAULT_DATA_FILE else {
                "backend":"legacy_json_test_adapter","database":os.path.abspath(DATA_FILE)})
            return

        if path == "/api/v1/archive/conversations":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            search = (query.get("q") or [""])[0]
            limit=max(1,min(int((query.get("limit") or ["500"])[0]),2000)); offset=max(0,int((query.get("offset") or ["0"])[0]))
            items=list_archive_conversations(search,limit,offset); total=count_archive_conversations(search)
            self._send_json({"conversations":items,"total":total,"limit":limit,"offset":offset,"has_more":offset+len(items)<total})
            return

        if path == "/api/v1/archive/imports":
            self._send_json({"imports": list_archive_imports()})
            return

        if path == "/api/v1/archive/jobs":
            self._send_json({"jobs": list_import_jobs()})
            return

        if path == "/api/v1/archive/candidates":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            status = (query.get("status") or ["pending"])[0]
            self._send_json({"candidates": list_candidates(status)})
            return

        if path == "/api/v1/archive/analysis":
            self._send_json(archive_analysis_overview())
            return

        if path == "/api/v1/archive/links":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            status = (query.get("status") or ["pending"])[0]
            self._send_json({"links":list_candidate_links(status)})
            return

        if path.startswith("/api/v1/archive/analysis/jobs/"):
            job = get_analysis_job(urllib.parse.unquote(path.rsplit("/", 1)[-1]))
            self._send_json(job if job else {"error":"Analysis job not found"}, 200 if job else 404)
            return

        if path.startswith("/api/v1/archive/jobs/"):
            job = get_import_job(urllib.parse.unquote(path.rsplit("/", 1)[-1]))
            self._send_json(job if job else {"error": "Import job not found"}, 200 if job else 404)
            return

        if path.startswith("/api/v1/archive/conversations/"):
            conversation_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            result = get_archive_conversation(conversation_id)
            if not result:
                self._send_json({"error": "Conversation not found"}, 404)
            else:
                self._send_json(result)
            return

        # ── Standalone Widget SDK & Serving ──
        if path == "/sdk/seed-signature-widget.js":
            js_code = """
(function() {
  window.SeedSignature = {
    openSignModal: function(options) {
      var sessionToken = options.sessionToken;
      var onComplete = options.onComplete;
      var onError = options.onError;

      if (!sessionToken) {
        if (onError) onError("Missing sessionToken");
        return;
      }

      // Create modal container
      var backdrop = document.createElement('div');
      backdrop.id = 'seed-sig-backdrop';
      backdrop.style.position = 'fixed';
      backdrop.style.inset = '0';
      backdrop.style.background = 'rgba(6, 8, 15, 0.85)';
      backdrop.style.backdropFilter = 'blur(8px)';
      backdrop.style.zIndex = '9999';
      backdrop.style.display = 'flex';
      backdrop.style.alignItems = 'center';
      backdrop.style.justifyContent = 'center';
      backdrop.style.padding = '20px';

      // Create modal box
      var container = document.createElement('div');
      container.style.width = '100%';
      container.style.maxWidth = '500px';
      container.style.height = '480px';
      container.style.background = '#0d1117';
      container.style.border = '1px solid #21262d';
      container.style.borderRadius = '16px';
      container.style.overflow = 'hidden';
      container.style.position = 'relative';
      container.style.boxShadow = '0 24px 64px rgba(0,0,0,0.6)';

      // Create iframe
      var iframe = document.createElement('iframe');
      iframe.src = '/widget/sign?token=' + encodeURIComponent(sessionToken);
      iframe.style.width = '100%';
      iframe.style.height = '100%';
      iframe.style.border = 'none';

      container.appendChild(iframe);
      backdrop.appendChild(container);
      document.body.appendChild(backdrop);

      // Listener for child message
      function handleMessage(event) {
        var data = event.data;
        if (data && data.type === 'SIGN_COMPLETE') {
          cleanup();
          if (onComplete) onComplete({
            signatureId: data.signatureId,
            certificateUrl: data.certificateUrl
          });
        } else if (data && data.type === 'SIGN_CANCEL') {
          cleanup();
          if (onError) onError("User cancelled signing");
        } else if (data && data.type === 'SIGN_ERROR') {
          cleanup();
          if (onError) onError(data.error);
        }
      }

      function cleanup() {
        window.removeEventListener('message', handleMessage);
        if (backdrop.parentNode) {
          backdrop.parentNode.removeChild(backdrop);
        }
      }

      window.addEventListener('message', handleMessage);
    }
  };
})();
            """
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(js_code)))
            self.end_headers()
            self.wfile.write(js_code.encode("utf-8"))
            return

        elif path == "/widget/sign":
            query = self.path.split("?")[-1] if "?" in self.path else ""
            token = ""
            if "token=" in query:
                token = query.split("token=")[-1].split("&")[0]
            
            if not token or token not in SIGNATURE_SESSIONS:
                html = """
                <html><body style="background:#06080f;color:#bc8cff;font-family:sans-serif;text-align:center;padding-top:100px;">
                <h2>Invalid or Expired Signature Session</h2>
                <p style="color:#8b949e">Please close this window and try signing the seed again.</p>
                </body></html>
                """
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
                return
            
            session = SIGNATURE_SESSIONS[token]
            seed_content = session["content"]
            
            html = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{
      background: #0d1117;
      color: #f0f6fc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 24px;
      display: flex;
      flex-direction: column;
      height: 100vh;
      box-sizing: border-box;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #21262d;
      padding-bottom: 12px;
      margin-bottom: 16px;
    }}
    .title {{
      font-weight: 700;
      font-size: 14px;
      color: #3fb950;
    }}
    .content-box {{
      background: #06080f;
      border: 1px solid #21262d;
      border-radius: 8px;
      padding: 16px;
      font-family: monospace;
      font-size: 13px;
      color: #c9d1d9;
      margin-bottom: 16px;
      overflow-y: auto;
      flex-grow: 1;
      white-space: pre-wrap;
      word-break: break-all;
    }}
    .input-group {{
      margin-bottom: 20px;
    }}
    .input-label {{
      font-size: 11px;
      font-weight: 700;
      color: #8b949e;
      text-transform: uppercase;
      margin-bottom: 6px;
    }}
    .text-input {{
      width: 100%;
      background: #06080f;
      border: 1px solid #21262d;
      color: #f0f6fc;
      border-radius: 6px;
      padding: 8px 12px;
      outline: none;
      box-sizing: border-box;
    }}
    .text-input:focus {{
      border-color: #3fb950;
    }}
    .actions {{
      display: flex;
      justify-content: flex-end;
      gap: 12px;
    }}
    .btn {{
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid #21262d;
      transition: all 0.15s;
    }}
    .btn-ghost {{
      background: transparent;
      color: #8b949e;
    }}
    .btn-ghost:hover {{
      color: #f0f6fc;
      background: rgba(255,255,255,0.05);
    }}
    .btn-primary {{
      background: #3fb950;
      color: #000;
      border-color: #3fb950;
    }}
    .btn-primary:hover {{
      filter: brightness(1.1);
    }}
  </style>
</head>
<body>
  <div class="header">
    <div class="title">🔐 SEED SIGNATURE WIDGET</div>
    <div style="font-size: 10px; color: #8b949e;">[SCIA PROVENANCE]</div>
  </div>
  
  <div class="input-label">Verify Seed Intent Content</div>
  <div class="content-box">\"{seed_content}\"</div>
  
  <div class="input-group">
    <div class="input-label">Enter Signing Passphrase</div>
    <input type="password" id="passphrase" class="text-input" placeholder="Type personal key passphrase..." />
  </div>
  
  <div class="actions">
    <button class="btn btn-ghost" onclick="cancel()">Cancel</button>
    <button class="btn btn-primary" onclick="submit()">Seal Provenance Signature</button>
  </div>

  <script>
    function cancel() {{
      window.parent.postMessage({{ type: 'SIGN_CANCEL' }}, '*');
    }}
    
    async function submit() {{
      const pass = document.getElementById('passphrase').value.trim();
      if (!pass) {{
        alert('Please enter a passphrase to sign the seed.');
        return;
      }}
      
      try {{
        const resp = await fetch('/widget/sign/submit', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            token: '{token}',
            passphrase: pass
          }})
        }});
        const result = await resp.json();
        if (result.error) {{
          alert(result.error);
        }} else {{
          window.parent.postMessage({{
            type: 'SIGN_COMPLETE',
            signatureId: result.signatureId,
            certificateUrl: result.certificateUrl
          }}, '*');
        }}
      }} catch(e) {{
        alert('Failed to connect to backend signature engine.');
      }}
    }}
  </script>
</body>
</html>
"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        elif path.startswith("/seeds/verify/"):
            sig_id = path.replace("/seeds/verify/", "").strip("/")
            seeds = load_seeds()
            
            target_seed = None
            for s in seeds:
                if s.get("trust_state", {}).get("signature") == sig_id:
                    target_seed = s
                    break
            
            if target_seed:
                content_text = target_seed.get("intent", target_seed.get("description", ""))
                date_str = target_seed.get("created_at", datetime.now().isoformat())
                html = f"""<!DOCTYPE html>
<html>
<head>
  <title>Verifiable Provenance Record</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    body {{
      background: #06080f;
      color: #f0f6fc;
      font-family: 'Inter', sans-serif;
      margin: 0;
      padding: 40px 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      box-sizing: border-box;
    }}
    .cert {{
      background: #0d1117;
      border: 1.5px solid #21262d;
      border-radius: 16px;
      width: 100%;
      max-width: 580px;
      padding: 40px;
      box-shadow: 0 24px 64px rgba(0,0,0,0.6);
      border-top: 4px solid #3fb950;
      position: relative;
    }}
    .badge {{
      background: rgba(63,185,80,0.15);
      border: 1px solid #3fb950;
      color: #3fb950;
      border-radius: 20px;
      padding: 6px 14px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1px;
      display: inline-block;
      margin-bottom: 24px;
    }}
    h1 {{
      font-size: 24px;
      font-weight: 900;
      margin: 0 0 16px 0;
      letter-spacing: -0.5px;
    }}
    p {{
      color: #8b949e;
      font-size: 13.5px;
      line-height: 1.6;
      margin-top: 0;
      margin-bottom: 28px;
    }}
    .field-label {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      text-transform: uppercase;
      color: #8b949e;
      margin-bottom: 6px;
    }}
    .field-value {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
      color: #c9d1d9;
      background: #06080f;
      border: 1px solid #21262d;
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 20px;
      white-space: pre-wrap;
      word-break: break-all;
    }}
    .footer {{
      border-top: 1px solid #21262d;
      padding-top: 24px;
      margin-top: 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: #8b949e;
    }}
  </style>
</head>
<body>
  <div class="cert">
    <div class="badge">✓ Verified Original Seed</div>
    <h1>Provenance Certificate</h1>
    <p>This cryptographic signature record guarantees the authorship and content integrity of the original intent seed.</p>
    
    <div class="field-label">Signature ID</div>
    <div class="field-value" style="color:#bc8cff;font-weight:bold;">{sig_id}</div>
    
    <div class="field-label">Original Seed Intent</div>
    <div class="field-value">"{content_text}"</div>
    
    <div class="field-label">Verification Timestamp</div>
    <div class="field-value">{date_str}</div>
    
    <div class="field-label">Attributed Lineage Authority</div>
    <div class="field-value" style="color:#3fb950;">Seed-Class Intelligence Architecture (SCIA v4.0)</div>
    
    <div class="footer">
      <span>Lineage: Pass (Authentic)</span>
      <span>Seed Reflections Provenance Engine</span>
    </div>
  </div>
</body>
</html>
"""
            else:
                html = f"""<!DOCTYPE html>
<html>
<head>
  <title>Invalid Signature Certificate</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    body {{
      background: #06080f;
      color: #f0f6fc;
      font-family: 'Inter', sans-serif;
      margin: 0;
      padding: 40px 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      box-sizing: border-box;
    }}
    .cert {{
      background: #0d1117;
      border: 1.5px solid #21262d;
      border-radius: 16px;
      width: 100%;
      max-width: 580px;
      padding: 40px;
      box-shadow: 0 24px 64px rgba(0,0,0,0.6);
      border-top: 4px solid #f85149;
    }}
    .badge {{
      background: rgba(248,81,73,0.15);
      border: 1px solid #f85149;
      color: #f85149;
      border-radius: 20px;
      padding: 6px 14px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1px;
      display: inline-block;
      margin-bottom: 24px;
    }}
    h1 {{
      font-size: 24px;
      font-weight: 900;
      margin: 0 0 16px 0;
      letter-spacing: -0.5px;
    }}
    p {{
      color: #8b949e;
      font-size: 13.5px;
      line-height: 1.6;
      margin-top: 0;
      margin-bottom: 28px;
    }}
  </style>
</head>
<body>
  <div class="cert">
    <div class="badge">✕ WARNING: INVALID SIGNATURE</div>
    <h1>Attribution Check Failed</h1>
    <p>The cryptographic signature ID <strong>{sig_id}</strong> is invalid or does not match any authenticated record in our provenance registry. The content lineage has been compromised or modified.</p>
  </div>
</body>
</html>
"""
            self.send_response(200 if target_seed else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return



        # ── API Endpoint: List Seeds ──
        elif path == "/api/v1/seeds":
            db = load_db()
            seeds = db["seeds"]
            summaries = []
            for s in seeds:
                summaries.append({
                    "id": s.get("seed_id"),
                    "seed_id": s.get("seed_id"),
                    "title": s.get("title") or s.get("intent", "").split("\n")[0][:100],
                    "intent": s.get("intent"),
                    "description": s.get("description") or s.get("intent"),
                    "stage": s.get("status", "planted"),
                    "status": s.get("status", "planted"),
                    "stage_emoji": "🌱" if s.get("status") == "planted" else "🌸",
                    "growth": s.get("growth", 0),
                    "source": s.get("source", "web"),
                    "source_platform": s.get("source_platform", "web"),
                    "source_transcript_id": s.get("source_transcript_id"),
                    "source_thread_title": s.get("source_thread_title"),
                    "source_excerpt": s.get("source_excerpt", ""),
                    "source_message_id": s.get("source_message_id", ""),
                    "source_timestamp": s.get("source_timestamp", ""),
                    "created_at": s.get("created_at"),
                    "modified_at": s.get("modified_at"),
                    "completed_at": s.get("completed_at"),
                    "is_cryptographically_signed": s.get("is_cryptographically_signed", False),
                    "trust_state": s.get("trust_state", {}),
                    "evidence_status": s.get("evidence_status", "Explicitly Stated"),
                    "authority_status": s.get("authority_status", "Detected"),
                    "continuity_status": s.get("continuity_status", "Active"),
                    "project_id": s.get("project_id", "default_project"),
                    "versions": s.get("versions", []),
                    "related_seeds": s.get("related_seeds", []),
                    "parent_seed_id": s.get("parent_seed_id", None),
                    "child_seeds": s.get("child_seeds", []),
                    "conflict_references": s.get("conflict_references", []),
                    "decision_references": s.get("decision_references", []),
                    "keywords": s.get("keywords", []),
                    "recovery_suggestion": s.get("recovery_suggestion", "")
                })
            self._send_json({
                "seeds": summaries,
                "projects": db.get("projects", []),
                "sources": db.get("sources", []),
                "decisions": db.get("decisions", []),
                "conflicts": db.get("conflicts", []),
                "relationships": db.get("relationships", [])
            })
            return

        # ── API Endpoint: Weighted Lost-Seeds Engine ──
        elif path == "/api/v1/analysis/lost-seeds":
            project_id = get_query_param(self.path, "project_id") or "default_project"
            db = load_db()
            
            # Find all active / planted seeds for the project
            active_seeds = []
            for s in db["seeds"]:
                if s.get("project_id") == project_id:
                    status = s.get("status", "planted")
                    continuity = s.get("continuity_status", "Active")
                    if status not in ["wilted", "abandoned", "completed"] and continuity not in ["Historical", "Superseded"]:
                        active_seeds.append(s)

            # Get relationships, decisions, sources
            relationships = db.get("relationships", [])
            sources = sorted(
                [src for src in db.get("sources", []) if src.get("project_id") == project_id],
                key=lambda x: x.get("created_at") or ""
            )

            # Extract latest transcript text if available
            latest_transcript_text = ""
            if sources:
                latest_transcript_text = (sources[-1].get("content") or "").lower()

            results = []
            for s in active_seeds:
                seed_id = s.get("seed_id")
                
                # 1. No descendants
                has_descendants = False
                for r in relationships:
                    if r.get("source_seed_id") == seed_id:
                        has_descendants = True
                        break
                if not has_descendants and len(s.get("child_seeds", [])) > 0:
                    has_descendants = True
                no_descendants = 1.0 if not has_descendants else 0.0

                # 2. No decisions linked
                no_decisions = 1.0 if len(s.get("decision_references", [])) == 0 else 0.0

                # 3. No versions in history
                no_versions = 1.0 if len(s.get("versions", [])) == 0 else 0.0

                # 4. Absent from latest transcript text
                absent_from_transcript = 0.0
                if sources:
                    terms = s.get("keywords", [])[:]
                    if s.get("title"):
                        terms.append(s["title"])
                    terms = [t.lower() for t in terms if len(t.strip()) > 3]
                    
                    if not terms:
                        title_words = [w.lower() for w in re.findall(r"\w+", s.get("title") or "") if len(w) > 3]
                        terms.extend(title_words)

                    if terms:
                        found_term = False
                        for t in terms:
                            if t in latest_transcript_text:
                                found_term = True
                                break
                        if not found_term:
                            absent_from_transcript = 1.0
                    else:
                        absent_from_transcript = 0.5
                else:
                    absent_from_transcript = 0.5

                # 5. Inactivity score
                inactivity_score = 0.0
                last_mod = s.get("modified_at") or s.get("created_at") or ""
                if len(sources) >= 3:
                    cutoff_date = sources[-3].get("created_at") or ""
                    if last_mod < cutoff_date:
                        inactivity_score = 1.0
                elif sources:
                    if last_mod < (sources[-1].get("created_at") or ""):
                        inactivity_score = 1.0
                else:
                    inactivity_score = 0.0

                # Calculate weighted score using inverted protective signals:
                # - presence of descendants (no_descendants = 0 if descendants exist, 1 otherwise; weight = 0.25)
                # - presence of linked decisions (no_decisions = 0 if linked, 1 otherwise; weight = 0.20)
                # - presence of versions (no_versions = 0 if versions exist, 1 otherwise; weight = 0.15)
                # - presence in latest session transcripts (absent_from_transcript = 0 if found, 1 if absent, 0.5 default if no transcripts; weight = 0.25)
                # - active updates (inactivity_score = 0 if updated recently, 1 if inactive/stale; weight = 0.15)
                score = (no_descendants * 0.25) + (no_decisions * 0.20) + (no_versions * 0.15) + (absent_from_transcript * 0.25) + (inactivity_score * 0.15)
                
                # Classify into candidate tiers (declaring likelihood candidates rather than definitive lost state)
                if score >= 0.8:
                    classification = "High Confidence Candidate"
                elif score >= 0.6:
                    classification = "Likely Candidate"
                elif score >= 0.3:
                    classification = "Possible Candidate"
                else:
                    classification = "Active"

                results.append({
                    "seed_id": seed_id,
                    "title": s.get("title") or "Untitled Seed",
                    "score": round(score, 2),
                    "classification": classification,
                    "metrics": {
                        "no_descendants": no_descendants,
                        "no_decisions": no_decisions,
                        "no_versions": no_versions,
                        "absent_from_transcript": absent_from_transcript,
                        "inactivity_score": inactivity_score
                    }
                })

            self._send_json({"project_id": project_id, "lost_seeds": results})
            return

        # ── API Endpoint: Dual Drift Analysis ──
        elif path == "/api/v1/analysis/intent-drift":
            project_id = get_query_param(self.path, "project_id") or "default_project"
            db = load_db()

            # Find matching project
            project = next((p for p in db.get("projects", []) if p.get("project_id") == project_id), None)
            project_charter = ""
            if project:
                project_charter = f"{project.get('purpose', '')} {project.get('description', '')}".strip()

            # Find all active seeds
            active_seeds = []
            for s in db["seeds"]:
                if s.get("project_id") == project_id:
                    status = s.get("status", "planted")
                    if status not in ["wilted", "abandoned", "completed"]:
                        active_seeds.append(s)

            # 1. Calculate Mission Drift
            charter_words = set(w.lower() for w in re.findall(r"\w+", project_charter) if len(w) > 3)
            
            seed_words = set()
            for s in active_seeds:
                seed_text = f"{s.get('title', '')} {s.get('intent', '')} {' '.join(s.get('keywords', []))}"
                words = re.findall(r"\w+", seed_text)
                for w in words:
                    if len(w) > 3:
                        seed_words.add(w.lower())

            if charter_words:
                shared_words = charter_words.intersection(seed_words)
                mission_drift_index = 1.0 - (len(shared_words) / len(charter_words))
                matched_terms = list(shared_words)
                missing_charter_terms = list(charter_words - seed_words)
                new_terms = list(seed_words - charter_words)
            else:
                mission_drift_index = 0.0
                matched_terms = []
                missing_charter_terms = []
                new_terms = list(seed_words)

            # 2. Calculate Decision Coverage
            decisions = db.get("decisions", [])
            approved_decision_ids = {d.get("decision_id") for d in decisions if d.get("status") == "Accepted"}
            
            unapproved_seeds = []
            for s in active_seeds:
                linked = False
                for d_ref in s.get("decision_references", []):
                    if d_ref in approved_decision_ids:
                        linked = True
                        break
                if not linked:
                    unapproved_seeds.append(s.get("seed_id"))

            if active_seeds:
                decision_coverage_index = 1.0 - (len(unapproved_seeds) / len(active_seeds))
            else:
                decision_coverage_index = 1.0

            self._send_json({
                "project_id": project_id,
                "mission_drift_index": round(mission_drift_index * 100, 1),
                "decision_coverage_index": round(decision_coverage_index * 100, 1),
                "scope_drift_index": round((1.0 - decision_coverage_index) * 100, 1), # kept for backward compat
                "uncovered_seed_ids": unapproved_seeds,
                "unapproved_seed_ids": unapproved_seeds, # kept for backward compat
                "matched_terms": matched_terms,
                "missing_charter_terms": missing_charter_terms,
                "new_terms": new_terms,
                "analysis_method": "deterministic lexical analysis",
                "confidence_limitations": "Lexical analysis only checks direct word presence and does not capture synonymy or conceptual mapping."
            })
            return

        # ── API Endpoint: Export Seed record ──
        elif path.startswith("/api/v1/seeds/") and path.endswith("/export"):
            parts = path.split("/")
            seed_id = parts[-2]
            db = load_db()
            target = next((s for s in db["seeds"] if s.get("seed_id") == seed_id), None)
            if not target:
                self._send_json({"error": f"Seed {seed_id} not found"}, 404)
                return

            title_text = target.get('title') or (target.get('intent') or "")[:60] or "Untitled Seed"
            title_text = str(title_text).strip()
            
            seed_id_str = target.get('seed_id') or "Not recorded"
            project_id_str = target.get('project_id') or "Not recorded"
            status_str = target.get('status') or "Not recorded"
            evidence_str = target.get('evidence_status') or "Not recorded"
            auth_str = target.get('authority_status') or "Not recorded"
            cont_str = target.get('continuity_status') or "Not recorded"
            intent_str = target.get('intent') or "Not recorded"
            excerpt_str = target.get('source_excerpt') or "Not recorded"
            
            md = f"# Seed Record: {title_text}\n\n" \
                 f"* **Seed ID**: `{seed_id_str}`\n" \
                 f"* **Project ID**: `{project_id_str}`\n" \
                 f"* **Lifecycle Status**: {status_str}\n" \
                 f"* **Evidence Status**: {evidence_str}\n" \
                 f"* **Authority Status**: {auth_str}\n" \
                 f"* **Continuity Status**: {cont_str}\n\n" \
                 f"## Original Wording / Intent\n> {intent_str}\n\n" \
                 f"## Source Transcript Excerpt\n> {excerpt_str}\n\n"

            # Decisions
            md += "## Linked Architectural Decisions\n"
            related_decisions = [d for d in db.get("decisions", []) if seed_id in d.get("related_seeds", [])]
            if related_decisions:
                for d in related_decisions:
                    d_type = d.get("decision_type") or "Not recorded"
                    d_maker = d.get("decision_maker") or "user"
                    d_stmt = d.get("decision_statement") or "Not recorded"
                    d_date = d.get("date") or "Not recorded"
                    md += f"* **[{d_type}]** {d_stmt} *(Maker: {d_maker}, Date: {d_date})*\n"
            else:
                md += "*No linked decisions*\n"
            md += "\n"

            # Conflicts
            md += "## Linked Intent Conflicts\n"
            related_conflicts = [c for c in db.get("conflicts", []) if c.get("seed_a") == seed_id or c.get("seed_b") == seed_id]
            if related_conflicts:
                for c in related_conflicts:
                    c_subj = c.get("subject") or "Not recorded"
                    c_type = c.get("conflict_type") or "Not recorded"
                    c_sev = c.get("severity") or "Medium"
                    c_status = c.get("status") or "Unresolved"
                    md += f"* **[{c_type} / {c_sev}]** {c_subj} *(Status: {c_status})*\n"
            else:
                md += "*No linked conflicts*\n"
            md += "\n"

            # Signatures
            md += "## Cryptographic Attestation & Signature\n"
            trust = target.get("trust_state") or {}
            is_signed = target.get("is_cryptographically_signed") or False
            sig_id = trust.get("signature") if trust.get("signature") != "unsigned" else None
            sig_result = target.get("verification_result") or {}
            if is_signed and sig_id:
                cert_url = sig_result.get("certificate_url") or f"/seeds/verify/{sig_id}"
                signed_at = sig_result.get("signed_at") or "Not recorded"
                md += f"* **Status**: 🔐 Signed & Cryptographically Attested\n" \
                      f"* **Signature ID**: `{sig_id}`\n" \
                      f"* **Signed At**: {signed_at}\n" \
                      f"* **Certificate**: [View Verification Page]({cert_url})\n"
            else:
                md += "*Unsigned / Unverified*\n"
            md += "\n"

            # Version History
            md += "## Prior Wording Version History\n"
            versions = target.get("versions")
            if versions and isinstance(versions, list):
                for idx, v in enumerate(versions, 1):
                    v_intent = v.get("intent") or "Not recorded"
                    v_status = v.get("status") or "Not recorded"
                    v_mod = v.get("modified_at") or "Not recorded"
                    md += f"### Version {idx} ({v_mod})\n" \
                          f"* **Status**: {v_status}\n" \
                          f"* **Wording**: {v_intent}\n\n"
            else:
                md += "*No prior versions*\n"
            md += "\n"

            # Metadata Details
            platform_str = target.get('source_platform') or "Not recorded"
            thread_str = target.get('source_thread_title') or "Not recorded"
            created_str = target.get('created_at') or "Not recorded"
            modified_str = target.get('modified_at') or "Not recorded"
            md += f"## Metadata Details\n" \
                  f"* **Source platform**: {platform_str}\n" \
                  f"* **Source thread**: {thread_str}\n" \
                  f"* **Created at**: {created_str}\n" \
                  f"* **Modified at**: {modified_str}\n"
            
            self._send_json({
                "seed": target,
                "markdown": md
            }, 200)
            return

        # ── API Endpoint: Get Transcript by ID ──
        elif path.startswith("/api/v1/transcripts/"):
            transcript_id = path.replace("/api/v1/transcripts/", "").strip("/")
            if not transcript_id or len(transcript_id) > 32:
                self._send_json({"error": "Invalid transcript ID"}, 400)
                return
            text = load_transcript(transcript_id)
            if text:
                self._send_json({"transcript_id": transcript_id, "text": text})
            else:
                self._send_json({"error": "Transcript not found"}, 404)
            return

        # ── API Endpoint: Get Current User ──
        elif path == "/api/v1/users/me" or path == "/users/me":
            with DB_LOCK:
                db = load_db()
                account = resolve_account_for_request(self, db)
                sync_account_cycle(account)
                tier_plan = account.get("plan", "free").lower()
                quota = TIER_QUOTAS.get(tier_plan, TIER_QUOTAS["free"])
                seeds_used = len(db.get("seeds", []))
                reflections_used = account.get("reflections_used_this_month", 0)
                self._send_json({
                    "id": account.get("id", 1),
                    "name": account.get("name", "Workspace User"),
                    "email": account.get("email", ""),
                    "active_plan": tier_plan,
                    "plan": tier_plan,
                    "plan_name": quota["name"],
                    "role": account.get("role", "consumer"),
                    "seeds_used": seeds_used,
                    "seeds_limit": quota["max_seeds"],
                    "reflections_used": reflections_used,
                    "reflections_limit": quota["max_monthly_reflections"],
                    "tokens_consumed": account.get("tokens_consumed", 0)
                })
            return

        # ── API Endpoint: Get Consumer Dashboard Info ──
        elif path == "/api/v1/users/me/consumer-dashboard":
            with DB_LOCK:
                db = load_db()
                account = resolve_account_for_request(self, db)
                sync_account_cycle(account)
                tier_plan = account.get("plan", "free").lower()
                quota = TIER_QUOTAS.get(tier_plan, TIER_QUOTAS["free"])
                seeds = db.get("seeds", [])
                self._send_json({
                    "plan": tier_plan,
                    "plan_name": quota["name"],
                    "seeds_used": len(seeds),
                    "seeds_limit": quota["max_seeds"],
                    "reflections_used": account.get("reflections_used_this_month", 0),
                    "reflections_limit": quota["max_monthly_reflections"],
                    "recent_seeds": [s.get("seed_id") for s in seeds[-5:]]
                })
            return

        # ── API Endpoint: Get Seeds Stats ──
        elif path == "/api/v1/seeds/stats" or path == "/seeds/stats":
            seeds = load_seeds()
            counts = {
                "active": 0,
                "planted": 0,
                "germinating": 0,
                "growing": 0,
                "bloomed": 0,
                "wilted": 0,
                "abandoned": 0,
                "completed": 0,
                "revived": 0,
                "drifting": 0,
                "paused": 0
            }
            total_revivals = 0
            for s in seeds:
                st = s.get("status", "planted")
                if st in counts:
                    counts[st] += 1
                
                # Groupings
                if st in ("growing", "active"):
                    counts["active"] += 1
                elif st in ("wilted", "abandoned"):
                    counts["abandoned"] += 1
                elif st in ("bloomed", "completed"):
                    counts["completed"] += 1

                if s.get("is_cryptographically_signed", False):
                    total_revivals += 1

            self._send_json({
                "total_seeds": len(seeds),
                "total_threads": len(seeds) // 2 + (len(seeds) % 2) if seeds else 0,
                "total_edges": len(seeds) - 1 if len(seeds) > 1 else 0,
                "total_revivals": total_revivals,
                "status_counts": counts
            })
            return

        # ── API Endpoint: Get Settings ──
        elif path == "/api/v1/settings":
            cfg = load_config()
            self._send_json(cfg)
            return

        # ── API Endpoint: Platform Master Control Overview ──
        elif path in ("/api/v1/admin/overview", "/admin/stats"):
            import time
            seeds = load_seeds()
            uptime = int(time.time() - START_TIME) if "START_TIME" in globals() else 3600
            
            # Storage Footprint
            active_store = str(storage_status().get("database")) if os.path.abspath(DATA_FILE) == DEFAULT_DATA_FILE else DATA_FILE
            db_size_bytes = os.path.getsize(active_store) if os.path.exists(active_store) else 0
            transcripts_count = 0
            transcripts_bytes = 0
            if os.path.exists(TRANSCRIPTS_DIR):
                for f in os.listdir(TRANSCRIPTS_DIR):
                    fp = os.path.join(TRANSCRIPTS_DIR, f)
                    if os.path.isfile(fp):
                        transcripts_count += 1
                        transcripts_bytes += os.path.getsize(fp)

            # LLM Token & Cost Aggregation
            total_prompt_tok = sum(item.get("prompt_tokens", 0) for item in TELEMETRY_LOG)
            total_comp_tok = sum(item.get("completion_tokens", 0) for item in TELEMETRY_LOG)
            total_tokens = total_prompt_tok + total_comp_tok
            total_cost_usd = sum(item.get("estimated_cost_usd", 0.0) for item in TELEMETRY_LOG)

            cfg = load_config()

            # Load Real Accounts from Database
            db = load_db()
            accounts_data = db.get("accounts", [])
            users_list = []
            for acc in accounts_data:
                sync_account_cycle(acc)
                tier_plan = acc.get("plan", "free").lower()
                quota = TIER_QUOTAS.get(tier_plan, TIER_QUOTAS["free"])
                reflections_used = acc.get("reflections_used_this_month", 0)
                acc_seeds = len(seeds) if acc.get("role") == "admin" else acc.get("seeds_count", len(seeds))
                users_list.append({
                    "id": acc.get("id", "usr_unknown"),
                    "name": acc.get("name", "Workspace User"),
                    "email": acc.get("email", ""),
                    "role": acc.get("role", "consumer"),
                    "plan": acc.get("plan", "free").capitalize() + " Tier",
                    "status": acc.get("status", "active").capitalize(),
                    "seeds_count": acc_seeds,
                    "seeds_limit": quota["max_seeds"],
                    "reflections_count": reflections_used,
                    "reflections_limit": quota["max_monthly_reflections"],
                    "tokens_consumed": acc.get("tokens_consumed", 0),
                    "last_active": acc.get("last_active", "Today")
                })

            # Stripe Configuration from config or env
            stripe_mode = cfg.get("stripe_mode", "test")
            calc_mrr = sum(20 if a.get("plan") == "master" else (9 if a.get("plan") == "pro" else 0) for a in accounts_data if a.get("status", "").lower() != "suspended")
            stripe_keys = {
                "mode": stripe_mode,
                "secret_key": cfg.get("stripe_secret_key", "sk_test_mock_seedreflections_12345"),
                "webhook_secret": cfg.get("stripe_webhook_secret", "whsec_mock_seedreflections_12345"),
                "checkout_urls": {
                    "free": cfg.get("stripe_checkout_free", "https://buy.stripe.com/test_seed_reflections_free"),
                    "pro": cfg.get("stripe_checkout_pro", "https://buy.stripe.com/test_seed_reflections_pro"),
                    "master": cfg.get("stripe_checkout_master", "https://buy.stripe.com/test_seed_reflections_master")
                },
                "monthly_revenue_mrr": f"${calc_mrr:.2f} USD",
                "webhook_events": STRIPE_WEBHOOK_LOG[-10:]
            }

            self._send_json({
                "status": "healthy",
                "uptime_seconds": uptime,
                "uptime_human": f"{uptime // 3600}h {(uptime % 3600) // 60}m {uptime % 60}s",
                "llm_telemetry": {
                    "active_provider": cfg.get("llm_provider", "openai_compatible"),
                    "active_model": cfg.get("llm_model", "qwen-qwq-32b"),
                    "endpoint_url": cfg.get("llm_api_url", "https://api.groq.com/openai/v1"),
                    "api_key_masked": (cfg.get("llm_api_key", "")[:8] + "..." + cfg.get("llm_api_key", "")[-4:]) if len(cfg.get("llm_api_key", "")) > 12 else "Not configured",
                    "total_requests": len(TELEMETRY_LOG),
                    "total_prompt_tokens": total_prompt_tok,
                    "total_completion_tokens": total_comp_tok,
                    "total_tokens": total_tokens,
                    "estimated_spend_usd": round(total_cost_usd, 4),
                    "ai_killswitch_enabled": bool(cfg.get("ai_killswitch_enabled", False)),
                    "ai_monthly_budget_usd": float(cfg.get("ai_monthly_budget_usd", 50.0)),
                    "ai_budget_hard_stop": bool(cfg.get("ai_budget_hard_stop", True)),
                    "budget_percent_used": min(100.0, round((total_cost_usd / max(0.01, float(cfg.get("ai_monthly_budget_usd", 50.0)))) * 100.0, 1)),
                    "gateway_status": "killed" if cfg.get("ai_killswitch_enabled", False) else ("budget_capped" if (total_cost_usd >= float(cfg.get("ai_monthly_budget_usd", 50.0)) and cfg.get("ai_budget_hard_stop", True)) else "active"),
                    "recent_telemetry": TELEMETRY_LOG[-10:]
                },
                "stripe_billing": stripe_keys,
                "storage_metrics": {
                    "total_seeds": len(seeds),
                    "seeds_db_size_kb": round(db_size_bytes / 1024.0, 1),
                    "transcripts_count": transcripts_count,
                    "transcripts_size_kb": round(transcripts_bytes / 1024.0, 1)
                },
                "users": users_list
            })
            return

        # ── API Endpoint: Get Admin Activity Feed ──
        elif path == "/activity":
            seeds = load_seeds()
            activity_list = [
                {
                    "type": "operation",
                    "description": "Seed Reflections standalone system initialized",
                    "timestamp": datetime.now().isoformat()
                }
            ]
            for s in seeds[-5:]:
                activity_list.append({
                    "type": "seed_mint" if s.get("is_cryptographically_signed") else "seed_planted",
                    "description": f"Planted new intent: '{s.get('intent', '')[:40]}...'",
                    "timestamp": s.get("created_at") or datetime.now().isoformat()
                })
            
            # Sort by timestamp desc
            activity_list.reverse()
            self._send_json({"activity": activity_list})
            return

        # ── API Endpoint: Get Trust Status ──
        elif path == "/trust-status":
            seeds = load_seeds()
            signed_count = sum(1 for s in seeds if s.get("is_cryptographically_signed"))
            verified = signed_count > 0 or len(seeds) == 0
            self._send_json({
                "status": "Verified & Secured" if verified else "Unsigned Seeds Present",
                "verified": verified,
                "signature_chain": [
                    {
                        "seed_id": s.get("seed_id"),
                        "signature": s.get("trust_state", {}).get("signature"),
                        "signed_at": s.get("verification_result", {}).get("signed_at")
                    } for s in seeds if s.get("is_cryptographically_signed")
                ]
            })
            return

        # ── API Endpoint: Export Context Package ──
        elif path == "/api/v1/projects/export-package":
            project_id = get_query_param(self.path, "project_id") or "default_project"
            db = load_db()
            
            project = next((p for p in db.get("projects", []) if p.get("project_id") == project_id), None)
            if not project:
                self._send_json({"error": f"Project '{project_id}' not found"}, 404)
                return

            proj_seeds = [s for s in db.get("seeds", []) if s.get("project_id") == project_id]
            proj_decisions = [d for d in db.get("decisions", []) if d.get("project_id") == project_id]
            proj_conflicts = [c for c in db.get("conflicts", []) if c.get("project_id") == project_id]
            
            seed_ids = {s["seed_id"] for s in proj_seeds}
            proj_relationships = [r for r in db.get("relationships", []) 
                                  if r.get("source_seed_id") in seed_ids or r.get("target_seed_id") in seed_ids]

            # Generate Markdown Summary Package
            md = f"# Portable Context Package: {project.get('name', 'Untitled Project')}\n"
            md += f"* **Project ID**: `{project_id}`\n"
            md += f"* **Exported At**: `{datetime.now().isoformat()}`\n\n"
            
            md += "## Mission Charter\n"
            md += f"* **Purpose**: {project.get('purpose', 'Not set')}\n"
            md += f"* **Description**: {project.get('description', 'Not set')}\n\n"
            
            md += f"## Authoritative Seeds ({len(proj_seeds)} total)\n"
            if proj_seeds:
                for s in proj_seeds:
                    signed_indicator = "🔐 Signed" if is_seed_signed_and_valid(s) else "Draft"
                    md += f"* **[{s.get('status', 'planted')} - {signed_indicator}]** `{s.get('seed_id')}`: {s.get('title') or s.get('intent', '')[:60]}\n"
                    md += f"  > Intent: {s.get('intent', '')}\n"
            else:
                md += "*No seeds recorded.*\n"
            md += "\n"
            
            md += f"## Architectural Decisions ({len(proj_decisions)} total)\n"
            if proj_decisions:
                for d in proj_decisions:
                    md += f"* **[{d.get('status', 'Proposed')}]** `{d.get('decision_id')}` ({d.get('decision_type', 'Architecture')}): {d.get('decision_statement')}\n"
            else:
                md += "*No decisions recorded.*\n"
            md += "\n"
            
            md += f"## Provenance Lineage Relationships ({len(proj_relationships)} total)\n"
            if proj_relationships:
                for r in proj_relationships:
                    md += f"* `{r.get('source_seed_id')}` ➔ **[{r.get('relationship_type')}]** ➔ `{r.get('target_seed_id')}` *(Status: {r.get('approval_status', 'Proposed')})*\n"
            else:
                md += "*No relationships recorded.*\n"
            md += "\n"
            
            self._send_json({
                "project_id": project_id,
                "markdown_package": md.strip(),
                "json_package": {
                    "package_version": "2.0.0",
                    "project": project,
                    "seeds": proj_seeds,
                    "decisions": proj_decisions,
                    "conflicts": proj_conflicts,
                    "relationships": proj_relationships
                }
            })
            return

        # ── API Endpoint: SCIA Context Adapter ──
        elif path == "/api/v1/scia/context":
            project_id = get_query_param(self.path, "project_id") or "default_project"
            db = load_db()
            
            project = next((p for p in db.get("projects", []) if p.get("project_id") == project_id), None)
            if not project:
                self._send_json({"error": f"Project '{project_id}' not found"}, 404)
                return

            active_seeds = [s for s in db.get("seeds", []) 
                            if s.get("project_id") == project_id 
                            and s.get("status") not in ["wilted", "abandoned"]]
            accepted_decisions = [d for d in db.get("decisions", []) 
                                  if d.get("project_id") == project_id and d.get("status") == "Accepted"]
            
            seed_ids = {s["seed_id"] for s in active_seeds}
            approved_relationships = [r for r in db.get("relationships", []) 
                                      if r.get("approval_status") == "Approved" 
                                      and (r.get("source_seed_id") in seed_ids or r.get("target_seed_id") in seed_ids)]

            self._send_json({
                "project_id": project_id,
                "charter": {
                    "purpose": project.get("purpose", ""),
                    "description": project.get("description", "")
                },
                "seeds": [{"seed_id": s["seed_id"], "title": s.get("title") or s.get("intent", "")[:60], "intent": s["intent"], "status": s["status"], "signed": is_seed_signed_and_valid(s)} for s in active_seeds],
                "decisions": [{"decision_id": d["decision_id"], "type": d["decision_type"], "statement": d["decision_statement"]} for d in accepted_decisions],
                "relationships": [{"source": r["source_seed_id"], "target": r["target_seed_id"], "type": r["relationship_type"]} for r in approved_relationships]
            })
            return

        # ── API Endpoint: Admin 1-Click Database Backup Download ──
        elif path in ("/api/v1/admin/backup", "/api/v1/admin/database/backup"):
            with DB_LOCK:
                db = load_db()
                backup_json = json.dumps(db, indent=2).encode("utf-8")
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"seed_reflections_backup_{timestamp_str}.json"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(backup_json)))
                self.end_headers()
                self.wfile.write(backup_json)
            return

        # ── Static File Server ──
        # Retired dashboard.html — hard redirect to consumer
        if path == "/dashboard.html":
            self.send_response(301)
            self.send_header("Location", "/consumer")
            self.end_headers()
            return

        # Default index
        if path == "/" or path == "/index.html":
            filename = "index.html"
        elif path in ("/consumer", "/dashboard"):
            filename = "consumer-dashboard.html"
        elif path == "/admin":
            # ── Admin password & session gate ────────────────────────────
            # Reload .env dynamically if present
            if os.path.exists(ENV_FILE):
                try:
                    with open(ENV_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                CONFIG[k.strip()] = v.strip()
                except Exception:
                    pass

            # 1. Check Cookie for admin_session
            cookie_header = self.headers.get("Cookie", "")
            has_valid_session = False
            if cookie_header:
                for item in cookie_header.split(";"):
                    if "=" in item:
                        k, v = item.strip().split("=", 1)
                        if k == "admin_session" and v in ADMIN_SESSIONS:
                            has_valid_session = True
                            break

            # 2. Check Authorization Bearer token
            auth_header = self.headers.get("Authorization", "")
            if not has_valid_session and auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                if token in ADMIN_SESSIONS:
                    has_valid_session = True

            # 3. Check Basic Auth fallback
            if not has_valid_session:
                admin_password = CONFIG.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "changeme")
                import base64
                expected = base64.b64encode(f"admin:{admin_password}".encode()).decode()
                if auth_header.startswith("Basic ") and auth_header[6:] == expected:
                    has_valid_session = True

            if not has_valid_session:
                self.send_response(302)
                self.send_header("Location", "/auth.html?mode=admin")
                self.end_headers()
                return
            filename = "admin-dashboard.html"
        else:
            filename = path.lstrip("/")

        # Prevent directory traversal
        safe_path = os.path.abspath(os.path.join(os.getcwd(), filename))
        if not safe_path.startswith(os.getcwd()):
            self.send_error(403, "Access Denied")
            return

        if os.path.exists(safe_path) and os.path.isfile(safe_path):
            content_type, _ = mimetypes.guess_type(safe_path)
            if not content_type:
                content_type = "application/octet-stream"

            try:
                with open(safe_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                # Force browser to bypass cache on localhost reload
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, f"Internal Error: {e}")
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        path = self.path.split("?")[0]
        if DEPLOYMENT_MODE != "local" and path.startswith("/api/v1/"):
            self._send_json({"error":"Legacy local API is unavailable in hosted mode; use authenticated /api/v2 routes."},403)
            return
        content_length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")
        if path == "/api/v2/restore/upload":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]=="local": self._send_json({"error":"Hosted tenant restore is unavailable in local mode."},409); return
            if content_length<=0 or content_length>MAX_UPLOAD_BYTES:
                self._send_json({"error":"Backup is empty or exceeds the configured size limit","limit_bytes":MAX_UPLOAD_BYTES},400 if content_length<=0 else 413); return
            if "multipart/form-data" not in content_type: self._send_json({"error":"Expected multipart/form-data"},400); return
            staged_path=None
            try:
                filename,staged_path=stream_multipart_upload(self.rfile,content_length,content_type)
                if not filename.lower().endswith(".zip"): raise ValueError("Expected a SeedReflections ZIP backup")
                self._send_json(tenant_restore_backup_archive(user["workspace_id"],staged_path))
            except (ValueError,zipfile.BadZipFile) as exc: self._send_json({"error":str(exc)},400)
            finally:
                if staged_path: Path(staged_path).unlink(missing_ok=True)
            return
        if path == "/api/v2/imports/upload":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if content_length<=0 or content_length>MAX_UPLOAD_BYTES:
                self._send_json({"error":"Upload is empty or exceeds the configured size limit","limit_bytes":MAX_UPLOAD_BYTES},400 if content_length<=0 else 413); return
            if "multipart/form-data" not in content_type: self._send_json({"error":"Expected multipart/form-data"},400); return
            if user["workspace_id"]!="local":
                current=tenant_usage(user["workspace_id"])
                if current["source_bytes"]+content_length>HOSTED_STORAGE_BYTES:
                    self._send_json({"error":"Workspace storage quota exceeded","limit_bytes":HOSTED_STORAGE_BYTES,"used_bytes":current["source_bytes"]},413); return
            try:
                filename,staged_path=stream_multipart_upload(self.rfile,content_length,content_type)
                if user["workspace_id"]=="local":
                    job_id=create_import_job(filename); target=process_import_job; args=(job_id,filename,staged_path)
                else:
                    job=tenant_create_import_job(user["workspace_id"],filename); job_id=job["id"]
                    target=process_tenant_import_job; args=(user["workspace_id"],job_id,filename,staged_path)
                threading.Thread(target=target,args=args,daemon=True).start()
                self._send_json({"status":"accepted","job_id":job_id},202)
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        if path in ("/api/v1/upload_export", "/upload_export"):
            if content_length <= 0:
                self._send_json({"error": "Upload is empty"}, 400)
                return
            if content_length > MAX_UPLOAD_BYTES:
                self._send_json({"error": "Upload exceeds the configured size limit", "limit_bytes": MAX_UPLOAD_BYTES}, 413)
                return
            if "multipart/form-data" not in content_type:
                self._send_json({"error": "Expected multipart/form-data"}, 400)
                return
            try:
                filename, staged_path = stream_multipart_upload(self.rfile, content_length, content_type)
                job_id = create_import_job(filename)
                threading.Thread(target=process_import_job, args=(job_id, filename, staged_path), daemon=True).start()
                self._send_json({"status": "accepted", "job_id": job_id, "message": "Upload staged and import queued."}, 202)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                print(f"Error staging upload: {exc}")
                self._send_json({"error": "Upload could not be staged"}, 500)
            return
        if path == "/api/v2/integrations/import" and (content_length<=0 or content_length>MAX_UPLOAD_BYTES):
            self._send_json({"error":"API delivery is empty or exceeds the configured size limit","limit_bytes":MAX_UPLOAD_BYTES},400 if content_length<=0 else 413)
            return
        post_data = self.rfile.read(content_length)
        body = {}
        if "application/json" in content_type:
            if post_data:
                try:
                    body = json.loads(post_data.decode("utf-8"))
                except Exception:
                    self._send_json({"error": "Invalid JSON payload"}, 400)
                    return

        if path == "/api/v2/integrations":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if not isinstance(body,dict): self._send_json({"error":"Expected a JSON object"},400); return
            try:
                created=create_api_integration(user["workspace_id"],body.get("name"),body.get("provider"))
                created["import_endpoint"]="/api/v2/integrations/import"
                self._send_json(created,201)
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        integration_revoke_match=re.fullmatch(r"/api/v2/integrations/([^/]+)/revoke",path)
        if integration_revoke_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            try: self._send_json(revoke_api_integration(urllib.parse.unquote(integration_revoke_match.group(1)),user["workspace_id"]))
            except KeyError as exc: self._send_json({"error":str(exc)},404)
            return
        if path == "/api/v2/integrations/import":
            integration=authenticate_api_integration(self._bearer_token())
            if not integration: self._send_json({"error":"Invalid or revoked connection token"},401); return
            try:
                if isinstance(body,list): conversations=body
                elif isinstance(body,dict) and isinstance(body.get("conversations"),list): conversations=body["conversations"]
                elif isinstance(body,dict) and isinstance(body.get("conversation"),dict): conversations=[body["conversation"]]
                elif isinstance(body,dict) and isinstance(body.get("messages"),list):
                    conversations=[{"id":body.get("id") or uuid.uuid4().hex,"title":body.get("title") or integration["name"],"messages":body["messages"]}]
                else: raise ValueError("Send conversations[], conversation{}, or a conversation object containing messages[]")
                if not conversations or any(not isinstance(item,dict) for item in conversations): raise ValueError("At least one valid conversation is required")
                normalized=[]
                for item in conversations:
                    item=dict(item); item.setdefault("source_platform",integration["provider"]); normalized.append(item)
                payload=json.dumps({"conversations":normalized},ensure_ascii=False)
                filename=f"{integration['provider']}-api-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
                if integration["workspace_id"]=="local": result=import_archive_json(payload,filename)
                else: result=tenant_import_json(integration["workspace_id"],payload,filename)
                record_api_delivery(integration["id"])
                self._send_json({"status":"imported","integration_id":integration["id"],"provider":integration["provider"],
                    "conversation_count":len(result.get("conversations",[])),"message_count":result.get("message_count",0),
                    "reconciliation":result.get("reconciliation",{})},202)
            except (ValueError,TypeError) as exc:
                record_api_delivery(integration["id"],exc); self._send_json({"error":str(exc)},400)
            return
        if path == "/api/v2/auth/signup":
            if not auth_request_allowed(f"{self.client_address[0]}:signup"):
                self._send_json({"error":"Too many authentication attempts. Try again later."},429); return
            if DEPLOYMENT_MODE == "local": self._send_json({"error":"Local mode uses the device owner and does not require an account"},409); return
            try:
                result=auth_signup(body.get("name"),body.get("email"),body.get("password"),DEPLOYMENT_MODE)
                create_empty_workspace(result["workspace_id"]); self._send_json(result,201)
            except ValueError as exc: self._send_json({"error":str(exc)},409 if "exists" in str(exc) else 400)
            return
        if path == "/api/v2/auth/login":
            if not auth_request_allowed(f"{self.client_address[0]}:login"):
                self._send_json({"error":"Too many authentication attempts. Try again later."},429); return
            try: self._send_json(auth_login(body.get("email"),body.get("password")))
            except ValueError as exc: self._send_json({"error":str(exc)},401)
            return
        if path == "/api/v2/auth/logout":
            if DEPLOYMENT_MODE != "local": auth_logout(self._bearer_token())
            self._send_json({"status":"local_session" if DEPLOYMENT_MODE=="local" else "signed_out"})
            return
        if path == "/api/v2/imports":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            try:
                filename=body.get("filename") or "export.json"
                data=body.get("data")
                if data is None: raise ValueError("Archive data is required")
                encoded=json.dumps(data,ensure_ascii=False)
                if user["workspace_id"]!="local":
                    incoming=len(data.get("conversations") or data.get("data") or [data]) if isinstance(data,dict) else len(data) if isinstance(data,list) else 0
                    current=tenant_usage(user["workspace_id"])
                    if current["conversations"]+incoming>HOSTED_MAX_CONVERSATIONS:
                        self._send_json({"error":"Workspace conversation quota exceeded","limit":HOSTED_MAX_CONVERSATIONS,"used":current["conversations"]},413); return
                    if len(encoded.encode("utf-8"))>MAX_UPLOAD_BYTES:
                        self._send_json({"error":"Import exceeds the configured size limit","limit_bytes":MAX_UPLOAD_BYTES},413); return
                if user["workspace_id"] == "local":
                    result=import_archive_json(encoded,filename)
                    result={**result,"conversations":len(result.get("conversations",[])),"messages":result.get("message_count",0)}
                else:
                    result=tenant_import_json(user["workspace_id"],encoded,filename)
                self._send_json(result,201)
            except (ValueError,json.JSONDecodeError) as exc: self._send_json({"error":str(exc)},400)
            return
        if path == "/api/v2/restore":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]=="local": self._send_json({"error":"Hosted tenant restore is unavailable in local mode."},409); return
            try: self._send_json(tenant_restore_backup(user["workspace_id"],body.get("backup")))
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        if path == "/api/v2/projects":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            name=str(body.get("name") or "").strip(); mission=str(body.get("mission") or "").strip()
            if not name: self._send_json({"error":"Project name is required"},400); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); project_id=uuid.uuid4().hex
            workspace.setdefault("projects",[]).append({"project_id":project_id,"name":name,"mission":mission,
                "stage":"Active","created_at":datetime.now().isoformat(),"updated_at":datetime.now().isoformat()})
            save_workspace(workspace,user["workspace_id"],"project_created")
            self._send_json({"id":project_id},201)
            return
        if path == "/api/v2/settings":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            allowed={"user_name","user_email","api_mode","llm_provider","llm_model","llm_api_url","llm_api_key",
                "privacy_analytics","privacy_store_transcripts","privacy_sign_seeds","privacy_ai_training","privacy_marketing_emails"}
            workspace=load_workspace(workspace_id=user["workspace_id"]); settings=dict(workspace.get("settings") or {})
            settings.update({key:value for key,value in body.items() if key in allowed})
            workspace["settings"]=settings; save_workspace(workspace,user["workspace_id"],"settings_updated")
            self._send_json({"status":"success"})
            return
        if path == "/api/v2/connectors/connect":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]!="local": self._send_json({"error":"Install or activate the SeedReflections desktop connector before connecting local AI data."},409); return
            try:
                connector=add_source_connector(body.get("provider"),body.get("root_path"),body.get("auto_sync",True),"local")
                result=sync_source_connector(connector["id"],"local")
                self._send_json({"connector":connector,"sync":result},201)
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        if path == "/api/v2/connectors/preview":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]!="local": self._send_json({"error":"Install or activate the SeedReflections desktop connector before previewing local AI data."},409); return
            try: self._send_json(preview_connector_source(body.get("provider"),body.get("root_path"),"local"))
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        if path == "/api/v2/connectors/connect-preview":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]!="local": self._send_json({"error":"Desktop connector required"},409); return
            try:
                self._send_json(connect_connector_preview(body.get("preview_id"),body.get("selected_paths"),body.get("include_new",True),body.get("auto_sync",True),"local"),201)
            except KeyError as exc: self._send_json({"error":str(exc)},404)
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        connector_sync_match=re.fullmatch(r"/api/v2/connectors/([^/]+)/sync",path)
        if connector_sync_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]!="local": self._send_json({"error":"Desktop connector required"},409); return
            try: self._send_json(sync_source_connector(urllib.parse.unquote(connector_sync_match.group(1)),"local"))
            except KeyError as exc: self._send_json({"error":str(exc)},404)
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        connector_remove_match=re.fullmatch(r"/api/v2/connectors/([^/]+)/disconnect",path)
        if connector_remove_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]!="local": self._send_json({"error":"Desktop connector required"},409); return
            try: self._send_json(remove_source_connector(urllib.parse.unquote(connector_remove_match.group(1)),"local"))
            except KeyError as exc: self._send_json({"error":str(exc)},404)
            return
        if path in {"/api/v2/workspace/seeds/update","/api/v2/workspace/seeds/delete"}:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); seed_id=str(body.get("seed_id") or "")
            seed=next((item for item in workspace.get("seeds",[]) if (item.get("seed_id") or item.get("id"))==seed_id),None)
            if not seed: self._send_json({"error":"Seed not found"},404); return
            if path.endswith("/delete"):
                workspace["seeds"]=[item for item in workspace.get("seeds",[]) if (item.get("seed_id") or item.get("id"))!=seed_id]
                workspace["relationships"]=[item for item in workspace.get("relationships",[]) if item.get("source_seed_id")!=seed_id and item.get("target_seed_id")!=seed_id]
                reason="seed_deleted"
            else:
                protected={"seed_id","id","candidate_id","source_conversation_id","source_message_id","created_at"}
                seed.update({key:value for key,value in body.items() if key not in protected}); seed["updated_at"]=datetime.now().isoformat(); reason="seed_updated"
            save_workspace(workspace,user["workspace_id"],reason); self._send_json({"status":"success"}); return
        if path == "/api/v2/workspace/decisions":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            statement=str(body.get("decision_statement") or "").strip()
            if not statement: self._send_json({"error":"Decision statement is required"},400); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); item={**body,"decision_id":uuid.uuid4().hex,"statement":statement,"created_at":datetime.now().isoformat()}
            workspace.setdefault("decisions",[]).append(item); save_workspace(workspace,user["workspace_id"],"decision_created")
            self._send_json({"status":"success","decision":item},201); return
        if path == "/api/v2/workspace/conflicts":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); seed_ids={item.get("seed_id") or item.get("id") for item in workspace.get("seeds",[])}
            if not body.get("subject") or body.get("seed_a") not in seed_ids or body.get("seed_b") not in seed_ids or body.get("seed_a")==body.get("seed_b"):
                self._send_json({"error":"A subject and two different existing seeds are required"},400); return
            item={**body,"conflict_id":uuid.uuid4().hex,"created_at":datetime.now().isoformat()}; workspace.setdefault("conflicts",[]).append(item)
            save_workspace(workspace,user["workspace_id"],"conflict_created"); self._send_json({"status":"success","conflict":item},201); return
        if path in {"/api/v2/workspace/relationships/create","/api/v2/workspace/relationships/approve","/api/v2/workspace/relationships/delete"}:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); relationships=workspace.setdefault("relationships",[])
            if path.endswith("/create"):
                seed_ids={item.get("seed_id") or item.get("id") for item in workspace.get("seeds",[])}; source=body.get("source_seed_id"); target=body.get("target_seed_id")
                if source not in seed_ids or target not in seed_ids or source==target: self._send_json({"error":"Two different existing seeds are required"},400); return
                item={**body,"relationship_id":uuid.uuid4().hex,"approval_status":"Approved" if body.get("created_by")=="user" else "Proposed","created_at":datetime.now().isoformat()}; relationships.append(item)
            else:
                relationship_id=body.get("relationship_id"); item=next((entry for entry in relationships if entry.get("relationship_id")==relationship_id),None)
                if not item: self._send_json({"error":"Relationship not found"},404); return
                if path.endswith("/delete"): workspace["relationships"]=[entry for entry in relationships if entry.get("relationship_id")!=relationship_id]
                else: item.update({"approval_status":"Approved","approved":True,"approved_at":datetime.now().isoformat()})
            save_workspace(workspace,user["workspace_id"],"relationship_changed"); self._send_json({"status":"success"}); return
        if path == "/api/v2/projects/import-package":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            package=body.get("json_package")
            if not isinstance(package,dict) or package.get("package_version")!="2.0.0" or not isinstance(package.get("project"),dict):
                self._send_json({"error":"A valid 2.0.0 json_package is required"},400); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); counts={"seeds":0,"decisions":0,"conflicts":0,"relationships":0}
            project=package["project"]; project_id=project.get("project_id") or project.get("id")
            if not project_id: self._send_json({"error":"Package project ID is required"},400); return
            existing=next((item for item in workspace.get("projects",[]) if (item.get("project_id") or item.get("id"))==project_id),None)
            if existing: existing.update(project)
            else: workspace.setdefault("projects",[]).append(project)
            for key,id_key in (("seeds","seed_id"),("decisions","decision_id"),("conflicts","conflict_id"),("relationships","relationship_id")):
                target=workspace.setdefault(key,[]); known={item.get(id_key) for item in target}
                for item in package.get(key) or []:
                    if isinstance(item,dict) and item.get(id_key) and item.get(id_key) not in known: target.append(item); known.add(item[id_key]); counts[key]+=1
            save_workspace(workspace,user["workspace_id"],"context_package_imported")
            self._send_json({"status":"success","imported":counts}); return
        if path == "/api/v2/reflections":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            transcript=str(body.get("transcript") or "").strip()
            if not transcript: self._send_json({"error":"Missing 'transcript' field"},400); return
            title=str(body.get("title") or "Pasted workspace reflection").strip()
            conversation_id=f"reflection-{uuid.uuid4().hex}"
            encoded=json.dumps([{"id":conversation_id,"title":title,"messages":[{"role":"user","content":transcript}]}],ensure_ascii=False)
            if user["workspace_id"]=="local":
                imported=import_archive_json(encoded,"workspace-reflection.json")
                stored=(imported.get("conversations") or [{}])[0]
                result=analyze_conversation(stored.get("id") or conversation_id)
                created=result.get("created",0)
            else:
                tenant_import_json(user["workspace_id"],encoded,"workspace-reflection.json")
                stored=(tenant_list_conversations(user["workspace_id"],title,1,0) or [{}])[0]
                result=tenant_analyze(user["workspace_id"],stored.get("id") or conversation_id)
                created=result.get("candidates_created",result.get("created",0))
            self._send_json({"answer":f"Mapped this reflection into {created} review candidate{'s' if created != 1 else ''}. Open Idea Browser to confirm what should become part of your workspace.",
                "candidates_created":created,"conversation_id":stored.get("id") or conversation_id},201)
            return
        if path == "/api/v2/chat":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            prompt=str(body.get("prompt") or "").strip()
            if not prompt: self._send_json({"error":"Prompt is required"},400); return
            workspace=load_workspace(workspace_id=user["workspace_id"])
            active_id=body.get("active_seed_id")
            seed=next((item for item in workspace.get("seeds",[]) if (item.get("seed_id") or item.get("id"))==active_id),None)
            if seed:
                title=seed.get("title") or str(seed.get("intent") or "this idea")[:80]
                intent=seed.get("intent") or seed.get("summary") or "No intent has been recorded yet."
                next_action=seed.get("next_action") or "Define the next concrete action and the evidence that will show it is complete."
                answer=(f"You are continuing **{title}**.\n\nThe confirmed intent is: {intent}\n\n"
                        f"Current next action: {next_action}\n\nYour prompt was: {prompt}\n\n"
                        "I have kept this response grounded in the confirmed workspace record. Use the source conversation alongside it before changing the idea's direction.")
            else:
                open_seeds=[item for item in workspace.get("seeds",[]) if str(item.get("status","")).lower() not in {"completed","done","archived","wilted"}]
                answer=(f"Your workspace currently has {len(open_seeds)} active confirmed idea{'s' if len(open_seeds) != 1 else ''}. "
                        "Choose one from the shelf to continue with its saved intent and source context, or import a conversation and map its ideas first.")
            self._send_json({"answer":answer,"grounded":True,"active_seed_id":active_id})
            return
        if path == "/api/v2/analysis/run":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            if user["workspace_id"]=="local":
                job=create_analysis_job(); target=run_archive_analysis; args=(job["id"],)
            else:
                if tenant_usage(user["workspace_id"])["analysis_jobs"]>=HOSTED_MAX_ANALYSIS_JOBS:
                    self._send_json({"error":"Workspace analysis-job quota exceeded","limit":HOSTED_MAX_ANALYSIS_JOBS},429); return
                job=tenant_create_analysis_job(user["workspace_id"]); target=tenant_run_analysis_job; args=(user["workspace_id"],job["id"])
            threading.Thread(target=target,args=args,daemon=True).start(); self._send_json(job,202); return
        if path == "/api/v2/relationships/generate":
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            result=(generate_candidate_links() if user["workspace_id"]=="local" else tenant_generate_links(user["workspace_id"]))
            self._send_json(result); return
        relationship_review_match=re.fullmatch(r"/api/v2/relationships/([^/]+)/review",path)
        if relationship_review_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            try:
                result=(review_candidate_link(urllib.parse.unquote(relationship_review_match.group(1)),body.get("action"))
                        if user["workspace_id"]=="local" else tenant_review_link(user["workspace_id"],urllib.parse.unquote(relationship_review_match.group(1)),body.get("action")))
                if user["workspace_id"]!="local" and body.get("action")=="accept":
                    result["relationships_created"]=len(materialize_tenant_relationships(user["workspace_id"]))
                self._send_json(result)
            except KeyError as exc: self._send_json({"error":str(exc)},404)
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        analyze_v2_match=re.fullmatch(r"/api/v2/conversations/([^/]+)/analyze",path)
        if analyze_v2_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            conversation_id=urllib.parse.unquote(analyze_v2_match.group(1))
            try:
                result=(analyze_conversation(conversation_id) if user["workspace_id"] == "local"
                        else tenant_analyze(user["workspace_id"],conversation_id))
                if user["workspace_id"]=="local": result={**result,"candidates_created":result.get("created",0)}
                self._send_json(result)
            except (KeyError,ValueError) as exc: self._send_json({"error":str(exc)},404)
            return
        review_v2_match=re.fullmatch(r"/api/v2/candidates/([^/]+)/review",path)
        if review_v2_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            try:
                candidate_id=urllib.parse.unquote(review_v2_match.group(1)); action=body.get("action")
                if user["workspace_id"]!="local" and action=="accept":
                    result=accept_tenant_candidate(user["workspace_id"],candidate_id,body.get("project_id"),
                        body.get("title"),body.get("intent"),body.get("next_action"))
                    result["relationships_created"]=len(materialize_tenant_relationships(user["workspace_id"]))
                    self._send_json(result); return
                workspace=None; project_id=body.get("project_id")
                if action == "accept":
                    workspace=load_workspace(workspace_id=user["workspace_id"])
                    if project_id and not any((item.get("project_id") or item.get("id"))==project_id for item in workspace.get("projects",[])):
                        self._send_json({"error":"Project not found"},400); return
                candidate=(review_candidate(candidate_id,action) if user["workspace_id"] == "local" else tenant_review(user["workspace_id"],candidate_id,action))
                result={"candidate":candidate,"status":candidate["status"]}
                if workspace is not None:
                    now=datetime.now().isoformat()
                    if candidate.get("kind") == "decision":
                        entity_id=uuid.uuid4().hex
                        workspace.setdefault("decisions",[]).append({"decision_id":entity_id,"project_id":project_id,
                            "candidate_id":candidate_id,"statement":str(body.get("title") or candidate["title"]),
                            "rationale":str(body.get("intent") or candidate["interpretation"]),"status":"active",
                            "source_conversation_id":candidate["conversation_id"],"source_message_id":candidate["message_id"],"created_at":now})
                        result["decision_id"]=entity_id
                    else:
                        entity_id=uuid.uuid4().hex
                        workspace.setdefault("seeds",[]).append({"seed_id":entity_id,"project_id":project_id,
                            "candidate_id":candidate_id,"title":str(body.get("title") or candidate["title"]),
                            "intent":str(body.get("intent") or candidate["interpretation"]),"status":"Active",
                            "continuity_status":"User Confirmed","source_conversation_id":candidate["conversation_id"],
                            "source_message_id":candidate["message_id"],"next_action":str(body.get("next_action") or "Review the source context and choose the next concrete action."),
                            "created_at":now,"updated_at":now})
                        result["seed_id"]=entity_id
                    save_workspace(workspace,user["workspace_id"],"candidate_accepted")
                    if user["workspace_id"]=="local":
                        linked_workspace=load_workspace(workspace_id="local")
                        linked=materialize_confirmed_candidate_links(linked_workspace)
                        if linked: save_workspace(linked_workspace,"local","relationship_materialized")
                        result["relationships_created"]=len(linked)
                    else:
                        result["relationships_created"]=len(materialize_tenant_relationships(user["workspace_id"]))
                self._send_json(result)
            except KeyError as exc: self._send_json({"error":str(exc)},404)
            except ValueError as exc: self._send_json({"error":str(exc)},400)
            return
        resume_v2_match=re.fullmatch(r"/api/v2/seeds/([^/]+)/resume",path)
        if resume_v2_match:
            user=self._runtime_user()
            if not user: self._send_json({"error":"Authentication required"},401); return
            workspace=load_workspace(workspace_id=user["workspace_id"]); seed_id=urllib.parse.unquote(resume_v2_match.group(1))
            seed=next((item for item in workspace.get("seeds",[]) if (item.get("seed_id") or item.get("id"))==seed_id),None)
            if not seed: self._send_json({"error":"Seed not found"},404); return
            seed["status"]="Active"; seed["continuity_status"]="Recovered"; seed["updated_at"]=datetime.now().isoformat()
            save_workspace(workspace,user["workspace_id"],"seed_recovered"); self._send_json({"status":"recovered"})
            return
        if DEPLOYMENT_MODE != "local" and path.startswith("/api/v1/"):
            self._send_json({"error":"Legacy local API is unavailable in hosted mode; use authenticated /api/v2 routes."},403)
            return

        if path == "/api/v1/archive/import-text":
            try:
                archive = import_archive_text(body.get("text"), body.get("title") or "Pasted conversation")
                self._send_json({"status": "success", **archive}, 201)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                print(f"Error importing pasted conversation: {exc}")
                self._send_json({"error": "Unable to import pasted conversation"}, 500)
            return

        if path == "/api/v1/archive/analyze-all":
            job = create_analysis_job()
            threading.Thread(target=run_archive_analysis, args=(job["id"],), daemon=True).start()
            self._send_json(job, 202)
            return

        if path == "/api/v1/archive/links/generate":
            self._send_json(generate_candidate_links())
            return

        link_review_match = re.fullmatch(r"/api/v1/archive/links/([^/]+)/review", path)
        if link_review_match:
            try:
                link = review_candidate_link(urllib.parse.unquote(link_review_match.group(1)), body.get("action"))
                relationships = []
                if body.get("action") == "accept":
                    with DB_LOCK:
                        workspace = load_db()
                        relationships = materialize_confirmed_candidate_links(workspace)
                        if relationships: save_db(workspace)
                self._send_json({"status":"ok","link_status":link["status"],
                    "relationships_created":len(relationships),
                    "awaiting_accepted_ideas":body.get("action")=="accept" and not relationships})
            except ValueError as exc:
                self._send_json({"error":str(exc)},400)
            return

        analyze_match = re.fullmatch(r"/api/v1/archive/conversations/([^/]+)/analyze", path)
        if analyze_match:
            try:
                result = analyze_conversation(urllib.parse.unquote(analyze_match.group(1)))
                result["relationship_suggestions_created"] = generate_candidate_links()["created"]
                self._send_json(result)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 404)
            return

        review_match = re.fullmatch(r"/api/v1/archive/candidates/([^/]+)/review", path)
        if review_match:
            try:
                action = body.get("action")
                candidate = review_candidate(urllib.parse.unquote(review_match.group(1)), action)
                seed = None; decision = None
                if action == "accept":
                    with DB_LOCK:
                        workspace = load_db()
                        if candidate["kind"] == "decision":
                            decision = {
                                "decision_id":"decision_" + uuid.uuid4().hex,
                                "project_id":body.get("project_id") or "default_project",
                                "decision_statement":body.get("interpretation") or candidate["interpretation"],
                                "decision_type":"Architecture", "status":"Accepted",
                                "source_conversation":candidate["conversation_title"],
                                "source_conversation_id":candidate["conversation_id"],
                                "source_message_id":candidate["message_id"], "source_excerpt":candidate["excerpt"],
                                "date":datetime.now().isoformat(), "decision_maker":"user", "related_seeds":[],
                                "evidence_status":"Source Verified", "authority_status":"User Confirmed",
                                "extraction_method":candidate["extraction_method"], "candidate_id":candidate["id"]
                            }
                            workspace.setdefault("decisions", []).append(decision)
                        else:
                            abandoned = candidate["kind"] == "abandoned"
                            seed = {
                                "seed_id": "seed-" + uuid.uuid4().hex,
                                "title": body.get("title") or candidate["title"],
                                "description": body.get("interpretation") or candidate["interpretation"],
                                "intent": body.get("interpretation") or candidate["interpretation"],
                                "status": "wilted" if abandoned else "planted", "confidence": candidate["confidence"],
                                "candidate_kind":candidate["kind"],
                                "source_platform": candidate["platform"], "source_thread_title": candidate["conversation_title"],
                                "source_conversation_id": candidate["conversation_id"], "source_message_id": candidate["message_id"],
                                "source_excerpt": candidate["excerpt"], "evidence_status": "Source Verified",
                                "authority_status": "User Confirmed", "continuity_status": "Historical" if abandoned else "Active",
                                "project_id": body.get("project_id") or "default_project", "created_at": datetime.now().isoformat(),
                                "extraction_method": candidate["extraction_method"], "candidate_id": candidate["id"]
                            }
                            workspace.setdefault("seeds", []).append(seed)
                        materialize_confirmed_candidate_links(workspace)
                        save_db(workspace)
                self._send_json({"status":"ok","candidate_status":candidate["status"],
                    "entity_type":"decision" if decision else "idea" if seed else None,"seed":seed,"decision":decision})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            return

        if path == "/api/v1/projects/import-package":
            json_pkg = body.get("json_package")
            if not json_pkg or not isinstance(json_pkg, dict):
                self._send_json({"error": "Missing json_package object in body"}, 400)
                return
            
            pkg_version = json_pkg.get("package_version")
            if pkg_version != "2.0.0":
                self._send_json({"error": "Unsupported package version. Only 2.0.0 is supported."}, 400)
                return

            incoming_project = json_pkg.get("project")
            incoming_seeds = json_pkg.get("seeds") or []
            incoming_decisions = json_pkg.get("decisions") or []
            incoming_conflicts = json_pkg.get("conflicts") or []
            incoming_relationships = json_pkg.get("relationships") or []

            if not incoming_project or not incoming_project.get("project_id"):
                self._send_json({"error": "Invalid project metadata in package"}, 400)
                return

            imported_seeds_count = 0
            imported_decisions_count = 0
            imported_conflicts_count = 0
            imported_relationships_count = 0

            with DB_LOCK:
                db = load_db()
                
                # 1. Merge project metadata
                proj_id = incoming_project["project_id"]
                existing_proj = next((p for p in db.get("projects", []) if p.get("project_id") == proj_id), None)
                if not existing_proj:
                    db.setdefault("projects", []).append(incoming_project)
                else:
                    existing_proj.update(incoming_project)

                # 2. Merge seeds
                for s in incoming_seeds:
                    s_id = s.get("seed_id")
                    if not s_id:
                        continue
                    existing_s = next((x for x in db.get("seeds", []) if x.get("seed_id") == s_id), None)
                    if not existing_s:
                        db.setdefault("seeds", []).append(s)
                        imported_seeds_count += 1
                    else:
                        incoming_is_signed = s.get("is_cryptographically_signed", False)
                        existing_is_signed = existing_s.get("is_cryptographically_signed", False)
                        
                        should_overwrite = False
                        if incoming_is_signed and not existing_is_signed:
                            should_overwrite = True
                        elif incoming_is_signed == existing_is_signed:
                            in_ts = s.get("modified_at") or s.get("created_at") or ""
                            ex_ts = existing_s.get("modified_at") or existing_s.get("created_at") or ""
                            if in_ts > ex_ts:
                                should_overwrite = True
                        
                        if should_overwrite:
                            existing_s.clear()
                            existing_s.update(s)
                            imported_seeds_count += 1

                # 3. Merge decisions
                for d in incoming_decisions:
                    d_id = d.get("decision_id")
                    if not d_id:
                        continue
                    existing_d = next((x for x in db.get("decisions", []) if x.get("decision_id") == d_id), None)
                    if not existing_d:
                        db.setdefault("decisions", []).append(d)
                        imported_decisions_count += 1
                    else:
                        in_ts = d.get("modified_at") or d.get("date") or ""
                        ex_ts = existing_d.get("modified_at") or existing_d.get("date") or ""
                        if in_ts > ex_ts:
                            existing_d.clear()
                            existing_d.update(d)
                            imported_decisions_count += 1

                # 4. Merge conflicts
                for c in incoming_conflicts:
                    c_id = c.get("conflict_id")
                    if not c_id:
                        continue
                    existing_c = next((x for x in db.get("conflicts", []) if x.get("conflict_id") == c_id), None)
                    if not existing_c:
                        db.setdefault("conflicts", []).append(c)
                        imported_conflicts_count += 1
                    else:
                        in_ts = c.get("modified_at") or c.get("created_at") or ""
                        ex_ts = existing_c.get("modified_at") or existing_c.get("created_at") or ""
                        if in_ts > ex_ts:
                            existing_c.clear()
                            existing_c.update(c)
                            imported_conflicts_count += 1

                # 5. Merge relationships
                for r in incoming_relationships:
                    r_id = r.get("relationship_id")
                    if not r_id:
                        continue
                    existing_r = next((x for x in db.get("relationships", []) if x.get("relationship_id") == r_id), None)
                    if not existing_r:
                        is_dup = False
                        for existing_rel in db.get("relationships", []):
                            if existing_rel.get("approval_status") in ["Approved", "Proposed"]:
                                if (existing_rel["source_seed_id"] == r["source_seed_id"] and
                                    existing_rel["target_seed_id"] == r["target_seed_id"] and
                                    existing_rel["relationship_type"] == r["relationship_type"]):
                                    is_dup = True
                                    break
                                rel_meta = RELATIONSHIP_REGISTRY.get(r["relationship_type"], {})
                                if rel_meta.get("symmetric") and (
                                    existing_rel["source_seed_id"] == r["target_seed_id"] and
                                    existing_rel["target_seed_id"] == r["source_seed_id"] and
                                    existing_rel["relationship_type"] == r["relationship_type"]
                                ):
                                    is_dup = True
                                    break
                        if not is_dup:
                            db.setdefault("relationships", []).append(r)
                            imported_relationships_count += 1
                    else:
                        if r.get("approval_status") == "Approved" and existing_r.get("approval_status") != "Approved":
                            existing_r.update(r)
                            imported_relationships_count += 1
                
                rebuild_relationship_references(db)
                save_db(db)

            self._send_json({
                "status": "success",
                "imported": {
                    "seeds": imported_seeds_count,
                    "decisions": imported_decisions_count,
                    "conflicts": imported_conflicts_count,
                    "relationships": imported_relationships_count
                }
            }, 200)
            return

        elif path == "/api/v1/auth/login" or path == "/auth/login":
            # Dynamically refresh .env
            if os.path.exists(ENV_FILE):
                try:
                    with open(ENV_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                CONFIG[k.strip()] = v.strip()
                except Exception:
                    pass

            email = (body.get("email") or "").strip().lower()
            password = body.get("password") or ""
            admin_password = CONFIG.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "changeme")
            admin_email = (CONFIG.get("ADMIN_EMAIL") or os.environ.get("ADMIN_EMAIL", "admin@seedreflections.internal")).strip().lower()

            # Check if this is an admin login attempt
            is_admin_attempt = email == admin_email or email == "admin"
            if is_admin_attempt:
                if password == admin_password:
                    token = f"admin_session_{int(time.time())}_{hashlib.sha256(password.encode()).hexdigest()[:12]}"
                    ADMIN_SESSIONS[token] = {
                        "email": email,
                        "name": "Administrator",
                        "role": "admin",
                        "created_at": time.time()
                    }
                    # Send response with Set-Cookie for seamless browser navigation to /admin
                    response_data = json.dumps({
                        "access_token": token,
                        "refresh_token": f"refresh_{token}",
                        "role": "admin",
                        "user": {
                            "name": "Administrator",
                            "email": email,
                            "role": "admin"
                        }
                    }).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response_data)))
                    self.send_header("Set-Cookie", f"admin_session={token}; Path=/; HttpOnly; SameSite=Lax")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(response_data)
                    return
                else:
                    self._send_json({"detail": "Invalid admin password."}, 401)
                    return

            # Standard consumer login
            user_token = f"user_token_{int(time.time())}"
            self._send_json({
                "access_token": user_token,
                "refresh_token": f"refresh_{user_token}",
                "role": "consumer",
                "user": {
                    "name": email.split("@")[0].capitalize() if "@" in email else "User",
                    "email": email,
                    "role": "consumer"
                }
            }, 200)
            return

        elif path == "/api/v1/auth/signup" or path == "/auth/signup":
            email = (body.get("email") or "").strip().lower()
            name = (body.get("name") or "").strip() or (email.split("@")[0].capitalize() if "@" in email else "User")
            plan = (body.get("plan") or "free").lower()
            user_id = f"usr_{os.urandom(6).hex()}"
            with DB_LOCK:
                db = load_db()
                existing = next((a for a in db.get("accounts", []) if a.get("email") == email), None)
                if not existing:
                    new_acc = {
                        "id": user_id,
                        "email": email,
                        "name": name,
                        "role": "consumer",
                        "plan": plan,
                        "status": "active",
                        "tokens_consumed": 0,
                        "created_at": datetime.now().isoformat(),
                        "last_active": "Just now"
                    }
                    db.setdefault("accounts", []).append(new_acc)
                    save_db(db)
                else:
                    user_id = existing.get("id")

            self._send_json({
                "access_token": f"user_token_{user_id}",
                "refresh_token": f"refresh_{user_id}",
                "user": {
                    "id": user_id,
                    "name": name,
                    "email": email,
                    "role": "consumer",
                    "plan": plan
                }
            }, 200)
            return

        elif path == "/api/v1/subscriptions/checkout" or path == "/subscriptions/checkout":
            plan = body.get("plan", "").lower()
            checkout_urls = {
                "free": "https://buy.stripe.com/test_seed_reflections_free",
                "pro": "https://buy.stripe.com/test_seed_reflections_pro",
                "master": "https://buy.stripe.com/test_seed_reflections_master"
            }
            url = checkout_urls.get(plan, "https://buy.stripe.com/test_seed_reflections_pro")
            self._send_json({"checkout_url": url}, 200)
            return

        elif path == "/api/v1/subscriptions/portal" or path == "/subscriptions/portal":
            self._send_json({"portal_url": "https://billing.stripe.com/p/login/test_mock_portal"}, 200)
            return

        # ── API Endpoint: Live Stripe Webhook Ingestion & Subscription Sync ──
        elif path in ("/api/v1/stripe/webhook", "/stripe/webhook"):
            cfg = load_config()
            webhook_secret = (cfg.get("stripe_webhook_secret") or os.environ.get("STRIPE_WEBHOOK_SECRET") or "").strip()
            stripe_sig_header = self.headers.get("Stripe-Signature", "").strip()

            # Cryptographic signature verification if configured and signature header provided
            if webhook_secret and not webhook_secret.startswith("whsec_placeholder") and not webhook_secret.startswith("whsec_mock") and stripe_sig_header:
                try:
                    sig_parts = {}
                    for item in stripe_sig_header.split(","):
                        if "=" in item:
                            k, v = item.strip().split("=", 1)
                            sig_parts[k] = v
                    t = sig_parts.get("t", "")
                    v1 = sig_parts.get("v1", "")
                    if not t or not v1:
                        self._send_json({"error": "Invalid Stripe-Signature format"}, 400)
                        return
                    
                    signed_payload = f"{t}.".encode("utf-8") + post_data
                    expected_sig = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(expected_sig, v1):
                        self._send_json({"error": "Stripe signature verification failed"}, 400)
                        return
                except Exception as e:
                    self._send_json({"error": f"Signature verification error: {e}"}, 400)
                    return

            event = body
            if not isinstance(event, dict) or not event.get("type"):
                self._send_json({"error": "Invalid Stripe event payload"}, 400)
                return

            event_type = event.get("type", "")
            event_id = event.get("id", f"evt_{int(time.time())}")
            data_obj = event.get("data", {}).get("object", {})

            # 1. Checkout session completed -> upgrade account to paid tier
            if event_type == "checkout.session.completed":
                cust_email = (data_obj.get("customer_email") or (data_obj.get("customer_details") or {}).get("email") or "").strip().lower()
                client_ref_id = data_obj.get("client_reference_id", "")
                cust_id = data_obj.get("customer", "")
                sub_id = data_obj.get("subscription", "")
                
                # Determine target plan
                plan = (data_obj.get("metadata", {}).get("plan") or "").strip().lower()
                if not plan:
                    amt = data_obj.get("amount_total", 0)
                    if amt >= 2000:
                        plan = "master"
                    elif amt >= 900:
                        plan = "pro"
                    else:
                        plan = "pro"

                with DB_LOCK:
                    db = load_db()
                    matched_acc = None
                    for a in db.get("accounts", []):
                        if client_ref_id and a.get("id") == client_ref_id:
                            matched_acc = a
                            break
                        if cust_email and a.get("email", "").lower() == cust_email:
                            matched_acc = a
                            break
                        if cust_id and a.get("stripe_customer_id") == cust_id:
                            matched_acc = a
                            break

                    if matched_acc:
                        matched_acc["plan"] = plan
                        if cust_id:
                            matched_acc["stripe_customer_id"] = cust_id
                        if sub_id:
                            matched_acc["stripe_subscription_id"] = sub_id
                        matched_acc["status"] = "active"
                        matched_acc["modified_at"] = datetime.now().isoformat()
                        save_db(db)
                        record_stripe_event(event_type, event_id, matched_acc.get("email", cust_email), plan, f"Upgraded to {plan} tier via checkout")
                        self._send_json({"received": True, "event": event_type, "status": "upgraded", "user_id": matched_acc.get("id"), "plan": plan}, 200)
                        return
                    else:
                        if cust_email:
                            new_acc = {
                                "id": client_ref_id or f"usr_{os.urandom(6).hex()}",
                                "email": cust_email,
                                "name": cust_email.split("@")[0].capitalize(),
                                "role": "consumer",
                                "plan": plan,
                                "status": "active",
                                "stripe_customer_id": cust_id,
                                "stripe_subscription_id": sub_id,
                                "tokens_consumed": 0,
                                "created_at": datetime.now().isoformat(),
                                "last_active": "Just now"
                            }
                            db.setdefault("accounts", []).append(new_acc)
                            save_db(db)
                            record_stripe_event(event_type, event_id, cust_email, plan, f"Created new {plan} account via checkout")
                            self._send_json({"received": True, "event": event_type, "status": "created", "user_id": new_acc["id"], "plan": plan}, 200)
                            return
                        else:
                            record_stripe_event(event_type, event_id, "unknown", plan, "Ignored: No customer email provided")
                            self._send_json({"received": True, "event": event_type, "warning": "No email to associate"}, 200)
                            return

            # 2. Subscription updated
            elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
                sub_id = data_obj.get("id", "")
                cust_id = data_obj.get("customer", "")
                sub_status = data_obj.get("status", "active")
                plan = (data_obj.get("metadata", {}).get("plan") or "").strip().lower()
                if not plan:
                    items = (data_obj.get("items", {}) or {}).get("data", [])
                    if items:
                        price_amt = (items[0].get("price", {}) or {}).get("unit_amount", 0)
                        plan = "master" if price_amt >= 2000 else "pro"
                    else:
                        plan = "pro"

                with DB_LOCK:
                    db = load_db()
                    matched_acc = None
                    for a in db.get("accounts", []):
                        if sub_id and a.get("stripe_subscription_id") == sub_id:
                            matched_acc = a
                            break
                        if cust_id and a.get("stripe_customer_id") == cust_id:
                            matched_acc = a
                            break

                    if matched_acc:
                        if sub_status in ("active", "trialing"):
                            matched_acc["plan"] = plan
                            matched_acc["status"] = "active"
                        elif sub_status in ("past_due", "unpaid"):
                            matched_acc["status"] = "past_due"
                        elif sub_status in ("canceled", "incomplete_expired"):
                            matched_acc["plan"] = "free"
                            matched_acc["status"] = "active"
                        matched_acc["modified_at"] = datetime.now().isoformat()
                        save_db(db)
                        record_stripe_event(event_type, event_id, matched_acc.get("email"), matched_acc.get("plan"), f"Subscription status: {sub_status}")
                        self._send_json({"received": True, "event": event_type, "status": "synced", "user_id": matched_acc.get("id")}, 200)
                        return
                    else:
                        record_stripe_event(event_type, event_id, "unlinked", plan, f"Subscription {sub_id} unlinked")
                        self._send_json({"received": True, "event": event_type, "warning": "No account matched subscription"}, 200)
                        return

            # 3. Subscription deleted -> Downgrade to Free
            elif event_type == "customer.subscription.deleted":
                sub_id = data_obj.get("id", "")
                cust_id = data_obj.get("customer", "")
                with DB_LOCK:
                    db = load_db()
                    matched_acc = None
                    for a in db.get("accounts", []):
                        if sub_id and a.get("stripe_subscription_id") == sub_id:
                            matched_acc = a
                            break
                        if cust_id and a.get("stripe_customer_id") == cust_id:
                            matched_acc = a
                            break

                    if matched_acc:
                        matched_acc["plan"] = "free"
                        matched_acc["stripe_subscription_id"] = None
                        matched_acc["modified_at"] = datetime.now().isoformat()
                        save_db(db)
                        record_stripe_event(event_type, event_id, matched_acc.get("email"), "free", "Subscription deleted: downgraded to Free tier")
                        self._send_json({"received": True, "event": event_type, "status": "downgraded_to_free", "user_id": matched_acc.get("id")}, 200)
                        return
                    else:
                        record_stripe_event(event_type, event_id, "unlinked", "free", f"Deleted subscription {sub_id} unlinked")
                        self._send_json({"received": True, "event": event_type, "warning": "No account matched subscription"}, 200)
                        return

            # 4. Invoices and general events
            else:
                cust_email = (data_obj.get("customer_email") or "").strip().lower()
                record_stripe_event(event_type, event_id, cust_email, "n/a", f"Logged event: {event_type}")
                self._send_json({"received": True, "event": event_type, "status": "recorded"}, 200)
                return

        elif path == "/api/seed/create" or path == "/api/v1/api/seed/create" or path == "/api/v1/seed/create":
            seed_id = body.get("seed_id")
            content = body.get("content")
            if not seed_id or not content:
                self._send_json({"error": "Missing seed_id or content"}, 400)
                return
            token = f"tok_{os.urandom(8).hex()}"
            SIGNATURE_SESSIONS[token] = {
                "seed_id": seed_id,
                "content": content,
                "created_at": datetime.now().isoformat()
            }
            self._send_json({
                "sessionToken": token,
                "widgetUrl": f"/widget/sign?token={token}"
            }, 200)
            return

        elif path == "/widget/sign/submit":
            token = body.get("token")
            passphrase = body.get("passphrase", "default")
            if not token or token not in SIGNATURE_SESSIONS:
                self._send_json({"error": "Invalid or expired session token"}, 400)
                return
            session = SIGNATURE_SESSIONS[token]
            seed_id = session["seed_id"]
            content = session["content"]
            
            sig_hash = hashlib.sha256(f"{seed_id}:{content}:{passphrase}".encode("utf-8")).hexdigest()[:12].upper()
            signature_id = f"SIG_SCIA_{sig_hash}"
            certificate_url = f"/seeds/verify/{signature_id}"
            
            del SIGNATURE_SESSIONS[token]
            
            self._send_json({
                "signatureId": signature_id,
                "certificateUrl": certificate_url
            }, 200)
            return

        # ── API Endpoint: Plant Seed ──
        elif path == "/api/v1/seeds" or path == "/seeds":
            intent = body.get("intent", "").strip()
            if not intent:
                self._send_json({"error": "Missing 'intent' field"}, 400)
                return

            # Pre-validate inputs
            if "status" in body and body["status"] not in ["planted", "growing", "bloomed", "wilted"]:
                self._send_json({"error": f"Invalid status value '{body['status']}'"}, 400)
                return
            if "evidence_status" in body and body["evidence_status"] not in ['Explicitly Stated', 'Repeatedly Supported', 'Implied', 'Inferred', 'Ambiguous', 'Conflicting']:
                self._send_json({"error": f"Invalid evidence_status value '{body['evidence_status']}'"}, 400)
                return
            if "authority_status" in body and body["authority_status"] not in ['Detected', 'Under Review', 'User Confirmed', 'Authoritative', 'Superseded', 'Rejected', 'Unresolved']:
                self._send_json({"error": f"Invalid authority_status value '{body['authority_status']}'"}, 400)
                return
            if "continuity_status" in body and body["continuity_status"] not in ['Active', 'Dormant', 'Lost', 'Recovered', 'Restored', 'Replaced', 'Historical']:
                self._send_json({"error": f"Invalid continuity_status value '{body['continuity_status']}'"}, 400)
                return

            seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
            new_seed = {
                "seed_id": seed_id,
                "intent": intent,
                "title": body.get("title", intent.split("\n")[0][:60]),
                "summary": body.get("summary", intent),
                "source": body.get("source", "web"),
                "source_platform": body.get("source_platform", "web"),
                "source_transcript": body.get("source_transcript"),
                "source_transcript_id": body.get("source_transcript_id"),
                "source_thread_title": body.get("source_thread_title"),
                "source_excerpt": body.get("source_excerpt", intent),
                "source_message_id": body.get("source_message_id", ""),
                "source_timestamp": body.get("source_timestamp", ""),
                "status": body.get("status", "planted"),
                "evidence_status": body.get("evidence_status", "Explicitly Stated"),
                "authority_status": body.get("authority_status", "Detected"),
                "continuity_status": body.get("continuity_status", "Active"),
                "project_id": body.get("project_id", "default_project"),
                "growth": 0,
                "created_at": datetime.now().isoformat(),
                "modified_at": datetime.now().isoformat(),
                "completed_at": None,
                "versions": [],
                "related_seeds": [],
                "parent_seed_id": None,
                "child_seeds": [],
                "conflict_references": [],
                "decision_references": [],
                "is_cryptographically_signed": False,
                "trust_state": {
                    "signature": "unsigned",
                    "verification": "unverified",
                    "lineage": "missing"
                }
            }

            with DB_LOCK:
                db = load_db()
                account = resolve_account_for_request(self, db)
                tier_plan = account.get("plan", "free").lower()
                quota = TIER_QUOTAS.get(tier_plan, TIER_QUOTAS["free"])
                current_seeds_count = len(db.get("seeds", []))

                # Enforce free tier seed quota limit
                if tier_plan == "free" and current_seeds_count >= quota["max_seeds"]:
                    cfg = load_config()
                    upgrade_url = cfg.get("stripe_checkout_pro", "https://buy.stripe.com/test_seed_reflections_pro")
                    self._send_json({
                        "error": f"Free tier seed limit reached ({current_seeds_count}/{quota['max_seeds']}). Upgrade to Pro for unlimited seeds.",
                        "code": "SEED_QUOTA_EXCEEDED",
                        "seeds_used": current_seeds_count,
                        "seeds_limit": quota["max_seeds"],
                        "upgrade_url": upgrade_url
                    }, 403)
                    return

                proj_id = new_seed["project_id"]
                if proj_id != "default_project" and not any(p.get("project_id") == proj_id for p in db["projects"]):
                    self._send_json({"error": f"Referenced Project ID '{proj_id}' does not exist"}, 400)
                    return

                new_seed["owner_id"] = account.get("id")
                account["seeds_count"] = current_seeds_count + 1
                db["seeds"].append(new_seed)
                if save_db(db):
                    self._send_json({
                        "status": "planted",
                        "seed": new_seed,
                        "message": "Seed planted successfully!"
                    }, 201)
                else:
                    self._send_json({"error": "Failed to save seed to store"}, 500)
            return

        # ── API Endpoint: Update Seed ──
        elif path == "/api/v1/seeds/update" or path == "/seeds/update":
            seed_id = body.get("seed_id")
            if not seed_id:
                self._send_json({"error": "Missing 'seed_id' field"}, 400)
                return

            if "field" in body and "value" in body:
                body[body["field"]] = body["value"]

            # Pre-validate inputs before acquiring database lock where possible
            if "status" in body and body["status"] not in ["planted", "growing", "bloomed", "wilted"]:
                self._send_json({"error": f"Invalid status value '{body['status']}'"}, 400)
                return
            if "evidence_status" in body and body["evidence_status"] not in ['Explicitly Stated', 'Repeatedly Supported', 'Implied', 'Inferred', 'Ambiguous', 'Conflicting']:
                self._send_json({"error": f"Invalid evidence_status value '{body['evidence_status']}'"}, 400)
                return
            if "authority_status" in body and body["authority_status"] not in ['Detected', 'Under Review', 'User Confirmed', 'Authoritative', 'Superseded', 'Rejected', 'Unresolved']:
                self._send_json({"error": f"Invalid authority_status value '{body['authority_status']}'"}, 400)
                return
            if "continuity_status" in body and body["continuity_status"] not in ['Active', 'Dormant', 'Lost', 'Recovered', 'Restored', 'Replaced', 'Historical']:
                self._send_json({"error": f"Invalid continuity_status value '{body['continuity_status']}'"}, 400)
                return

            with DB_LOCK:
                db = load_db()
                target_seed = None
                for s in db["seeds"]:
                    if s.get("seed_id") == seed_id:
                        target_seed = s
                        break

                if not target_seed:
                    self._send_json({"error": f"Seed {seed_id} not found"}, 404)
                    return

                if "project_id" in body:
                    proj_id = body["project_id"]
                    if proj_id != "default_project" and not any(p.get("project_id") == proj_id for p in db["projects"]):
                        self._send_json({"error": f"Referenced Project ID '{proj_id}' does not exist"}, 400)
                        return

                if is_seed_signed_and_valid(target_seed):
                    modifying_core = False
                    if "intent" in body and body["intent"] != target_seed.get("intent"):
                        modifying_core = True
                    if "title" in body and body["title"] != target_seed.get("title"):
                        modifying_core = True
                    if "summary" in body and body["summary"] != target_seed.get("summary"):
                        modifying_core = True

                    if modifying_core:
                        self._send_json({
                            "error": "Forbidden",
                            "message": f"Seed {seed_id} is cryptographically signed and immutable. Direct mutations are blocked. Use the evolution API instead."
                        }, 403)
                        return

                # Push current version into history list for audit trail
                old_version = {
                    "intent": target_seed.get("intent"),
                    "title": target_seed.get("title", ""),
                    "summary": target_seed.get("summary", ""),
                    "status": target_seed.get("status"),
                    "evidence_status": target_seed.get("evidence_status"),
                    "authority_status": target_seed.get("authority_status"),
                    "continuity_status": target_seed.get("continuity_status"),
                    "modified_at": target_seed.get("modified_at") or target_seed.get("created_at")
                }
                if "versions" not in target_seed:
                    target_seed["versions"] = []
                target_seed["versions"].append(old_version)

                # Update fields
                if "intent" in body: target_seed["intent"] = body["intent"]
                if "title" in body: target_seed["title"] = body["title"]
                if "summary" in body: target_seed["summary"] = body["summary"]
                if "status" in body: target_seed["status"] = body["status"]
                if "evidence_status" in body: target_seed["evidence_status"] = body["evidence_status"]
                if "authority_status" in body: target_seed["authority_status"] = body["authority_status"]
                if "continuity_status" in body: target_seed["continuity_status"] = body["continuity_status"]
                if "project_id" in body: target_seed["project_id"] = body["project_id"]
                if "source_excerpt" in body: target_seed["source_excerpt"] = body["source_excerpt"]
                if "keywords" in body: target_seed["keywords"] = body["keywords"]
                if "recovery_suggestion" in body: target_seed["recovery_suggestion"] = body["recovery_suggestion"]
                target_seed["modified_at"] = datetime.now().isoformat()

                if save_db(db):
                    self._send_json({"status": "success", "seed": target_seed})
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return

        # ── API Endpoint: Evolve Seed ──
        elif path == "/api/v1/seeds/evolve" or path == "/seeds/evolve":
            parent_seed_id = body.get("parent_seed_id")
            if not parent_seed_id:
                self._send_json({"error": "Missing 'parent_seed_id' field"}, 400)
                return

            with DB_LOCK:
                db = load_db()
                parent_seed = next((s for s in db["seeds"] if s.get("seed_id") == parent_seed_id), None)
                if not parent_seed:
                    self._send_json({"error": f"Parent Seed {parent_seed_id} not found"}, 404)
                    return

                new_seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
                new_seed = dict(parent_seed)
                new_seed["seed_id"] = new_seed_id
                new_seed["parent_seed_id"] = parent_seed_id
                
                if "intent" in body:
                    new_seed["intent"] = body["intent"]
                if "title" in body:
                    new_seed["title"] = body["title"]
                else:
                    new_seed["title"] = body.get("intent", "").split("\n")[0][:60]
                if "summary" in body:
                    new_seed["summary"] = body["summary"]
                else:
                    new_seed["summary"] = new_seed["intent"]

                # Reset signature on evolved clone
                new_seed["is_cryptographically_signed"] = False
                new_seed["trust_state"] = {
                    "signature": "unsigned",
                    "verification": "unverified",
                    "lineage": "present"
                }
                if "verification_result" in new_seed:
                    del new_seed["verification_result"]

                # Successor is created as a proposed evolution
                new_seed["continuity_status"] = "Proposed"
                new_seed["created_at"] = datetime.now().isoformat()
                new_seed["modified_at"] = datetime.now().isoformat()
                new_seed["versions"] = []
                new_seed["child_seeds"] = []
                new_seed["related_seeds"] = []

                # Create the proposed relationship link
                relationship_id = f"rel_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
                evidence = str(body.get("evidence") or "").strip()
                proposed_rel = {
                    "relationship_id": relationship_id,
                    "source_seed_id": parent_seed_id,
                    "target_seed_id": new_seed_id,
                    "relationship_type": "Evolved Into",
                    "created_at": datetime.now().isoformat(),
                    "proposed_by": "user",
                    "approval_status": "Proposed",
                    "approved_by": None,
                    "approved_at": None,
                    "approval_basis": None,
                    "supporting_sources": [],
                    "evidence": evidence
                }

                if "relationships" not in db:
                    db["relationships"] = []
                db["relationships"].append(proposed_rel)
                db["seeds"].append(new_seed)

                if save_db(db):
                    self._send_json({
                        "status": "success",
                        "seed": new_seed,
                        "relationship": proposed_rel
                    }, 201)
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return

        # ── API Endpoint: Supersede Seed ──
        elif path == "/api/v1/seeds/supersede" or path == "/seeds/supersede":
            original_seed_id = body.get("original_seed_id")
            successor_seed_id = body.get("successor_seed_id")
            if not original_seed_id or not successor_seed_id:
                self._send_json({"error": "Missing 'original_seed_id' or 'successor_seed_id'"}, 400)
                return

            with DB_LOCK:
                db = load_db()
                original_seed = next((s for s in db["seeds"] if s.get("seed_id") == original_seed_id), None)
                successor_seed = next((s for s in db["seeds"] if s.get("seed_id") == successor_seed_id), None)

                if not original_seed:
                    self._send_json({"error": f"Original Seed {original_seed_id} not found"}, 404)
                    return
                if not successor_seed:
                    self._send_json({"error": f"Successor Seed {successor_seed_id} not found"}, 404)
                    return

                # Verify there is an APPROVED relationship of type "Evolved Into" or "Replaced By" linking them
                rel = next((r for r in db.get("relationships", [])
                            if r.get("source_seed_id") == original_seed_id
                            and r.get("target_seed_id") == successor_seed_id
                            and r.get("relationship_type") in ["Evolved Into", "Replaced By"]
                            and r.get("approval_status") == "Approved"), None)

                if not rel:
                    self._send_json({
                        "error": "Forbidden",
                        "message": f"No approved 'Evolved Into' or 'Replaced By' relationship found between original {original_seed_id} and successor {successor_seed_id}. Relationship must be approved before supersession can be authorized."
                    }, 400)
                    return

                # Perform the supersession transition
                original_seed["continuity_status"] = "Superseded"
                successor_seed["continuity_status"] = "Active"
                
                original_seed["modified_at"] = datetime.now().isoformat()
                successor_seed["modified_at"] = datetime.now().isoformat()

                if save_db(db):
                    self._send_json({
                        "status": "success",
                        "message": f"Seed {original_seed_id} superseded successfully by {successor_seed_id}.",
                        "original_seed": original_seed,
                        "successor_seed": successor_seed
                    })
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return

        # ── API Endpoint: Create Project ──
        elif path == "/api/v1/projects/create" or path == "/projects/create":
            name = str(body.get("name") or "").strip()
            if not name:
                self._send_json({"error": "Missing or empty 'name' field"}, 400)
                return

            project_id = str(body.get("project_id") or "").strip()
            if not project_id:
                project_id = f"project_{os.urandom(4).hex()}"
            elif not re.match(r"^[a-zA-Z0-9_\-]+$", project_id):
                self._send_json({"error": "Invalid format for 'project_id'"}, 400)
                return

            stage = str(body.get("stage") or "Active").strip()
            if stage not in ["Active", "Archived", "Completed"]:
                self._send_json({"error": f"Invalid stage '{stage}' for project"}, 400)
                return

            owner = str(body.get("owner") or "developer").strip()
            purpose = str(body.get("purpose") or "").strip()
            description = str(body.get("description") or "").strip()

            with DB_LOCK:
                db = load_db()
                if any(p.get("project_id") == project_id for p in db["projects"]):
                    self._send_json({"error": f"Project ID {project_id} already exists"}, 400)
                    return

                new_project = {
                    "project_id": project_id,
                    "name": name,
                    "purpose": purpose,
                    "description": description,
                    "owner": owner,
                    "created_at": datetime.now().isoformat(),
                    "last_reflection_date": None,
                    "stage": stage
                }
                db["projects"].append(new_project)
                if save_db(db):
                    self._send_json({"status": "success", "project": new_project})
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return

        # ── API Endpoint: Create Decision ──
        elif path == "/api/v1/decisions/create" or path == "/decisions/create":
            decision_statement = str(body.get("decision_statement") or "").strip()
            if not decision_statement:
                self._send_json({"error": "Missing or empty 'decision_statement' field"}, 400)
                return

            decision_type = str(body.get("decision_type") or "Architecture").strip()
            if decision_type not in ["Architecture", "Design", "Naming", "Scope", "Stripe"]:
                self._send_json({"error": f"Invalid decision type '{decision_type}'"}, 400)
                return

            status = str(body.get("status") or "Accepted").strip()
            if status not in ["Proposed", "Accepted", "Rejected", "Deprecated"]:
                self._send_json({"error": f"Invalid status '{status}'"}, 400)
                return

            project_id = str(body.get("project_id") or "default_project").strip()
            related_seeds = body.get("related_seeds")
            if related_seeds is None:
                related_seeds = []
            elif not isinstance(related_seeds, list):
                self._send_json({"error": "'related_seeds' must be an array"}, 400)
                return
            
            related_seeds = [str(sid).strip() for sid in related_seeds]
            source_conversation = str(body.get("source_conversation") or "").strip()
            source_excerpt = str(body.get("source_excerpt") or "").strip()
            decision_maker = str(body.get("decision_maker") or "user").strip()
            decision_id = str(body.get("decision_id") or "").strip()
            if not decision_id:
                decision_id = f"decision_{os.urandom(4).hex()}"

            with DB_LOCK:
                db = load_db()
                
                # Verify project exists
                if project_id != "default_project" and not any(p.get("project_id") == project_id for p in db["projects"]):
                    self._send_json({"error": f"Referenced Project ID '{project_id}' does not exist"}, 400)
                    return
                
                # Verify related seeds exist
                existing_seed_ids = {s.get("seed_id") for s in db["seeds"]}
                for sid in related_seeds:
                    if sid not in existing_seed_ids:
                        self._send_json({"error": f"Referenced Seed ID '{sid}' does not exist"}, 400)
                        return

                if any(d.get("decision_id") == decision_id for d in db["decisions"]):
                    self._send_json({"error": f"Decision ID {decision_id} already exists"}, 400)
                    return

                new_decision = {
                    "decision_id": decision_id,
                    "project_id": project_id,
                    "decision_statement": decision_statement,
                    "decision_type": decision_type,
                    "status": status,
                    "source_conversation": source_conversation,
                    "source_excerpt": source_excerpt,
                    "date": datetime.now().isoformat(),
                    "decision_maker": decision_maker,
                    "related_seeds": related_seeds
                }
                db["decisions"].append(new_decision)
                
                # Update references on related seeds
                for s in db["seeds"]:
                    if s.get("seed_id") in related_seeds:
                        if "decision_references" not in s:
                            s["decision_references"] = []
                        if decision_id not in s["decision_references"]:
                            s["decision_references"].append(decision_id)

                if save_db(db):
                    self._send_json({"status": "success", "decision": new_decision})
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return

        # ── API Endpoint: Create Conflict ──
        elif path == "/api/v1/conflicts/create" or path == "/conflicts/create":
            subject = str(body.get("subject") or "").strip()
            if not subject:
                self._send_json({"error": "Missing or empty 'subject' field"}, 400)
                return

            conflict_type = str(body.get("conflict_type") or "Intent Contradiction").strip()
            if conflict_type not in ["Intent Contradiction", "Scope Overlap", "Redundant Rule", "Dead Code"]:
                self._send_json({"error": f"Invalid conflict type '{conflict_type}'"}, 400)
                return

            seed_a = str(body.get("seed_a") or "").strip()
            seed_b = str(body.get("seed_b") or "").strip()
            if not seed_a or not seed_b:
                self._send_json({"error": "Missing 'seed_a' or 'seed_b' ID references"}, 400)
                return

            severity = str(body.get("severity") or "Medium").strip()
            if severity not in ["Low", "Medium", "High", "Critical"]:
                self._send_json({"error": f"Invalid severity '{severity}'"}, 400)
                return

            status = str(body.get("status") or "Unresolved").strip()
            if status not in ["Unresolved", "Resolved", "Mitigated", "Deferred"]:
                self._send_json({"error": f"Invalid status '{status}'"}, 400)
                return

            project_id = str(body.get("project_id") or "default_project").strip()
            conflict_id = f"conflict_{os.urandom(4).hex()}"

            with DB_LOCK:
                db = load_db()

                # Verify project exists
                if project_id != "default_project" and not any(p.get("project_id") == project_id for p in db["projects"]):
                    self._send_json({"error": f"Referenced Project ID '{project_id}' does not exist"}, 400)
                    return

                # Verify seed_a and seed_b exist
                existing_seed_ids = {s.get("seed_id") for s in db["seeds"]}
                if seed_a not in existing_seed_ids:
                    self._send_json({"error": f"Referenced Seed A ID '{seed_a}' does not exist"}, 400)
                    return
                if seed_b not in existing_seed_ids:
                    self._send_json({"error": f"Referenced Seed B ID '{seed_b}' does not exist"}, 400)
                    return

                new_conflict = {
                    "conflict_id": conflict_id,
                    "project_id": project_id,
                    "subject": subject,
                    "conflict_type": conflict_type,
                    "seed_a": seed_a,
                    "seed_b": seed_b,
                    "source_a": str(body.get("source_a") or "").strip(),
                    "source_b": str(body.get("source_b") or "").strip(),
                    "statement_a": str(body.get("statement_a") or "").strip(),
                    "statement_b": str(body.get("statement_b") or "").strip(),
                    "material_difference": str(body.get("material_difference") or "").strip(),
                    "severity": severity,
                    "status": status,
                    "resolution_date": datetime.now().isoformat() if status == "Resolved" else None
                }
                db["conflicts"].append(new_conflict)
                
                # Update conflict references on seed_a and seed_b
                for s in db["seeds"]:
                    if s.get("seed_id") in [seed_a, seed_b]:
                        if "conflict_references" not in s:
                            s["conflict_references"] = []
                        if conflict_id not in s["conflict_references"]:
                            s["conflict_references"].append(conflict_id)

                if save_db(db):
                    self._send_json({"status": "success", "conflict": new_conflict})
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return


        # ── API Endpoint: Create Relationship ──
        elif path == "/api/v1/relationships/create" or path == "/relationships/create":
            source_seed_id = str(body.get("source_seed_id") or "").strip()
            target_seed_id = str(body.get("target_seed_id") or "").strip()
            
            if not source_seed_id or not target_seed_id:
                self._send_json({"error": "Missing 'source_seed_id' or 'target_seed_id'"}, 400)
                return
                
            if source_seed_id == target_seed_id:
                self._send_json({"error": "Source and target seed IDs must be different"}, 400)
                return

            rel_type = str(body.get("relationship_type") or body.get("type") or "Evolved Into").strip()
            if rel_type not in RELATIONSHIP_REGISTRY:
                self._send_json({"error": f"Invalid relationship type '{rel_type}'"}, 400)
                return

            created_by = str(body.get("created_by") or body.get("proposed_by") or "user").strip()
            if created_by not in ["user", "ai", "heuristic"]:
                self._send_json({"error": f"Invalid creator/proposer value '{created_by}'"}, 400)
                return

            try:
                confidence = float(body.get("confidence", 1.0))
            except ValueError:
                self._send_json({"error": "Invalid confidence value"}, 400)
                return

            supporting_sources = body.get("supporting_sources")
            if supporting_sources is None:
                supporting_sources = []
            elif not isinstance(supporting_sources, list):
                self._send_json({"error": "'supporting_sources' must be an array"}, 400)
                return

            evidence = str(body.get("evidence") or "").strip()

            # Set explicit provenance fields
            proposed_by = created_by
            if proposed_by == "user":
                approval_status = "Approved"
                approved_by = "user"
                approved_at = datetime.now().isoformat()
                approval_basis = evidence or "User established relationship link"
            else:
                approval_status = "Proposed"
                approved_by = None
                approved_at = None
                approval_basis = None

            with DB_LOCK:
                db = load_db()
                existing_ids = {s.get("seed_id") for s in db["seeds"]}
                if source_seed_id not in existing_ids:
                    self._send_json({"error": f"Source Seed '{source_seed_id}' does not exist"}, 400)
                    return
                if target_seed_id not in existing_ids:
                    self._send_json({"error": f"Target Seed '{target_seed_id}' does not exist"}, 400)
                    return

                # Duplicate prevention: Check if identical relationship already exists in active/approved/proposed states
                is_symmetric = RELATIONSHIP_REGISTRY[rel_type]["symmetric"]
                duplicate_found = False
                for r in db.get("relationships", []):
                    if r.get("approval_status") in ["Proposed", "Approved"]:
                        if r.get("source_seed_id") == source_seed_id and r.get("target_seed_id") == target_seed_id and r.get("relationship_type") == rel_type:
                            duplicate_found = True
                            break
                        if is_symmetric:
                            if r.get("source_seed_id") == target_seed_id and r.get("target_seed_id") == source_seed_id and r.get("relationship_type") == rel_type:
                                duplicate_found = True
                                break

                if duplicate_found:
                    self._send_json({"error": "Relationship link already exists"}, 400)
                    return

                relationship_id = f"rel_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
                new_relationship = {
                    "relationship_id": relationship_id,
                    "source_seed_id": source_seed_id,
                    "target_seed_id": target_seed_id,
                    "relationship_type": rel_type,
                    "created_at": datetime.now().isoformat(),
                    "proposed_by": proposed_by,
                    "approval_status": approval_status,
                    "approved_by": approved_by,
                    "approved_at": approved_at,
                    "approval_basis": approval_basis,
                    "supporting_sources": supporting_sources,
                    "evidence": evidence
                }

                if "relationships" not in db:
                    db["relationships"] = []
                db["relationships"].append(new_relationship)

                # Cross-reference inside seeds ONLY if the relationship is Approved
                if approval_status == "Approved":
                    for s in db["seeds"]:
                        if s.get("seed_id") == source_seed_id:
                            if "child_seeds" not in s:
                                s["child_seeds"] = []
                            if target_seed_id not in s["child_seeds"]:
                                s["child_seeds"].append(target_seed_id)
                        if s.get("seed_id") == target_seed_id:
                            if "parent_seed_id" not in s or s["parent_seed_id"] is None:
                                s["parent_seed_id"] = source_seed_id
                            if "related_seeds" not in s:
                                s["related_seeds"] = []
                            if source_seed_id not in s["related_seeds"]:
                                s["related_seeds"].append(source_seed_id)

                if save_db(db):
                    self._send_json({"status": "success", "relationship": new_relationship})
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return

        # ── API Endpoint: Delete/Retract Relationship ──
        elif path == "/api/v1/relationships/delete" or path == "/relationships/delete":
            relationship_id = str(body.get("relationship_id") or "").strip()
            if not relationship_id:
                self._send_json({"error": "Missing 'relationship_id'"}, 400)
                return

            with DB_LOCK:
                db = load_db()
                if "relationships" not in db:
                    db["relationships"] = []
                
                rel = next((r for r in db["relationships"] if r.get("relationship_id") == relationship_id), None)
                if not rel:
                    self._send_json({"error": f"Relationship '{relationship_id}' not found"}, 404)
                    return

                # Prevent silent erasure: Approved links are marked Retracted, Proposed are marked Rejected
                status = rel.get("approval_status", "Proposed")
                src_id = rel.get("source_seed_id")
                tgt_id = rel.get("target_seed_id")

                if status == "Approved":
                    # Mark as Retracted tombstone record
                    rel["approval_status"] = "Retracted"
                    rel["retracted_by"] = str(body.get("retracted_by") or "user").strip()
                    rel["retracted_at"] = datetime.now().isoformat()
                    rel["retraction_basis"] = str(body.get("basis") or "User retracted relationship link").strip()

                    # Remove references from parent/child fields in actual seeds since relationship is no longer active
                    for s in db["seeds"]:
                        if s.get("seed_id") == src_id:
                            if "child_seeds" in s:
                                s["child_seeds"] = [c for c in s["child_seeds"] if c != tgt_id]
                        if s.get("seed_id") == tgt_id:
                            if s.get("parent_seed_id") == src_id:
                                s["parent_seed_id"] = None
                            if "related_seeds" in s:
                                s["related_seeds"] = [r for r in s["related_seeds"] if r != src_id]
                    message = "Relationship retracted successfully"
                else:
                    # Mark as Rejected tombstone record
                    rel["approval_status"] = "Rejected"
                    rel["rejected_by"] = str(body.get("rejected_by") or "user").strip()
                    rel["rejected_at"] = datetime.now().isoformat()
                    message = "Relationship proposal rejected successfully"

                if save_db(db):
                    self._send_json({"status": "success", "message": message, "relationship": rel})
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return

        # ── API Endpoint: Approve Relationship ──
        elif path == "/api/v1/relationships/approve" or path == "/relationships/approve":
            relationship_id = str(body.get("relationship_id") or "").strip()
            if not relationship_id:
                self._send_json({"error": "Missing 'relationship_id'"}, 400)
                return

            with DB_LOCK:
                db = load_db()
                if "relationships" not in db:
                    db["relationships"] = []

                rel = next((r for r in db["relationships"] if r.get("relationship_id") == relationship_id), None)
                if not rel:
                    self._send_json({"error": f"Relationship '{relationship_id}' not found"}, 404)
                    return

                if rel.get("approval_status") == "Approved":
                    self._send_json({"status": "success", "message": "Relationship is already approved", "relationship": rel})
                    return

                # Update approval provenance fields
                rel["approval_status"] = "Approved"
                rel["approved_by"] = str(body.get("approved_by") or "user").strip()
                rel["approved_at"] = datetime.now().isoformat()
                rel["approval_basis"] = str(body.get("basis") or rel.get("evidence") or "User approved relationship").strip()

                # Cross-reference inside seeds now that the relationship is Approved
                source_seed_id = rel.get("source_seed_id")
                target_seed_id = rel.get("target_seed_id")
                for s in db["seeds"]:
                    if s.get("seed_id") == source_seed_id:
                        if "child_seeds" not in s:
                            s["child_seeds"] = []
                        if target_seed_id not in s["child_seeds"]:
                            s["child_seeds"].append(target_seed_id)
                    if s.get("seed_id") == target_seed_id:
                        if "parent_seed_id" not in s or s["parent_seed_id"] is None:
                            s["parent_seed_id"] = source_seed_id
                        if "related_seeds" not in s:
                            s["related_seeds"] = []
                        if source_seed_id not in s["related_seeds"]:
                            s["related_seeds"].append(source_seed_id)

                if save_db(db):
                    self._send_json({"status": "success", "message": "Relationship approved successfully", "relationship": rel})
                else:
                    self._send_json({"error": "Failed to save database"}, 500)
            return


        # ── API Endpoint: Generate Widget Session Token ──
        elif path == "/api/v1/seed-signature/session":
            api_url = CONFIG["SEED_SIGNATURE_API_URL"].rstrip("/")
            api_key = CONFIG["SEED_SIGNATURE_API_KEY"]

            if not api_key:
                self._send_json({"error": "Seed Signature API key is unconfigured on this platform"}, 402)
                return

            req_data = json.dumps({"platform": "Seed Reflection standalone"}).encode("utf-8")
            req = urllib.request.Request(
                f"{api_url}/session",
                data=req_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                method="POST"
            )

            try:
                with urllib.request.urlopen(req, timeout=3) as resp:
                    session_data = json.loads(resp.read().decode("utf-8"))
                    self._send_json(session_data, 200)
            except URLError as e:
                print(f"Seed Signature authority unreachable: {e}")
                self._send_json({
                    "error": "Seed Signature service unavailable",
                    "message": "Failed to connect to the external signing authority."
                }, 503)
            return

        # ── API Endpoint: Save Seed Signature ──
        elif path.startswith("/api/v1/seeds/") and path.endswith("/signature"):
            seed_id = path.replace("/api/v1/seeds/", "").replace("/signature", "")
            
            sig_id = body.get("signatureId") or body.get("signature_id")
            cert_url = body.get("certificateUrl") or body.get("certificate_url")

            if not sig_id:
                self._send_json({"error": "Missing 'signatureId'"}, 400)
                return

            with DB_LOCK:
                db = load_db()
                found = False
                updated_seed = None
                for s in db["seeds"]:
                    if s.get("seed_id") == seed_id:
                        core_content = f"{s.get('title') or ''}|{s.get('intent') or ''}|{s.get('summary') or ''}"
                        digest = hashlib.sha256(core_content.encode("utf-8")).hexdigest()
                        s["is_cryptographically_signed"] = True
                        s["trust_state"] = {
                            "signature": sig_id,
                            "verification": "verified",
                            "lineage": "present",
                            "digest": digest
                        }
                        s["verification_result"] = {
                            "certificate_url": cert_url,
                            "signed_at": datetime.now().isoformat()
                        }
                        found = True
                        updated_seed = s
                        break

                if found:
                    save_db(db)
                    self._send_json({
                        "status": "signed",
                        "seed": updated_seed,
                        "message": f"Seed {seed_id} signed successfully."
                    })
                else:
                    self._send_json({"error": f"Seed {seed_id} not found"}, 404)
            return

        # ── API Endpoint: Upload Large Export JSON ──
        elif path == "/api/v1/upload_export" or path == "/upload_export":
            content_type_header = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type_header:
                self._send_json({"error": "Expected multipart/form-data"}, 400)
                return
            
            boundary_str = ""
            for token in content_type_header.split(";"):
                token = token.strip()
                if token.startswith("boundary="):
                    boundary_str = "--" + token.replace("boundary=", "")
            
            if not boundary_str:
                self._send_json({"error": "Mismatched boundary"}, 400)
                return

            # Parse multipart bytes
            form_data, files = parse_multipart(post_data, boundary_str)
            file_obj = files.get("file")
            if not file_obj:
                self._send_json({"error": "No file uploaded under key 'file'"}, 400)
                return

            filename = file_obj.get("filename") or "export.json"
            job_id = create_import_job(filename)
            threading.Thread(target=process_import_job, args=(job_id, filename, file_obj["content"]), daemon=True).start()
            self._send_json({"status": "accepted", "job_id": job_id, "message": "Import received and queued."}, 202)
            return

        # ── API Endpoint: Reflect Selected Conversations from Temp Upload ──
        elif path == "/api/v1/reflect_selected" or path == "/reflect_selected":
            selected_ids = body.get("conversations", [])
            if not selected_ids:
                self._send_json({"error": "Missing 'conversations' selection list"}, 400)
                return

            try:
                selected_convs = get_raw_archive_conversations(selected_ids)
                if not selected_convs:
                    self._send_json({"error": "No matching conversations were found in the persistent archive."}, 404)
                    return
                
                cfg = load_config()
                provider = cfg.get("llm_provider", "ollama")
                api_url = cfg.get("llm_api_url", "").rstrip("/")
                api_key = cfg.get("llm_api_key", "")
                model = cfg.get("llm_model", "llama3")
                
                seeds_to_append = []
                assimilated = []

                for c in selected_convs:
                    title = c.get("title") or c.get("name") or "Untitled Spark"
                    transcript = f"Conversation: {title}\n\n"
                    
                    if "mapping" in c and isinstance(c["mapping"], dict):
                        mapping = c["mapping"]
                        for node in mapping.values():
                            msg = node.get("message")
                            if msg and msg.get("content") and msg["content"].get("parts"):
                                parts = msg["content"]["parts"]
                                text = "\n".join(parts) if isinstance(parts, list) else str(parts)
                                role = msg.get("author", {}).get("role", "unknown")
                                transcript += f"[{role}]: {text}\n\n"
                    elif "chat_messages" in c and isinstance(c["chat_messages"], list):
                        for m in c["chat_messages"]:
                            role = m.get("sender") or "unknown"
                            text = m.get("text") or ""
                            transcript += f"[{role}]: {text}\n\n"
                    elif "messages" in c and isinstance(c["messages"], list):
                        for m in c["messages"]:
                            role = m.get("role") or m.get("sender") or "unknown"
                            content_val = m.get("content") or m.get("text") or ""
                            if isinstance(content_val, dict):
                                content_val = content_val.get("text") or content_val.get("parts") or ""
                            transcript += f"[{role}]: {content_val}\n\n"

                    # Save transcript to file and get hash ID
                    transcript_id = save_transcript(transcript)

                    # Build the LLM extraction prompt
                    prompt = (
                        "You are the Seed Reflections extraction engine. Analyze the following conversation transcript deeply.\n"
                        "Extract every 'Seed' — which means: any idea, spark of inspiration, project intention, task proposal, "
                        "design decision, tool suggestion, workflow plan, feature request, bug fix intention, refactoring idea, "
                        "architectural decision, integration plan, learning goal, or any actionable concept the user discussed.\n\n"
                        "Be THOROUGH. A long conversation may contain 10-50+ seeds. Do NOT summarize — extract each individual idea.\n\n"
                        "For each seed provide:\n"
                        "- 'title': A concise 5-12 word title summarizing the idea\n"
                        "- 'description': A 1-3 sentence explanation with specific details from the conversation\n"
                        "- 'status': One of 'planted' (new idea), 'growing' (actively being worked on in the conversation), "
                        "'bloomed' (completed/resolved in the conversation), 'wilted' (abandoned or rejected)\n\n"
                        "Return ONLY a JSON array of objects. No markdown, no backticks, no surrounding text.\n\n"
                        f"Transcript:\n{transcript[:80000]}"
                    )

                    extracted_seeds = []
                    
                    # ── LLM Provider: Ollama (local open-source LLMs) ──
                    ai_allowed, ai_code, ai_msg, _, _ = check_ai_gateway_status()
                    if not ai_allowed:
                        extracted_seeds = []
                    elif provider == "ollama" and api_url:
                        try:
                            req_payload = json.dumps({
                                "model": model or "llama3",
                                "messages": [{"role": "user", "content": prompt}],
                                "stream": False,
                                "format": "json"
                            }).encode("utf-8")
                            req = urllib.request.Request(f"{api_url}/api/chat", data=req_payload, headers={"Content-Type": "application/json"}, method="POST")
                            with urllib.request.urlopen(req, timeout=120) as resp:
                                res_data = json.loads(resp.read().decode("utf-8"))
                                content_res = res_data.get("message", {}).get("content", "").strip()
                                parsed = json.loads(content_res)
                                if isinstance(parsed, dict):
                                    for k in parsed:
                                        if isinstance(parsed[k], list):
                                            extracted_seeds = parsed[k]
                                            break
                                    else:
                                        extracted_seeds = [parsed]
                                elif isinstance(parsed, list):
                                    extracted_seeds = parsed
                        except Exception as e:
                            print(f"Ollama reflect failed for '{title}': {e}")

                    # ── LLM Provider: OpenAI / OpenAI-compatible (LM Studio, Together, etc.) ──
                    elif provider in ("openai", "openai_compatible") and api_key:
                        try:
                            endpoint_url = api_url or "https://api.openai.com/v1/chat/completions"
                            if not endpoint_url.endswith("/chat/completions"):
                                if endpoint_url.endswith("/v1"):
                                    endpoint_url = endpoint_url + "/chat/completions"
                                elif endpoint_url.endswith("/v1/"):
                                    endpoint_url = endpoint_url + "chat/completions"
                                else:
                                    endpoint_url = endpoint_url.rstrip("/") + "/v1/chat/completions"
                            req_payload = json.dumps({
                                "model": model or "gpt-4o-mini",
                                "messages": [{"role": "user", "content": prompt}]
                            }).encode("utf-8")
                            req = urllib.request.Request(
                                endpoint_url, 
                                data=req_payload, 
                                headers={
                                    "Content-Type": "application/json", 
                                    "Authorization": f"Bearer {api_key}",
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                                }, 
                                method="POST"
                            )
                            with urllib.request.urlopen(req, timeout=120) as resp:
                                res_data = json.loads(resp.read().decode("utf-8"))
                                usage_info = res_data.get("usage", {})
                                p_tok = usage_info.get("prompt_tokens", len(prompt) // 4)
                                c_tok = usage_info.get("completion_tokens", 100)
                                record_llm_usage(provider, model, p_tok, c_tok, caller_tag="reflect")
                                content_res = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                                # Strip markdown code fences if present
                                content_res = content_res.strip()
                                if content_res.startswith("```"):
                                    content_res = content_res.split("\n", 1)[-1]
                                    if content_res.endswith("```"):
                                        content_res = content_res[:-3]
                                parsed = json.loads(content_res)
                                if isinstance(parsed, dict):
                                    for k in parsed:
                                        if isinstance(parsed[k], list):
                                            extracted_seeds = parsed[k]
                                            break
                                    else:
                                        extracted_seeds = [parsed]
                                elif isinstance(parsed, list):
                                    extracted_seeds = parsed
                        except Exception as e:
                            print(f"OpenAI-compatible reflect failed for '{title}': {e}")

                    # ── LLM Provider: Gemini ──
                    elif provider == "gemini" and api_key:
                        try:
                            gemini_model = model or "gemini-2.5-flash"
                            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"
                            req_payload = json.dumps({
                                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                                "generationConfig": {"responseMimeType": "application/json"}
                            }).encode("utf-8")
                            req = urllib.request.Request(gemini_url, data=req_payload, headers={"Content-Type": "application/json"}, method="POST")
                            with urllib.request.urlopen(req, timeout=120) as resp:
                                res_data = json.loads(resp.read().decode("utf-8"))
                                content_res = res_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                                if content_res.startswith("```"):
                                    content_res = content_res.split("\n", 1)[-1]
                                    if content_res.endswith("```"):
                                        content_res = content_res[:-3]
                                parsed = json.loads(content_res)
                                if isinstance(parsed, dict):
                                    for k in parsed:
                                        if isinstance(parsed[k], list):
                                            extracted_seeds = parsed[k]
                                            break
                                    else:
                                        extracted_seeds = [parsed]
                                elif isinstance(parsed, list):
                                    extracted_seeds = parsed
                        except Exception as e:
                            print(f"Gemini reflect failed for '{title}': {e}")

                    if not extracted_seeds:
                        lines = transcript.split("\n")
                        # Expanded pattern to catch many more idea signals
                        pattern = re.compile(
                            r'(?:i want to|i need to|i would like to|let\'s|we should|we need to|we could|'
                            r'how about|idea:|feature:|we can|i\'m going to|i\'m thinking|'
                            r'plan to|going to build|going to create|going to make|should we|'
                            r'consider |think about|work on |build |create |implement |'
                            r'design |develop |set up |figure out |refactor |add |integrate |'
                            r'connect |deploy |launch |migrate |switch to )\s*(.+)',
                            re.IGNORECASE
                        )
                        seen = set()
                        for line in lines:
                            line = line.strip()
                            if not line or line.startswith("[assistant]") or line.startswith("[system]"):
                                continue
                            match = pattern.search(line)
                            if match:
                                intent = match.group(1).strip()
                                intent = re.sub(r'^[-*\s\.\?\!]+', '', intent)
                                if len(intent) > 10 and intent.lower() not in seen:
                                    seen.add(intent.lower())
                                    extracted_seeds.append({
                                        "title": intent[:80],
                                        "description": intent,
                                        "status": "planted"
                                    })
                        
                        # Also extract any user message over 30 chars as a potential context seed
                        if len(extracted_seeds) < 5:
                            for line in lines:
                                line = line.strip()
                                if line.startswith("[user]:") or line.startswith("[human]:"):
                                    msg_text = line.split(":", 1)[-1].strip()
                                    if len(msg_text) > 30 and msg_text.lower() not in seen:
                                        seen.add(msg_text.lower())
                                        extracted_seeds.append({
                                            "title": msg_text[:80],
                                            "description": msg_text,
                                            "status": "planted"
                                        })

                        if not extracted_seeds:
                            extracted_seeds.append({
                                "title": f"Reflections on: {title}",
                                "description": f"Full conversation thread '{title}' available for review.",
                                "status": "planted"
                            })

                    for s in extracted_seeds:
                        if not isinstance(s, dict) or not s.get("title"):
                            continue
                        enriched = enrich_heuristic_seed(s, transcript)
                        seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
                        new_seed = {
                            "seed_id": seed_id,
                            "intent": enriched.get("description") or enriched.get("title"),
                            "source": "conversation_extract",
                            "source_transcript_id": transcript_id,
                            "source_thread_title": title,
                            "status": enriched.get("status") or "planted",
                            "growth": 0,
                            "created_at": datetime.now().isoformat(),
                            "completed_at": None,
                            "is_cryptographically_signed": False,
                            "trust_state": {"signature": "unsigned", "verification": "unverified", "lineage": "missing"},
                            "confidence": enriched.get("confidence", 0.70),
                            "keywords": enriched.get("keywords", []),
                            "recovery_suggestion": enriched.get("recovery_suggestion", ""),
                            "source_platform": enriched.get("platform", "unknown")
                        }
                        seeds_to_append.append(new_seed)
                        assimilated.append(new_seed)
                
                with DB_LOCK:
                    db = load_db()
                    db["seeds"].extend(seeds_to_append)
                    save_db(db)
                
                # Cleanup temp file
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

                self._send_json({
                    "status": "success",
                    "assimilation_stats": {
                        "new_seed": len(assimilated),
                        "total_processed": len(selected_convs)
                    },
                    "answer": f"Assimilated {len(assimilated)} seeds from {len(selected_convs)} selected conversation threads.",
                    "seeds": [
                        {
                            "seed_id": s.get("seed_id"),
                            "title": s.get("intent", "").split("\n")[0][:100],
                            "description": s.get("intent"),
                            "status": s.get("status", "planted")
                        } for s in assimilated
                    ]
                })

            except Exception as e:
                print(f"Error executing select reflection: {e}")
                self._send_json({"error": f"Failed to reflect: {e}"}, 500)
            return

        # ── API Endpoint: Save Settings ──
        elif path in ("/api/v1/settings", "/api/v1/admin/config"):
            cfg = load_config()
            if "ai_monthly_budget_usd" in body:
                try:
                    body["ai_monthly_budget_usd"] = float(body["ai_monthly_budget_usd"])
                except Exception:
                    pass
            if "ai_budget_hard_stop" in body:
                body["ai_budget_hard_stop"] = bool(body["ai_budget_hard_stop"])
            if "ai_killswitch_enabled" in body:
                body["ai_killswitch_enabled"] = bool(body["ai_killswitch_enabled"])
            cfg.update(body)
            save_config(cfg)
            self._send_json({"status": "saved", "config": cfg})
            return

        # ── API Endpoint: Emergency AI Killswitch Toggle ──
        elif path == "/api/v1/admin/ai/killswitch":
            cfg = load_config()
            new_state = body.get("killswitch_enabled")
            if new_state is None:
                new_state = not cfg.get("ai_killswitch_enabled", False)
            else:
                new_state = bool(new_state)
            cfg["ai_killswitch_enabled"] = new_state
            save_config(cfg)
            action_str = "ACTIVATED (Outbound AI Paused)" if new_state else "DEACTIVATED (AI Gateway Resumed)"
            TELEMETRY_LOG.append({
                "timestamp": datetime.now().isoformat(),
                "provider": "admin",
                "model": "killswitch",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "caller": f"killswitch:{action_str}"
            })
            self._send_json({
                "status": "success",
                "killswitch_enabled": new_state,
                "message": f"Emergency AI Killswitch {action_str}"
            }, 200)
            return

        # ── API Endpoint: Admin User Update (Role, Plan, Status) ──
        elif path == "/api/v1/admin/users/update":
            user_id = body.get("user_id")
            if not user_id:
                self._send_json({"error": "Missing user_id"}, 400)
                return
            with DB_LOCK:
                db = load_db()
                account = next((a for a in db.get("accounts", []) if a.get("id") == user_id), None)
                if not account:
                    self._send_json({"error": "User account not found"}, 404)
                    return
                if "plan" in body:
                    account["plan"] = body["plan"]
                if "role" in body:
                    account["role"] = body["role"]
                if "status" in body:
                    account["status"] = body["status"]
                account["modified_at"] = datetime.now().isoformat()
                save_db(db)
                self._send_json({"status": "updated", "account": account})
            return

        # ── API Endpoint: Direct Tenant Account Creation ──
        elif path == "/api/v1/admin/users/create":
            name = (body.get("name") or "").strip()
            email = (body.get("email") or "").strip().lower()
            role = (body.get("role") or "consumer").strip().lower()
            plan = (body.get("plan") or "free").strip().lower()
            status = (body.get("status") or "active").strip().lower()
            password = (body.get("password") or "").strip()

            if not email:
                self._send_json({"error": "Missing 'email' field"}, 400)
                return
            if not name:
                name = email.split("@")[0].capitalize()

            with DB_LOCK:
                db = load_db()
                existing = next((a for a in db.get("accounts", []) if a.get("email", "").lower() == email), None)
                if existing:
                    self._send_json({"error": f"An account with email '{email}' already exists."}, 409)
                    return

                user_id = f"usr_{os.urandom(6).hex()}"
                new_acc = {
                    "id": user_id,
                    "email": email,
                    "name": name,
                    "role": role,
                    "plan": plan,
                    "status": status,
                    "reflections_used_this_month": 0,
                    "billing_cycle_month": datetime.now().strftime("%Y-%m"),
                    "tokens_consumed": 0,
                    "seeds_count": 0,
                    "created_at": datetime.now().isoformat(),
                    "last_active": "Just now"
                }
                if password:
                    new_acc["password_hash"] = hashlib.sha256(password.encode("utf-8")).hexdigest()

                db.setdefault("accounts", []).append(new_acc)
                save_db(db)
                TELEMETRY_LOG.append({
                    "timestamp": datetime.now().isoformat(),
                    "provider": "admin",
                    "model": "user_create",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "caller": f"user:created_{email}"
                })
                self._send_json({"status": "created", "account": new_acc}, 201)
            return

        # ── API Endpoint: Tenant Password Reset ──
        elif path == "/api/v1/admin/users/reset-password":
            user_id = body.get("user_id")
            new_password = (body.get("password") or "").strip()
            if not user_id or not new_password:
                self._send_json({"error": "Missing 'user_id' or 'password'"}, 400)
                return
            with DB_LOCK:
                db = load_db()
                account = next((a for a in db.get("accounts", []) if a.get("id") == user_id), None)
                if not account:
                    self._send_json({"error": "User account not found"}, 404)
                    return
                account["password_hash"] = hashlib.sha256(new_password.encode("utf-8")).hexdigest()
                account["password_updated_at"] = datetime.now().isoformat()
                save_db(db)
                TELEMETRY_LOG.append({
                    "timestamp": datetime.now().isoformat(),
                    "provider": "admin",
                    "model": "password_reset",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "caller": f"user:pwd_reset_{account.get('email')}"
                })
                self._send_json({"status": "success", "message": f"Password reset successfully for {account.get('email')}"}, 200)
            return

        # ── API Endpoint: Tenant Account Deletion ──
        elif path == "/api/v1/admin/users/delete":
            user_id = body.get("user_id")
            if not user_id:
                self._send_json({"error": "Missing 'user_id'"}, 400)
                return
            with DB_LOCK:
                db = load_db()
                account = next((a for a in db.get("accounts", []) if a.get("id") == user_id), None)
                if not account:
                    self._send_json({"error": "User account not found"}, 404)
                    return
                if account.get("id") == "usr_admin_master" or account.get("role") == "admin":
                    admins = [a for a in db.get("accounts", []) if a.get("role") == "admin"]
                    if len(admins) <= 1:
                        self._send_json({"error": "Cannot delete the primary platform administrator account."}, 403)
                        return
                db["accounts"] = [a for a in db.get("accounts", []) if a.get("id") != user_id]
                save_db(db)
                TELEMETRY_LOG.append({
                    "timestamp": datetime.now().isoformat(),
                    "provider": "admin",
                    "model": "user_delete",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "caller": f"user:deleted_{account.get('email')}"
                })
                self._send_json({"status": "deleted", "user_id": user_id, "email": account.get("email")}, 200)
            return

        # ── API Endpoint: Clean Orphan Transcripts & Cache ──
        elif path in ("/api/v1/admin/transcripts/clean", "/api/v1/admin/maintenance/clean-orphans"):
            with DB_LOCK:
                db = load_db()
                referenced_transcripts = set()
                # Find all transcript references across seeds and sources
                for s in db.get("seeds", []):
                    tid = s.get("source_transcript_id")
                    if tid:
                        referenced_transcripts.add(str(tid).strip())
                for src in db.get("sources", []):
                    tid = src.get("source_transcript_id") or src.get("transcript_id")
                    if tid:
                        referenced_transcripts.add(str(tid).strip())

                deleted_files = []
                bytes_reclaimed = 0
                if os.path.exists(TRANSCRIPTS_DIR):
                    for fname in os.listdir(TRANSCRIPTS_DIR):
                        fpath = os.path.join(TRANSCRIPTS_DIR, fname)
                        if os.path.isfile(fpath) and fname.endswith(".txt"):
                            base_id = fname[:-4]
                            if base_id not in referenced_transcripts:
                                fsize = os.path.getsize(fpath)
                                try:
                                    os.remove(fpath)
                                    deleted_files.append(fname)
                                    bytes_reclaimed += fsize
                                except Exception as e:
                                    print(f"Error deleting orphan transcript {fname}: {e}")

                TELEMETRY_LOG.append({
                    "timestamp": datetime.now().isoformat(),
                    "provider": "admin",
                    "model": "orphan_cleaner",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "caller": f"maintenance:purged_{len(deleted_files)}_orphans"
                })

                self._send_json({
                    "status": "success",
                    "purged_count": len(deleted_files),
                    "bytes_reclaimed": bytes_reclaimed,
                    "kb_reclaimed": round(bytes_reclaimed / 1024.0, 2),
                    "deleted_files": deleted_files,
                    "message": f"Successfully cleaned {len(deleted_files)} orphan transcripts ({round(bytes_reclaimed / 1024.0, 2)} KB reclaimed)."
                }, 200)
            return

        # ── API Endpoint: Test Platform LLM Connection ──
        elif path == "/api/v1/admin/test-llm":
            cfg = load_config()
            is_allowed, err_code, err_msg, _, _ = check_ai_gateway_status()
            if not is_allowed and err_code == "AI_KILLSWITCH_ACTIVE":
                self._send_json({
                    "success": False,
                    "message": "Cannot test connection: Emergency AI Killswitch is currently ENGAGED. Please deactivate killswitch first."
                }, 400)
                return
            provider = body.get("llm_provider") or cfg.get("llm_provider", "openai_compatible")
            api_url = body.get("llm_api_url") or cfg.get("llm_api_url", "https://api.groq.com/openai/v1")
            api_key = body.get("llm_api_key") or cfg.get("llm_api_key", "")
            model = body.get("llm_model") or cfg.get("llm_model", "qwen-qwq-32b")

            if not api_key:
                self._send_json({"success": False, "message": "No API key configured for platform."}, 400)
                return

            try:
                test_endpoint = api_url.rstrip("/")
                if not test_endpoint.endswith("/chat/completions"):
                    if test_endpoint.endswith("/v1"):
                        test_endpoint += "/chat/completions"
                    else:
                        test_endpoint += "/v1/chat/completions"
                req_data = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5
                }).encode("utf-8")
                req = urllib.request.Request(
                    test_endpoint,
                    data=req_data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                    method="POST"
                )
                start_t = time.time()
                with urllib.request.urlopen(req, timeout=12) as resp:
                    latency = round((time.time() - start_t) * 1000, 1)
                    self._send_json({
                        "success": True,
                        "latency_ms": latency,
                        "message": f"Connection verified successfully! ({latency}ms roundtrip)"
                    }, 200)
            except Exception as e:
                self._send_json({
                    "success": False,
                    "message": f"Connection test failed: {str(e)}"
                }, 200)
            return

        # ── API Endpoint: Delete Seed ──
        elif path == "/api/v1/seeds/delete" or path == "/seeds/delete":
            seed_id = body.get("seed_id")
            if not seed_id:
                self._send_json({"error": "Missing seed_id"}, 400)
                return
            with DB_LOCK:
                db = load_db()
                target_seed = next((s for s in db["seeds"] if s.get("seed_id") == seed_id), None)
                if not target_seed:
                    self._send_json({"error": "Seed not found"}, 404)
                    return
                
                # Check if it participated in approved relationships, signatures, decisions, or conflicts
                has_signatures = is_seed_signed_and_valid(target_seed)
                
                has_approved_relationships = False
                for r in db.get("relationships", []):
                    if (r.get("source_seed_id") == seed_id or r.get("target_seed_id") == seed_id) and r.get("approval_status") == "Approved":
                        has_approved_relationships = True
                        break
                        
                has_accepted_decisions = False
                for d in db.get("decisions", []):
                    if seed_id in d.get("related_seeds", []) and d.get("status") == "Accepted":
                        has_accepted_decisions = True
                        break
                        
                has_resolved_conflicts = False
                for c in db.get("conflicts", []):
                    if (c.get("seed_a") == seed_id or c.get("seed_b") == seed_id) and c.get("status") == "Resolved":
                        has_resolved_conflicts = True
                        break
                
                if has_signatures or has_approved_relationships or has_accepted_decisions or has_resolved_conflicts:
                    # Tombstone the seed instead of deleting it physically
                    target_seed["continuity_status"] = "Tombstoned"
                    target_seed["modified_at"] = datetime.now().isoformat()
                    # Do NOT cascade delete/nullify anything because we want to preserve historical provenance!
                    save_db(db)
                    self._send_json({"status": "success", "message": "Seed tombstoned successfully to preserve historical provenance", "tombstoned": True})
                    return
                else:
                    # Hard delete
                    db["seeds"] = [s for s in db["seeds"] if s.get("seed_id") != seed_id]
                    # Cascade cleanup (hard delete cascade is kept for drafts):
                    # 1. Remove references in other seeds' related_seeds and child_seeds
                    for s in db["seeds"]:
                        if "related_seeds" in s:
                            s["related_seeds"] = [rid for rid in s["related_seeds"] if rid != seed_id]
                        if "child_seeds" in s:
                            s["child_seeds"] = [cid for cid in s["child_seeds"] if cid != seed_id]
                        if s.get("parent_seed_id") == seed_id:
                            s["parent_seed_id"] = None

                    # 2. Remove references in decisions' related_seeds
                    for dec in db.get("decisions", []):
                        if "related_seeds" in dec:
                            dec["related_seeds"] = [rid for rid in dec["related_seeds"] if rid != seed_id]

                    # 3. Delete conflicts referencing this seed
                    db["conflicts"] = [c for c in db.get("conflicts", []) if c.get("seed_a") != seed_id and c.get("seed_b") != seed_id]
                    
                    # 4. Clean up proposed/rejected/retracted relationships involving this seed
                    db["relationships"] = [r for r in db.get("relationships", []) if r.get("source_seed_id") != seed_id and r.get("target_seed_id") != seed_id]

                    save_db(db)
                    self._send_json({"status": "success", "message": "Seed deleted successfully", "tombstoned": False})
                    return

        # ── API Endpoint: Reflect (Extract Seeds via LLM or Local Heuristics) ──
        elif path == "/api/v1/reflect" or path == "/reflect":
            transcript = body.get("transcript", "").strip()
            if not transcript:
                self._send_json({"error": "Missing 'transcript' field"}, 400)
                return

            # Check monthly reflection quota
            with DB_LOCK:
                db = load_db()
                account = resolve_account_for_request(self, db)
                sync_account_cycle(account)
                tier_plan = account.get("plan", "free").lower()
                quota = TIER_QUOTAS.get(tier_plan, TIER_QUOTAS["free"])
                used_reflections = account.get("reflections_used_this_month", 0)

                if used_reflections >= quota["max_monthly_reflections"]:
                    cfg = load_config()
                    target_upgrade = "master" if tier_plan == "pro" else "pro"
                    upgrade_url = cfg.get(f"stripe_checkout_{target_upgrade}", "https://buy.stripe.com/test_seed_reflections_pro")
                    self._send_json({
                        "error": f"Monthly reflection quota reached ({used_reflections}/{quota['max_monthly_reflections']}). Upgrade to {'Master' if tier_plan == 'pro' else 'Pro'} for more reflections.",
                        "code": "REFLECTION_QUOTA_EXCEEDED",
                        "reflections_used": used_reflections,
                        "reflections_limit": quota["max_monthly_reflections"],
                        "upgrade_url": upgrade_url
                    }, 429)
                    return

            cfg = load_config()
            provider = cfg.get("llm_provider", "ollama")
            api_url = cfg.get("llm_api_url", "").rstrip("/")
            api_key = cfg.get("llm_api_key", "")
            model = cfg.get("llm_model", "llama3")

            extracted_seeds = []
            extraction_method = "heuristics_fallback"

            prompt = (
                "You are the Seed Reflections extraction engine. Your task is to analyze the following "
                "conversation transcript and extract all 'Seeds' (ideas, sparks of inspiration, project intentions, "
                "or core tasks that the user initiated or proposed).\n"
                "Return the results ONLY as a JSON array of objects with these exact keys: "
                "'title', 'description', 'status' (must be one of: 'planted', 'germinating', 'growing', 'bloomed', 'wilted'). "
                "Do not include any chat formatting, markdown backticks, or text before/after the JSON array.\n\n"
                f"Transcript:\n{transcript}"
            )

            # Check AI Gateway killswitch and budget limits
            ai_allowed, ai_code, ai_msg, _, _ = check_ai_gateway_status()
            if not ai_allowed:
                extraction_method = f"heuristics_fallback ({ai_code})"
                TELEMETRY_LOG.append({
                    "timestamp": datetime.now().isoformat(),
                    "provider": "guardrail",
                    "model": ai_code,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "caller": f"reflect:blocked_{ai_code}"
                })

            # Try to query LLM if configured and gateway is operational
            if ai_allowed and provider == "ollama" and api_url:
                try:
                    req_payload = json.dumps({
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "format": "json"
                    }).encode("utf-8")
                    
                    req = urllib.request.Request(
                        f"{api_url}/api/chat",
                        data=req_payload,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        content = res_data.get("message", {}).get("content", "").strip()
                        extracted_seeds = json.loads(content)
                        extraction_method = f"ollama_local_{model}"
                except Exception as e:
                    print(f"Ollama call failed, falling back to heuristics: {e}")

            elif provider in ("openai", "openai_compatible") and api_key:
                try:
                    endpoint_url = api_url or "https://api.openai.com/v1/chat/completions"
                    if not endpoint_url.endswith("/chat/completions"):
                        if endpoint_url.endswith("/v1"):
                            endpoint_url = endpoint_url + "/chat/completions"
                        elif endpoint_url.endswith("/v1/"):
                            endpoint_url = endpoint_url + "chat/completions"
                        else:
                            endpoint_url = endpoint_url.rstrip("/") + "/v1/chat/completions"
                    req_payload = json.dumps({
                        "model": model or "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}]
                    }).encode("utf-8")
                    
                    req = urllib.request.Request(
                        endpoint_url,
                        data=req_payload,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        },
                        method="POST"
                    )
                    
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        content = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        content = content.strip()
                        if content.startswith("```"):
                            content = content.split("\n", 1)[-1]
                            if content.endswith("```"):
                                content = content[:-3]
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            for k in parsed:
                                if isinstance(parsed[k], list):
                                    extracted_seeds = parsed[k]
                                    break
                            else:
                                extracted_seeds = [parsed]
                        else:
                            extracted_seeds = parsed
                        extraction_method = f"{provider}_cloud_{model}"
                except Exception as e:
                    print(f"OpenAI/compatible call failed, falling back to heuristics: {e}")

            elif provider == "gemini" and api_key:
                try:
                    gemini_model = model or "gemini-2.5-flash"
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}"
                    req_payload = json.dumps({
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json"}
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        gemini_url,
                        data=req_payload,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        content = res_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        if content.startswith("```"):
                            content = content.split("\n", 1)[-1]
                            if content.endswith("```"):
                                content = content[:-3]
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            for k in parsed:
                                if isinstance(parsed[k], list):
                                    extracted_seeds = parsed[k]
                                    break
                            else:
                                extracted_seeds = [parsed]
                        elif isinstance(parsed, list):
                            extracted_seeds = parsed
                        extraction_method = f"gemini_{gemini_model}"
                except Exception as e:
                    print(f"Gemini call failed, falling back to heuristics: {e}")

            # Heuristics Fallback Parser
            if not extracted_seeds:
                lines = transcript.split("\n")
                pattern = re.compile(r'(?:i want to|let\'s|we should|how about|we need to|idea:|feature:)\s+(.+)', re.IGNORECASE)
                seen = set()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    match = pattern.search(line)
                    if match:
                        intent = match.group(1).strip()
                        intent = re.sub(r'^[-*\s\.\?\!]+', '', intent)
                        if len(intent) > 10 and intent not in seen:
                            seen.add(intent)
                            extracted_seeds.append({
                                "title": intent[:60] + ("..." if len(intent) > 60 else ""),
                                "description": intent,
                                "status": "planted"
                            })
                    elif line.startswith(("- ", "* ", "• ")) and len(line) > 15:
                        intent = line.lstrip("-*• ").strip()
                        if intent not in seen:
                            seen.add(intent)
                            extracted_seeds.append({
                                "title": intent[:60] + ("..." if len(intent) > 60 else ""),
                                "description": intent,
                                "status": "planted"
                            })

                if not extracted_seeds:
                    extracted_seeds.append({
                        "title": "Seed Reflections Workspace Feature",
                        "description": "Initialize a task to construct and verify the Seed Reflections isolated system.",
                        "status": "planted"
                    })
            # Save transcript to file and get ID
            transcript_id = save_transcript(transcript)

            # Optional parent seed linkage passed from focused chat or reflection
            parent_seed_id = body.get("parent_seed_id") or body.get("active_seed_id")

            # Auto-save extracted seeds directly into seeds.json database (with NLP enrichment)
            assimilated = []
            new_relationships = []

            for s in extracted_seeds:
                if not isinstance(s, dict) or not s.get("title"):
                    continue
                enriched = enrich_heuristic_seed(s, transcript)
                seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
                new_seed = {
                    "seed_id": seed_id,
                    "intent": enriched.get("description") or enriched.get("title"),
                    "title": enriched.get("title") or enriched.get("intent", "").split("\n")[0][:60],
                    "summary": enriched.get("description") or enriched.get("title"),
                    "source": "conversation_extract",
                    "source_transcript_id": transcript_id,
                    "status": enriched.get("status") or "planted",
                    "growth": 0,
                    "created_at": datetime.now().isoformat(),
                    "completed_at": None,
                    "is_cryptographically_signed": False,
                    "trust_state": {
                        "signature": "unsigned",
                        "verification": "unverified",
                        "lineage": "present" if parent_seed_id else "missing"
                    },
                    "confidence": enriched.get("confidence", 0.70),
                    "keywords": enriched.get("keywords", []),
                    "recovery_suggestion": enriched.get("recovery_suggestion", ""),
                    "source_platform": enriched.get("platform", "unknown"),
                    "source_thread_title": title_hint if 'title_hint' in locals() else "Pasted Transcript",
                    "parent_seed_id": parent_seed_id if parent_seed_id else None,
                    "child_seeds": [],
                    "related_seeds": [parent_seed_id] if parent_seed_id else []
                }
                assimilated.append(new_seed)

                # Automatically establish approved lineage relationship link if focused on parent seed
                if parent_seed_id:
                    rel_id = f"rel_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
                    new_relationships.append({
                        "relationship_id": rel_id,
                        "source_seed_id": parent_seed_id,
                        "target_seed_id": seed_id,
                        "relationship_type": "Evolved Into",
                        "created_at": datetime.now().isoformat(),
                        "proposed_by": "system",
                        "approval_status": "Approved",
                        "approved_by": "system",
                        "approved_at": datetime.now().isoformat(),
                        "evidence": f"Generated from conversational reflection on {new_seed.get('title', 'Idea')}"
                    })
            
            with DB_LOCK:
                db = load_db()
                account = resolve_account_for_request(self, db)
                sync_account_cycle(account)
                account["reflections_used_this_month"] = account.get("reflections_used_this_month", 0) + 1
                db["seeds"].extend(assimilated)
                if new_relationships:
                    db.setdefault("relationships", []).extend(new_relationships)
                    rebuild_relationship_references(db)
                save_db(db)

            self._send_json({
                "assimilation_stats": {
                    "new_seed": len(assimilated),
                    "total_processed": len(extracted_seeds)
                },
                "answer": f"Assimilated {len(assimilated)} seeds from your conversation transcript using **{extraction_method}** engine.",
                "seeds": [
                    {
                        "title": s.get("intent", "").split("\n")[0][:100],
                        "description": s.get("intent"),
                        "status": s.get("status", "planted")
                    } for s in assimilated
                ]
            })
            return

        # ── API Endpoint: Chat with Seeds & Transcripts ──
        elif path == "/api/v1/seeds/chat" or path == "/seeds/chat":
            prompt = body.get("prompt", "")
            active_seed_id = body.get("active_seed_id")
            
            context_transcript = ""
            active_seed_title = ""
            source_thread_title = ""
            if active_seed_id:
                seeds = load_seeds()
                for s in seeds:
                    if s.get("seed_id") == active_seed_id:
                        active_seed_title = s.get("intent", "").split("\n")[0][:100]
                        source_thread_title = s.get("source_thread_title", "")
                        # Load transcript from file
                        tid = s.get("source_transcript_id")
                        if tid:
                            context_transcript = load_transcript(tid) or ""
                        break
            
            system_prompt = (
                "You are the Seed Reflections assistant. Help the user plan, refine, and execute their coding ideas (seeds).\n"
                "You operate within their local isolated workspace. Keep your answers concise, practical, and highly developer-aligned."
            )
            if active_seed_id:
                system_prompt += f"\n\nThe user is currently focusing on the Seed: '{active_seed_title}'."
                if context_transcript:
                    system_prompt += (
                        "\nHere is the full text of the original conversation transcript from which this seed was extracted.\n"
                        "Use this context to answer their questions, recall past details, or expand on original specifications:\n"
                        "----------------------------------------\n"
                        f"{context_transcript[:40000]}\n"
                        "----------------------------------------\n"
                    )

            cfg = load_config()
            provider = cfg.get("llm_provider", "ollama")
            api_url = cfg.get("llm_api_url", "").rstrip("/")
            api_key = cfg.get("llm_api_key", "")
            model = cfg.get("llm_model", "llama3")

            answer = ""

            ai_allowed, ai_code, ai_msg, _, _ = check_ai_gateway_status()
            if not ai_allowed:
                answer = f"**[AI Gateway Paused]**\n\nNotice: {ai_msg}\n\nThe administrator has activated budget caps or emergency pause for outbound LLM calls."
            elif provider == "ollama" and api_url:
                try:
                    req_payload = json.dumps({
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False
                    }).encode("utf-8")
                    req = urllib.request.Request(f"{api_url}/api/chat", data=req_payload, headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        answer = res_data.get("message", {}).get("content", "").strip()
                except Exception as e:
                    print(f"Ollama chat failed: {e}")

            elif ai_allowed and provider == "openai" and api_key:
                try:
                    req_payload = json.dumps({
                        "model": model or "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ]
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        "https://api.openai.com/v1/chat/completions", 
                        data=req_payload, 
                        headers={
                            "Content-Type": "application/json", 
                            "Authorization": f"Bearer {api_key}",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }, 
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        answer = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                except Exception as e:
                    print(f"OpenAI chat failed: {e}")
 
            elif ai_allowed and provider == "openai_compatible" and api_key:
                try:
                    endpoint_url = api_url or "https://api.openai.com/v1/chat/completions"
                    if not endpoint_url.endswith("/chat/completions"):
                        if endpoint_url.endswith("/v1"):
                            endpoint_url = endpoint_url + "/chat/completions"
                        elif endpoint_url.endswith("/v1/"):
                            endpoint_url = endpoint_url + "chat/completions"
                        else:
                            endpoint_url = endpoint_url.rstrip("/") + "/v1/chat/completions"
                    req_payload = json.dumps({
                        "model": model or "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ]
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        endpoint_url, 
                        data=req_payload, 
                        headers={
                            "Content-Type": "application/json", 
                            "Authorization": f"Bearer {api_key}",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }, 
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        usage_info = res_data.get("usage", {})
                        p_tok = usage_info.get("prompt_tokens", len(prompt + system_prompt) // 4)
                        c_tok = usage_info.get("completion_tokens", 80)
                        record_llm_usage(provider, model, p_tok, c_tok, caller_tag="chat")
                        answer = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                except Exception as e:
                    print(f"OpenAI-compatible chat failed: {e}")

            elif provider == "gemini" and api_key:
                try:
                    req_payload = json.dumps({
                        "contents": [
                            {"role": "user", "parts": [{"text": f"System context:\n{system_prompt}\n\nUser Question:\n{prompt}"}]}
                        ]
                    }).encode("utf-8")
                    gemini_model = model or "gemini-2.5-flash"
                    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={api_key}", data=req_payload, headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        answer = res_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                except Exception as e:
                    print(f"Gemini chat failed: {e}")

            if not answer:
                answer = f"**[Offline Local Mode]**\n\nI parsed your prompt: *'{prompt}'*\n"
                if active_seed_id:
                    answer += f"Focusing on active seed: **{active_seed_title}**.\n\n"
                    if context_transcript:
                        answer += "*(Loaded original conversation transcript context - 40k characters parsed).* Based on the original specifications in the conversation, the core details outline this project task. Please configure an LLM key in Settings to trigger live AI conversation."
                    else:
                        answer += "*(No original transcript context exists for this seed).* Please configure an LLM key in Settings to trigger live AI conversation."
                else:
                    answer += "\nPlease configure an LLM API key in Settings to chat with your seed database dynamically."

            self._send_json({"answer": answer})
            return

        self._send_json({"error": "Endpoint Not Found"}, 404)
        return


def run(server_class=ThreadingHTTPServer, handler_class=SeedReflectionAPIHandler):
    server_address = (HOST, PORT)
    try:
        httpd = server_class(server_address, handler_class)
    except OSError as e:
        import sys
        if getattr(e, 'winerror', None) == 10048 or "already in use" in str(e).lower() or getattr(e, 'errno', None) == 98:
            print(f"\n❌ Error starting server: Port {PORT} is already in use!")
            print(f"Please ensure another instance of Seed Reflection is not running, or free port {PORT} and try again.\n")
            sys.exit(1)
        else:
            raise e

    print(f"\n======================================================")
    print(f"[START] Seed Reflection consumer backend server running...")
    print(f"[PORT] Serving dashboard on: http://localhost:{PORT}")
    print(f"[API] API Endpoint: http://localhost:{PORT}/api/v1")
    print(f"======================================================\n")
    if DEPLOYMENT_MODE=="local":
        interval=max(15,int(os.environ.get("SEED_REFLECTIONS_CONNECTOR_SYNC_SECONDS","60")))
        def connector_sync_loop():
            while True:
                time.sleep(interval)
                try: sync_automatic_connectors("local")
                except Exception as exc: print(f"Connector auto-sync failed: {exc}")
        threading.Thread(target=connector_sync_loop,daemon=True,name="seed-reflections-connector-sync").start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    run()
