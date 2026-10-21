import re

file_path = r'c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py'

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Let's replace the upload_export endpoint in server.py
old_upload_route = """        # ── API Endpoint: Upload Large Export JSON ──
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
            return"""

new_upload_route = """        # ── API Endpoint: Upload Large Export JSON ──
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
                    if not isinstance(c, dict):
                        continue
                    
                    title = c.get("title") or c.get("name") or c.get("subject")
                    depth = 0
                    snippet = ""
                    
                    # Case A: ChatGPT mapping format
                    if "mapping" in c and isinstance(c["mapping"], dict):
                        mapping = c["mapping"]
                        depth = len(mapping)
                        first_user_text = ""
                        for node in mapping.values():
                            msg = node.get("message")
                            if msg and msg.get("author", {}).get("role") == "user":
                                content_parts = msg.get("content")
                                if content_parts and content_parts.get("parts"):
                                    parts = content_parts["parts"]
                                    first_user_text = "\\n".join(parts) if isinstance(parts, list) else str(parts)
                                    if first_user_text:
                                        break
                        if first_user_text:
                            snippet = first_user_text[:120].strip() + ("..." if len(first_user_text) > 120 else "")
                            
                    # Case B: Claude chat_messages format
                    elif "chat_messages" in c and isinstance(c["chat_messages"], list):
                        chat_msgs = c["chat_messages"]
                        depth = len(chat_msgs)
                        first_human_msg = next((m for m in chat_msgs if m.get("sender") in ("human", "user")), {})
                        first_user_text = first_human_msg.get("text") or ""
                        if first_user_text:
                            snippet = first_user_text[:120].strip() + ("..." if len(first_user_text) > 120 else "")
                            
                    # Case C: Generic messages list format
                    elif "messages" in c and isinstance(c["messages"], list):
                        msgs = c["messages"]
                        depth = len(msgs)
                        first_user_text = ""
                        for m in msgs:
                            role = m.get("role") or m.get("sender") or ""
                            if role in ("user", "human", "customer"):
                                content_val = m.get("content") or m.get("text") or ""
                                if isinstance(content_val, dict):
                                    content_val = content_val.get("text") or content_val.get("parts") or ""
                                first_user_text = str(content_val)
                                if first_user_text:
                                    break
                        if first_user_text:
                            snippet = first_user_text[:120].strip() + ("..." if len(first_user_text) > 120 else "")
                    
                    if not snippet and depth > 0:
                        snippet = f"Conversation containing {depth} message turns."
                        
                    if not title:
                        if snippet:
                            title = snippet[:40].strip() + ("..." if len(snippet) > 40 else "")
                        else:
                            title = f"Conversation {i+1}"
                            
                    create_time = c.get("create_time") or c.get("created_at") or c.get("updated_at")
                    created_str = ""
                    if create_time:
                        if isinstance(create_time, (int, float)):
                            try:
                                created_str = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d")
                            except Exception:
                                pass
                        elif isinstance(create_time, str):
                            created_str = create_time[:10]
                            
                    summary.append({
                        "id": c.get("id") or c.get("uuid") or f"idx_{i}",
                        "title": title,
                        "snippet": snippet,
                        "created_at": created_str or "—",
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
            return"""

content = content.replace(old_upload_route, new_upload_route, 1)
print("upload_export endpoint updated in content string.")

# Let's replace the reflect_selected endpoint in server.py
old_reflect_selected = """        # ── API Endpoint: Reflect Selected Conversations from Temp Upload ──
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

                    # Run reflect extraction prompt"""

new_reflect_selected = """        # ── API Endpoint: Reflect Selected Conversations from Temp Upload ──
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
                    conv_id = c.get("id") or c.get("uuid") or ""
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

                    # Run reflect extraction prompt"""

content = content.replace(old_reflect_selected, new_reflect_selected, 1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("server.py updated with adaptive multi-format JSON parser.")
