"""
Patch server.py with:
1. Transcript file storage system
2. Gemini + generic OpenAI-compatible LLM provider in reflect_selected
3. Expanded heuristic fallback patterns
4. Fix duplicate source_transcript key bug
5. GET /api/v1/transcripts/{id} endpoint
6. Increase LLM timeout
7. Include source_transcript_id in GET /seeds response
"""

import re

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "r", encoding="utf-8") as f:
    content = f.read()

# ─────────────────────────────────────────────────────────────
# 1. Add TRANSCRIPTS_DIR constant and hashlib import + helper
# ─────────────────────────────────────────────────────────────

old_constants = '''PORT = 8476
DATA_FILE = "seeds.json"
ENV_FILE = ".env"
CONFIG_FILE = "config.json"'''

new_constants = '''PORT = 8476
DATA_FILE = "seeds.json"
ENV_FILE = ".env"
CONFIG_FILE = "config.json"
TRANSCRIPTS_DIR = "transcripts"

import hashlib

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
    """Load transcript text by hash ID."""
    t_path = os.path.join(TRANSCRIPTS_DIR, f"{transcript_id}.txt")
    if os.path.exists(t_path):
        with open(t_path, "r", encoding="utf-8") as f:
            return f.read()
    return None'''

if old_constants in content:
    content = content.replace(old_constants, new_constants, 1)
    print("1. Constants + transcript helpers added.")
else:
    print("WARNING: Constants block not found!")

# ─────────────────────────────────────────────────────────────
# 2. Fix GET /api/v1/seeds to include source_transcript_id
# ─────────────────────────────────────────────────────────────

old_get_seeds = '''            summaries.append({
                    "id": s.get("seed_id"),
                    "seed_id": s.get("seed_id"),
                    "title": s.get("intent", "").split("\\n")[0][:100],
                    "intent": s.get("intent"),
                    "description": s.get("intent"),
                    "stage": s.get("status", "planted"),
                    "status": s.get("status", "planted"),
                    "stage_emoji": "🌱" if s.get("status") == "planted" else "🌸",
                    "growth": s.get("growth", 0),
                    "source": s.get("source", "web"),
                    "created_at": s.get("created_at"),
                    "completed_at": s.get("completed_at"),
                    "is_cryptographically_signed": s.get("is_cryptographically_signed", False),
                    "trust_state": s.get("trust_state", {})
                })'''

new_get_seeds = '''            summaries.append({
                    "id": s.get("seed_id"),
                    "seed_id": s.get("seed_id"),
                    "title": s.get("intent", "").split("\\n")[0][:100],
                    "intent": s.get("intent"),
                    "description": s.get("intent"),
                    "stage": s.get("status", "planted"),
                    "status": s.get("status", "planted"),
                    "stage_emoji": "🌱" if s.get("status") == "planted" else "🌸",
                    "growth": s.get("growth", 0),
                    "source": s.get("source", "web"),
                    "source_transcript_id": s.get("source_transcript_id"),
                    "source_thread_title": s.get("source_thread_title"),
                    "created_at": s.get("created_at"),
                    "completed_at": s.get("completed_at"),
                    "is_cryptographically_signed": s.get("is_cryptographically_signed", False),
                    "trust_state": s.get("trust_state", {})
                })'''

if old_get_seeds in content:
    content = content.replace(old_get_seeds, new_get_seeds, 1)
    print("2. GET /seeds response updated with transcript_id.")
else:
    print("WARNING: GET seeds response block not found!")

# ─────────────────────────────────────────────────────────────
# 3. Add GET /api/v1/transcripts/{id} endpoint in do_GET
# ─────────────────────────────────────────────────────────────

# Insert before the first elif in do_GET after the seeds endpoint
old_get_user = '''        # ── API Endpoint: Get Current User ──
        elif path == "/api/v1/users/me" or path == "/users/me":'''

new_get_transcript_plus_user = '''        # ── API Endpoint: Get Transcript by ID ──
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
        elif path == "/api/v1/users/me" or path == "/users/me":'''

if old_get_user in content:
    content = content.replace(old_get_user, new_get_transcript_plus_user, 1)
    print("3. GET /transcripts/{id} endpoint added.")
else:
    print("WARNING: GET user endpoint not found!")

# ─────────────────────────────────────────────────────────────
# 4. Replace reflect_selected inner loop: LLM calls + heuristic + seed storage
#    This is the big one. Replace from the for loop through to save_seeds.
# ─────────────────────────────────────────────────────────────

old_reflect_loop = '''                for c in selected_convs:
                    title = c.get("title") or c.get("name") or "Untitled Spark"
                    transcript = f"Conversation: {title}\\n\\n"
                    
                    if "mapping" in c and isinstance(c["mapping"], dict):
                        mapping = c["mapping"]
                        for node in mapping.values():
                            msg = node.get("message")
                            if msg and msg.get("content") and msg["content"].get("parts"):
                                parts = msg["content"]["parts"]
                                text = "\\n".join(parts) if isinstance(parts, list) else str(parts)
                                role = msg.get("author", {}).get("role", "unknown")
                                transcript += f"[{role}]: {text}\\n\\n"
                    elif "chat_messages" in c and isinstance(c["chat_messages"], list):
                        for m in c["chat_messages"]:
                            role = m.get("sender") or "unknown"
                            text = m.get("text") or ""
                            transcript += f"[{role}]: {text}\\n\\n"
                    elif "messages" in c and isinstance(c["messages"], list):
                        for m in c["messages"]:
                            role = m.get("role") or m.get("sender") or "unknown"
                            content_val = m.get("content") or m.get("text") or ""
                            if isinstance(content_val, dict):
                                content_val = content_val.get("text") or content_val.get("parts") or ""
                            transcript += f"[{role}]: {content_val}\\n\\n"

                    # Run reflect extraction prompt
                    prompt = (
                        "You are the Seed Reflections extraction engine. Your task is to analyze the following "
                        "conversation transcript and extract all 'Seeds' (ideas, sparks of inspiration, project intentions, "
                        "or core tasks that the user initiated or proposed).\\n"
                        "Return the results ONLY as a JSON array of objects with these exact keys: "
                        "'title', 'description', 'status' (must be one of: 'planted', 'germinating', 'growing', 'bloomed', 'wilted'). "
                        "Do not include any chat formatting, markdown backticks, or text before/after the JSON array.\\n\\n"
                        f"Transcript:\\n{transcript[:60000]}" # limit to prevent token overflows
                    )

                    extracted_seeds = []
                    
                    if provider == "ollama" and api_url:
                        try:
                            import urllib.request
                            req_payload = json.dumps({
                                "model": model,
                                "messages": [{"role": "user", "content": prompt}],
                                "stream": False,
                                "format": "json"
                            }).encode("utf-8")
                            req = urllib.request.Request(f"{api_url}/api/chat", data=req_payload, headers={"Content-Type": "application/json"}, method="POST")
                            with urllib.request.urlopen(req, timeout=12) as resp:
                                res_data = json.loads(resp.read().decode("utf-8"))
                                content_res = res_data.get("message", {}).get("content", "").strip()
                                extracted_seeds = json.loads(content_res)
                        except Exception as e:
                            print(f"Ollama failed for {title}: {e}")

                    elif provider == "openai" and api_key:
                        try:
                            import urllib.request
                            req_payload = json.dumps({
                                "model": model or "gpt-4o-mini",
                                "messages": [{"role": "user", "content": prompt}],
                                "response_format": {"type": "json_object"}
                            }).encode("utf-8")
                            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=req_payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
                            with urllib.request.urlopen(req, timeout=12) as resp:
                                res_data = json.loads(resp.read().decode("utf-8"))
                                content_res = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                                parsed = json.loads(content_res)
                                if isinstance(parsed, dict):
                                    for k in parsed:
                                        if isinstance(parsed[k], list):
                                            extracted_seeds = parsed[k]
                                            break
                                    else:
                                        extracted_seeds = [parsed]
                                else:
                                    extracted_seeds = parsed
                        except Exception as e:
                            print(f"OpenAI failed for {title}: {e}")

                    # Heuristic Fallback
                    if not extracted_seeds:
                        import re
                        lines = transcript.split("\\n")
                        pattern = re.compile(r'(?:i want to|let\\'s|we should|how about|we need to|idea:|feature:)\\s+(.+)', re.IGNORECASE)
                        seen = set()
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            match = pattern.search(line)
                            if match:
                                intent = match.group(1).strip()
                                intent = re.sub(r'^[-*\\s\\.\\?\\!]+', '', intent)
                                if len(intent) > 10 and intent not in seen:
                                    seen.add(intent)
                                    extracted_seeds.append({"title": intent[:60] + "...", "description": intent, "status": "planted"})
                        
                        if not extracted_seeds:
                            extracted_seeds.append({
                                "title": f"Reflections on: {title}",
                                "description": f"Analyzed conversation thread '{title}'.",
                                "status": "planted"
                            })

                    for s in extracted_seeds:
                        if not isinstance(s, dict) or not s.get("title"):
                            continue
                        seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
                        new_seed = {
                            "seed_id": seed_id,
                            "intent": s.get("description") or s.get("title"),
                            "source": "conversation_extract",
                "source_transcript": transcript,
            "source_transcript": transcript,
                            "status": s.get("status") or "planted",
                            "growth": 0,
                            "created_at": datetime.now().isoformat(),
                            "completed_at": None,
                            "is_cryptographically_signed": False,
                            "trust_state": {"signature": "unsigned", "verification": "unverified", "lineage": "missing"}
                        }
                        seeds.append(new_seed)
                        assimilated.append(new_seed)
                
                save_seeds(seeds)'''

new_reflect_loop = '''                for c in selected_convs:
                    title = c.get("title") or c.get("name") or "Untitled Spark"
                    transcript = f"Conversation: {title}\\n\\n"
                    
                    if "mapping" in c and isinstance(c["mapping"], dict):
                        mapping = c["mapping"]
                        for node in mapping.values():
                            msg = node.get("message")
                            if msg and msg.get("content") and msg["content"].get("parts"):
                                parts = msg["content"]["parts"]
                                text = "\\n".join(parts) if isinstance(parts, list) else str(parts)
                                role = msg.get("author", {}).get("role", "unknown")
                                transcript += f"[{role}]: {text}\\n\\n"
                    elif "chat_messages" in c and isinstance(c["chat_messages"], list):
                        for m in c["chat_messages"]:
                            role = m.get("sender") or "unknown"
                            text = m.get("text") or ""
                            transcript += f"[{role}]: {text}\\n\\n"
                    elif "messages" in c and isinstance(c["messages"], list):
                        for m in c["messages"]:
                            role = m.get("role") or m.get("sender") or "unknown"
                            content_val = m.get("content") or m.get("text") or ""
                            if isinstance(content_val, dict):
                                content_val = content_val.get("text") or content_val.get("parts") or ""
                            transcript += f"[{role}]: {content_val}\\n\\n"

                    # Save transcript to file and get hash ID
                    transcript_id = save_transcript(transcript)

                    # Build the LLM extraction prompt
                    prompt = (
                        "You are the Seed Reflections extraction engine. Analyze the following conversation transcript deeply.\\n"
                        "Extract every 'Seed' — which means: any idea, spark of inspiration, project intention, task proposal, "
                        "design decision, tool suggestion, workflow plan, feature request, bug fix intention, refactoring idea, "
                        "architectural decision, integration plan, learning goal, or any actionable concept the user discussed.\\n\\n"
                        "Be THOROUGH. A long conversation may contain 10-50+ seeds. Do NOT summarize — extract each individual idea.\\n\\n"
                        "For each seed provide:\\n"
                        "- 'title': A concise 5-12 word title summarizing the idea\\n"
                        "- 'description': A 1-3 sentence explanation with specific details from the conversation\\n"
                        "- 'status': One of 'planted' (new idea), 'growing' (actively being worked on in the conversation), "
                        "'bloomed' (completed/resolved in the conversation), 'wilted' (abandoned or rejected)\\n\\n"
                        "Return ONLY a JSON array of objects. No markdown, no backticks, no surrounding text.\\n\\n"
                        f"Transcript:\\n{transcript[:80000]}"
                    )

                    extracted_seeds = []
                    
                    # ── LLM Provider: Ollama (local open-source LLMs) ──
                    if provider == "ollama" and api_url:
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
                                endpoint_url = endpoint_url.rstrip("/") + "/v1/chat/completions"
                            req_payload = json.dumps({
                                "model": model or "gpt-4o-mini",
                                "messages": [{"role": "user", "content": prompt}]
                            }).encode("utf-8")
                            req = urllib.request.Request(endpoint_url, data=req_payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
                            with urllib.request.urlopen(req, timeout=120) as resp:
                                res_data = json.loads(resp.read().decode("utf-8"))
                                content_res = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                                # Strip markdown code fences if present
                                content_res = content_res.strip()
                                if content_res.startswith("```"):
                                    content_res = content_res.split("\\n", 1)[-1]
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
                                    content_res = content_res.split("\\n", 1)[-1]
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

                    # ── Heuristic Fallback (no LLM configured or all LLM calls failed) ──
                    if not extracted_seeds:
                        import re
                        lines = transcript.split("\\n")
                        # Expanded pattern to catch many more idea signals
                        pattern = re.compile(
                            r'(?:i want to|i need to|i would like to|let\\'s|we should|we need to|we could|'
                            r'how about|idea:|feature:|we can|i\\'m going to|i\\'m thinking|'
                            r'plan to|going to build|going to create|going to make|should we|'
                            r'consider |think about|work on |build |create |implement |'
                            r'design |develop |set up |figure out |refactor |add |integrate |'
                            r'connect |deploy |launch |migrate |switch to )\\s*(.+)',
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
                                intent = re.sub(r'^[-*\\s\\.\\?\\!]+', '', intent)
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
                        seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
                        new_seed = {
                            "seed_id": seed_id,
                            "intent": s.get("description") or s.get("title"),
                            "source": "conversation_extract",
                            "source_transcript_id": transcript_id,
                            "source_thread_title": title,
                            "status": s.get("status") or "planted",
                            "growth": 0,
                            "created_at": datetime.now().isoformat(),
                            "completed_at": None,
                            "is_cryptographically_signed": False,
                            "trust_state": {"signature": "unsigned", "verification": "unverified", "lineage": "missing"}
                        }
                        seeds.append(new_seed)
                        assimilated.append(new_seed)
                
                save_seeds(seeds)'''

if old_reflect_loop in content:
    content = content.replace(old_reflect_loop, new_reflect_loop, 1)
    print("4. Reflect_selected loop fully replaced (LLM + heuristic + storage).")
else:
    print("WARNING: Reflect loop not found! Trying flexible match...")
    # Try to find and replace using line-by-line approach
    # Look for the start marker
    start_marker = "                for c in selected_convs:"
    end_marker = "                save_seeds(seeds)"
    
    lines = content.split("\n")
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if start_marker in line and start_idx is None:
            start_idx = i
        if end_marker in line and start_idx is not None:
            end_idx = i
            break
    
    if start_idx is not None and end_idx is not None:
        print(f"  Found block at lines {start_idx+1}-{end_idx+1}, replacing...")
        new_lines = new_reflect_loop.split("\n")
        lines = lines[:start_idx] + new_lines + lines[end_idx+1:]
        content = "\n".join(lines)
        print("4. Reflect_selected loop replaced via flexible match.")
    else:
        print(f"  FAILED: start_idx={start_idx}, end_idx={end_idx}")

# ─────────────────────────────────────────────────────────────
# 5. Update the chat endpoint to use transcript files
# ─────────────────────────────────────────────────────────────

old_chat_context = '''            context_transcript = ""
            active_seed_title = ""
            if active_seed_id:
                seeds = load_seeds()
                for s in seeds:
                    if s.get("seed_id") == active_seed_id:
                        active_seed_title = s.get("intent", "").split("\\n")[0][:100]
                        context_transcript = s.get("source_transcript", "")
                        break'''

new_chat_context = '''            context_transcript = ""
            active_seed_title = ""
            source_thread_title = ""
            if active_seed_id:
                seeds = load_seeds()
                for s in seeds:
                    if s.get("seed_id") == active_seed_id:
                        active_seed_title = s.get("intent", "").split("\\n")[0][:100]
                        source_thread_title = s.get("source_thread_title", "")
                        # Load transcript from file
                        tid = s.get("source_transcript_id")
                        if tid:
                            context_transcript = load_transcript(tid) or ""
                        break'''

if old_chat_context in content:
    content = content.replace(old_chat_context, new_chat_context, 1)
    print("5. Chat endpoint updated to load transcripts from files.")
else:
    print("WARNING: Chat context block not found!")


with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "w", encoding="utf-8") as f:
    f.write(content)

print("\n=== Server patch complete ===")
