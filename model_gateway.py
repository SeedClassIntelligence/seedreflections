"""Task-aware model catalog and selection policy for SeedReflections.

Selection is deterministic and contains no provider secrets. Invocation remains a
separate concern so every caller can apply authorization, budgets, and telemetry.
"""

TASK_CAPABILITIES = {
    "extract": {"structured_output", "analysis"},
    "classify": {"structured_output", "analysis"},
    "summarize": {"long_context", "analysis"},
    "research": {"reasoning", "long_context"},
    "plan": {"reasoning", "structured_output"},
    "write": {"writing", "long_context"},
    "code": {"coding", "reasoning"},
    "chat": {"conversation"},
}

DEFAULT_MODELS = [
    {"id":"ollama:qwen2.5:7b","provider":"ollama","model":"qwen2.5:7b","label":"Qwen 2.5 7B","source":"open","cost_tier":"local","capabilities":["analysis","structured_output","writing","conversation"],"context_window":32768},
    {"id":"ollama:qwen2.5-coder:7b","provider":"ollama","model":"qwen2.5-coder:7b","label":"Qwen 2.5 Coder 7B","source":"open","cost_tier":"local","capabilities":["coding","reasoning","structured_output","conversation"],"context_window":32768},
    {"id":"ollama:deepseek-r1:8b","provider":"ollama","model":"deepseek-r1:8b","label":"DeepSeek R1 8B","source":"open","cost_tier":"local","capabilities":["reasoning","analysis","long_context","plan","conversation"],"context_window":32768},
    {"id":"ollama:llama3.1:8b","provider":"ollama","model":"llama3.1:8b","label":"Llama 3.1 8B","source":"open","cost_tier":"local","capabilities":["analysis","writing","conversation","long_context"],"context_window":131072},
]

TASK_ALIASES = {"reflection":"extract","ingestion":"extract","artifact":"write","planning":"plan","programming":"code","ideation":"chat"}

def normalize_task(task):
    value = str(task or "chat").strip().lower().replace("-", "_")
    return TASK_ALIASES.get(value, value if value in TASK_CAPABILITIES else "chat")

def normalize_catalog(entries=None):
    catalog=[]
    for raw in (entries or DEFAULT_MODELS):
        item=dict(raw); item["capabilities"]=sorted(set(item.get("capabilities") or []))
        if item.get("id") and item.get("provider") and item.get("model"): catalog.append(item)
    return catalog

def select_model(task, catalog=None, preferred_model_id="", selection_mode="auto", available_providers=None):
    catalog=normalize_catalog(catalog); task=normalize_task(task)
    allowed=set(available_providers or [])
    candidates=[m for m in catalog if not allowed or m["provider"] in allowed]
    if selection_mode == "manual" and preferred_model_id:
        chosen=next((m for m in candidates if m["id"]==preferred_model_id),None)
        if chosen: return {**chosen,"task":task,"selection":"manual","reason":"User-selected model"}
    required=TASK_CAPABILITIES[task]
    def score(model):
        caps=set(model.get("capabilities") or [])
        return (len(required & caps)*100 + (25 if required <= caps else 0) + min(int(model.get("context_window") or 0),200000)//10000 - (10 if model.get("cost_tier")=="premium" else 0))
    if not candidates: return None
    chosen=max(candidates,key=score)
    return {**chosen,"task":task,"selection":"auto","reason":"Best available capability match for " + task}

def public_catalog(catalog=None):
    return [{k:v for k,v in item.items() if k not in {"api_key","secret"}} for item in normalize_catalog(catalog)]
