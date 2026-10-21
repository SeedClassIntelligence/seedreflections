import re

file_path = r'c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py'

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add Cache-Control headers to static file server inside do_GET
target_cache = """            try:
                with open(safe_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()"""

replacement_cache = """            try:
                with open(safe_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                # Force browser to bypass cache on localhost reload
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()"""

content = content.replace(target_cache, replacement_cache, 1)
print("Cache control headers added to static file server.")

# 2. Add multipart parser helper at the end of the file or near helpers
helper_target = """CONFIG_FILE = "config.json\""""

multipart_helper = """CONFIG_FILE = "config.json"

def parse_multipart(content_bytes, boundary_str):
    boundary = boundary_str.encode("utf-8")
    parts = content_bytes.split(boundary)
    files = {}
    data = {}
    for part in parts:
        if not part or part == b"--\\r\\n" or part == b"--" or part == b"--\\r\\n\\r\\n":
            continue
        if b"\\r\\n\\r\\n" not in part:
            continue
        headers_part, body_part = part.split(b"\\r\\n\\r\\n", 1)
        headers = headers_part.decode("utf-8", errors="ignore")
        if body_part.endswith(b"\\r\\n"):
            body_part = body_part[:-2]
        elif body_part.endswith(b"\\r"):
            body_part = body_part[:-1]
            
        import re
        cd_match = re.search(r'Content-Disposition:\\s*form-data;\\s*name="([^"]+)"(?:;\\s*filename="([^"]+)")?', headers, re.IGNORECASE)
        if cd_match:
            name = cd_match.group(1)
            filename = cd_match.group(2)
            if filename:
                files[name] = {"filename": filename, "content": body_part}
            else:
                data[name] = body_part.decode("utf-8", errors="ignore")
    return data, files"""

content = content.replace(helper_target, multipart_helper, 1)
print("Multipart parser helper added.")

# 3. Add POST /api/v1/upload_export and POST /api/v1/reflect_selected endpoints
post_target = """        # ── API Endpoint: Save Settings ──"""

upload_endpoints = """        # ── API Endpoint: Upload Large Export JSON ──
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

            os.makedirs("uploads", exist_ok=True)
            temp_path = os.path.join("uploads", "temp_export.json")
            try:
                with open(temp_path, "wb") as f:
                    f.write(file_obj["content"])
                
                # Extract conversation summary list
                with open(temp_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                
                if not isinstance(raw_data, list):
                    self._send_json({"error": "Invalid export JSON. Expected root array of conversations."}, 400)
                    return
                
                summary = []
                for i, c in enumerate(raw_data):
                    title = c.get("title") or f"Conversation {i+1}"
                    conv_id = c.get("id") or f"idx_{i}"
                    create_time = c.get("create_time")
                    created_str = ""
                    if create_time:
                        try:
                            created_str = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d")
                        except Exception:
                            pass
                    depth = len(c.get("mapping", {}))
                    summary.append({
                        "id": conv_id,
                        "title": title,
                        "created_at": created_str,
                        "depth": depth
                    })
                
                self._send_json({
                    "status": "success",
                    "message": f"Successfully parsed {len(summary)} threads.",
                    "conversations": summary
                })
            except Exception as e:
                print(f"Error handling upload: {e}")
                self._send_json({"error": f"Failed to parse upload: {e}"}, 500)
            return

        # ── API Endpoint: Reflect Selected Conversations from Temp Upload ──
        elif path == "/api/v1/reflect_selected" or path == "/reflect_selected":
            selected_ids = body.get("conversations", [])
            if not selected_ids:
                self._send_json({"error": "Missing 'conversations' selection list"}, 400)
                return

            temp_path = os.path.join("uploads", "temp_export.json")
            if not os.path.exists(temp_path):
                self._send_json({"error": "Temporary upload session expired. Please upload file again."}, 400)
                return

            try:
                with open(temp_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                
                selected_convs = []
                for c in raw_data:
                    conv_id = c.get("id") or ""
                    if conv_id in selected_ids:
                        selected_convs.append(c)
                
                cfg = load_config()
                provider = cfg.get("llm_provider", "ollama")
                api_url = cfg.get("llm_api_url", "").rstrip("/")
                api_key = cfg.get("llm_api_key", "")
                model = cfg.get("llm_model", "llama3")
                
                seeds = load_seeds()
                assimilated = []

                for c in selected_convs:
                    title = c.get("title") or "Untitled Spark"
                    # Unroll transcript
                    transcript = f"Conversation: {title}\\n\\n"
                    mapping = c.get("mapping", {})
                    for node in mapping.values():
                        msg = node.get("message")
                        if msg and msg.get("content") and msg["content"].get("parts"):
                            parts = msg["content"]["parts"]
                            text = "\\n".join(parts) if isinstance(parts, list) else str(parts)
                            role = msg.get("author", {}).get("role", "unknown")
                            transcript += f"[{role}]: {text}\\n\\n"

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
                            "status": s.get("status") or "planted",
                            "growth": 0,
                            "created_at": datetime.now().isoformat(),
                            "completed_at": None,
                            "is_cryptographically_signed": False,
                            "trust_state": {"signature": "unsigned", "verification": "unverified", "lineage": "missing"}
                        }
                        seeds.append(new_seed)
                        assimilated.append(new_seed)
                
                save_seeds(seeds)
                
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
                            "title": s.get("intent", "").split("\\n")[0][:100],
                            "description": s.get("intent"),
                            "status": s.get("status", "planted")
                        } for s in assimilated
                    ]
                })

            except Exception as e:
                print(f"Error executing select reflection: {e}")
                self._send_json({"error": f"Failed to reflect: {e}"}, 500)
            return

        # ── API Endpoint: Save Settings ──"""

content = content.replace(post_target, upload_endpoints, 1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("server.py updated with large JSON upload streaming parsing support.")
