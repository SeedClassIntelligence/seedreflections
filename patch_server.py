import re

file_path = r'c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py'

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add CONFIG_FILE and config loading helpers under ENV_FILE (line 21)
helpers_addition = """CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "llm_provider": "ollama",
        "llm_api_url": "http://127.0.0.1:11434",
        "llm_model": "llama3",
        "llm_api_key": ""
    }

def save_config(config_data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False"""

content = content.replace('ENV_FILE = ".env"', 'ENV_FILE = ".env"\n' + helpers_addition, 1)
print("Config helpers added.")

# 2. Add GET endpoints inside do_GET(self)
get_target = """        # ── Static File Server ──"""

get_addition = """        # ── API Endpoint: Get Current User ──
        elif path == "/api/v1/users/me" or path == "/users/me":
            self._send_json({
                "id": 1,
                "name": "Local Developer",
                "email": "local@workspace",
                "active_plan": "standalone",
                "role": "developer"
            })
            return

        # ── API Endpoint: Get Consumer Dashboard Info ──
        elif path == "/api/v1/users/me/consumer-dashboard":
            seeds = load_seeds()
            self._send_json({
                "plan": "standalone",
                "seeds_used": len(seeds),
                "seeds_limit": 10000,
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

        # ── Static File Server ──"""

content = content.replace(get_target, get_addition, 1)
print("GET endpoints added.")

# 3. Add POST endpoints inside do_POST(self)
# Let's add them before the final send_error(404) at the end of do_POST
post_target = """        self.send_error(404, "Endpoint Not Found")"""

post_addition = """        # ── API Endpoint: Save Settings ──
        elif path == "/api/v1/settings":
            save_config(body)
            self._send_json({"status": "saved", "config": body})
            return

        # ── API Endpoint: Reflect (Extract Seeds via LLM or Local Heuristics) ──
        elif path == "/api/v1/reflect" or path == "/reflect":
            transcript = body.get("transcript", "").strip()
            if not transcript:
                self._send_json({"error": "Missing 'transcript' field"}, 400)
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
                "or core tasks that the user initiated or proposed).\\n"
                "Return the results ONLY as a JSON array of objects with these exact keys: "
                "'title', 'description', 'status' (must be one of: 'planted', 'germinating', 'growing', 'bloomed', 'wilted'). "
                "Do not include any chat formatting, markdown backticks, or text before/after the JSON array.\\n\\n"
                f"Transcript:\\n{transcript}"
            )

            # Try to query LLM if configured
            if provider == "ollama" and api_url:
                try:
                    import urllib.request
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

            elif provider == "openai" and api_key:
                try:
                    import urllib.request
                    req_payload = json.dumps({
                        "model": model or "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"}
                    }).encode("utf-8")
                    
                    req = urllib.request.Request(
                        "https://api.openai.com/v1/chat/completions",
                        data=req_payload,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {api_key}"
                        },
                        method="POST"
                    )
                    
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        content = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        parsed = json.loads(content)
                        # OpenAI might wrap it in a root key
                        if isinstance(parsed, dict):
                            for k in parsed:
                                if isinstance(parsed[k], list):
                                    extracted_seeds = parsed[k]
                                    break
                            else:
                                extracted_seeds = [parsed]
                        else:
                            extracted_seeds = parsed
                        extraction_method = f"openai_cloud_{model}"
                except Exception as e:
                    print(f"OpenAI call failed, falling back to heuristics: {e}")

            # Heuristics Fallback Parser
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

            # Auto-save extracted seeds directly into seeds.json database
            seeds = load_seeds()
            assimilated = []
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
                    "trust_state": {
                        "signature": "unsigned",
                        "verification": "unverified",
                        "lineage": "missing"
                    }
                }
                seeds.append(new_seed)
                assimilated.append(new_seed)
            
            save_seeds(seeds)

            self._send_json({
                "assimilation_stats": {
                    "new_seed": len(assimilated),
                    "total_processed": len(extracted_seeds)
                },
                "answer": f"Assimilated {len(assimilated)} seeds from your conversation transcript using **{extraction_method}** engine.",
                "seeds": [
                    {
                        "title": s.get("intent", "").split("\\n")[0][:100],
                        "description": s.get("intent"),
                        "status": s.get("status", "planted")
                    } for s in assimilated
                ]
            })
            return

        # ── API Endpoint: Chat Mock ──
        elif path == "/api/v1/seeds/chat" or path == "/seeds/chat":
            prompt = body.get("prompt", "")
            cfg = load_config()
            self._send_json({
                "answer": f"Processed prompt: '{prompt}' inside local workspace. LLM engine: {cfg.get('llm_model', 'local')}"
            })
            return

        self.send_error(404, "Endpoint Not Found")"""

content = content.replace(post_target, post_addition, 1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("server.py updated successfully.")
