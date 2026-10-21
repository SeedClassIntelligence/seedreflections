with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace Block 1 (reflect_selected fallback loops) new_seed definition:
block1_old = """            seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
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
            }"""

block1_new = """            seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
            new_seed = {
                "seed_id": seed_id,
                "intent": s.get("description") or s.get("title"),
                "source": "conversation_extract",
                "source_transcript": transcript,
                "status": s.get("status") or "planted",
                "growth": 0,
                "created_at": datetime.now().isoformat(),
                "completed_at": None,
                "is_cryptographically_signed": False,
                "trust_state": {"signature": "unsigned", "verification": "unverified", "lineage": "missing"}
            }"""

if block1_old in content:
    content = content.replace(block1_old, block1_new, 1)
    print("Block 1 (reflect_selected fallback) updated successfully.")
else:
    print("WARNING: Block 1 target not found!")

# Replace Block 2 (/reflect endpoint loop) new_seed definition:
block2_old = """    for s in extracted_seeds:
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
        }"""

block2_new = """    for s in extracted_seeds:
        if not isinstance(s, dict) or not s.get("title"):
            continue
        seed_id = f"seed_{datetime.now().strftime('%m%d')}_{os.urandom(4).hex()}"
        new_seed = {
            "seed_id": seed_id,
            "intent": s.get("description") or s.get("title"),
            "source": "conversation_extract",
            "source_transcript": transcript,
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
        }"""

if block2_old in content:
    content = content.replace(block2_old, block2_new, 1)
    print("Block 2 (/reflect endpoint) updated successfully.")
else:
    # Let's try matching with different indentations
    lines = content.splitlines()
    found = False
    for i in range(len(lines) - 20):
        if "for s in extracted_seeds:" in lines[i] and "new_seed = {" in lines[i+4] and '"source": "conversation_extract"' in lines[i+7]:
            # Inject source_transcript
            # Find the line that has source: conversation_extract
            for j in range(i+5, i+15):
                if '"source": "conversation_extract"' in lines[j]:
                    lines.insert(j+1, '            "source_transcript": transcript,')
                    found = True
                    break
            if found:
                break
    if found:
        content = "\n".join(lines)
        print("Block 2 updated successfully using fallback lines search.")
    else:
        print("WARNING: Block 2 target not found!")

# Replace Chat Route:
chat_route_old = """        # ── API Endpoint: Chat Mock ──
        elif path == "/api/v1/seeds/chat" or path == "/seeds/chat":
            prompt = body.get("prompt", "")
            cfg = load_config()
            self._send_json({
                "answer": f"Processed prompt: '{prompt}' inside local workspace. LLM engine: {cfg.get('llm_model', 'local')}"
            })
            return"""

chat_route_new = """        # ── API Endpoint: Chat with Seeds & Transcripts ──
        elif path == "/api/v1/seeds/chat" or path == "/seeds/chat":
            prompt = body.get("prompt", "")
            active_seed_id = body.get("active_seed_id")
            
            context_transcript = ""
            active_seed_title = ""
            if active_seed_id:
                seeds = load_seeds()
                for s in seeds:
                    if s.get("seed_id") == active_seed_id:
                        active_seed_title = s.get("intent", "").split("\\n")[0][:100]
                        context_transcript = s.get("source_transcript", "")
                        break
            
            system_prompt = (
                "You are the Seed Reflections assistant. Help the user plan, refine, and execute their coding ideas (seeds).\\n"
                "You operate within their local isolated workspace. Keep your answers concise, practical, and highly developer-aligned."
            )
            if active_seed_id:
                system_prompt += f"\\n\\nThe user is currently focusing on the Seed: '{active_seed_title}'."
                if context_transcript:
                    system_prompt += (
                        "\\nHere is the full text of the original conversation transcript from which this seed was extracted.\\n"
                        "Use this context to answer their questions, recall past details, or expand on original specifications:\\n"
                        "----------------------------------------\\n"
                        f"{context_transcript[:40000]}\\n"
                        "----------------------------------------\\n"
                    )

            cfg = load_config()
            provider = cfg.get("llm_provider", "ollama")
            api_url = cfg.get("llm_api_url", "").rstrip("/")
            api_key = cfg.get("llm_api_key", "")
            model = cfg.get("llm_model", "llama3")

            answer = ""
            
            if provider == "ollama" and api_url:
                try:
                    import urllib.request
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
                    
            elif provider == "openai" and api_key:
                try:
                    import urllib.request
                    req_payload = json.dumps({
                        "model": model or "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ]
                    }).encode("utf-8")
                    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=req_payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        answer = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                except Exception as e:
                    print(f"OpenAI chat failed: {e}")

            elif provider == "gemini" and api_key:
                try:
                    import urllib.request
                    req_payload = json.dumps({
                        "contents": [
                            {"role": "user", "parts": [{"text": f"System context:\\n{system_prompt}\\n\\nUser Question:\\n{prompt}"}]}
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
                answer = f"**[Offline Local Mode]**\\n\\nI parsed your prompt: *'{prompt}'*\\n"
                if active_seed_id:
                    answer += f"Focusing on active seed: **{active_seed_title}**.\\n\\n"
                    if context_transcript:
                        answer += "*(Loaded original conversation transcript context - 40k characters parsed).* Based on the original specifications in the conversation, the core details outline this project task. Please configure an LLM key in Settings to trigger live AI conversation."
                    else:
                        answer += "*(No original transcript context exists for this seed).* Please configure an LLM key in Settings to trigger live AI conversation."
                else:
                    answer += "\\nPlease configure an LLM API key in Settings to chat with your seed database dynamically."

            self._send_json({"answer": answer})
            return"""

if chat_route_old in content:
    content = content.replace(chat_route_old, chat_route_new, 1)
    print("Chat Route updated successfully.")
else:
    print("WARNING: Chat Route target not found!")

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch complete.")
