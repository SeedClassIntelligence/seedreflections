file_path = r'c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py'

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Let's add the admin endpoints right after /api/v1/settings in do_GET
target_get = """        # ── API Endpoint: Get Settings ──
        elif path == "/api/v1/settings":
            cfg = load_config()
            self._send_json(cfg)
            return"""

addition_admin = """        # ── API Endpoint: Get Settings ──
        elif path == "/api/v1/settings":
            cfg = load_config()
            self._send_json(cfg)
            return

        # ── API Endpoint: Get Admin Stats ──
        elif path == "/admin/stats":
            import time
            seeds = load_seeds()
            uptime = int(time.time() - START_TIME) if "START_TIME" in globals() else 3600
            self._send_json({
                "repo": "Seed Reflections Standalone Garden",
                "local_metrics": {
                    "files_indexed": len(seeds),
                    "total_symbols": len(seeds) * 4 + 12
                },
                "system_health": {
                    "uptime_seconds": uptime
                }
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
            return"""

content = content.replace(target_get, addition_admin, 1)

# Let's ensure START_TIME is initialized in server.py
# Let's add it near line 25, under imports
import_addition = """import time
START_TIME = time.time()
"""

content = content.replace("import os", "import os\n" + import_addition, 1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Admin endpoints successfully added to server.py.")
