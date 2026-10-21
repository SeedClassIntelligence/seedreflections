# Architecture Specification

```mermaid
graph TD
    Client[Browser Frontend] -->|API REST Requests| Controller[server.py HTTP Request Handler]
    Controller -->|API Calls| LLM[Ollama / Gemini / Together / OpenAI]
    Controller -->|Read/Write| DB[(seeds.json Database)]
    Client -->|Checkout Redirects| Stripe[Stripe Billing Gateway]
```

### Components
* **API Handler**: Custom class extending python's `BaseHTTPRequestHandler`. Implements thread-safe file operations, JSON responses, and CORS preflight.
* **Extraction Pipeline**: Unified orchestrator with tiered fallback adapters.
* **Sovereign Client-side Platform**: Handles token auth, mock persistence, and clean URL redirects.
