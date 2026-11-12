# Workspace assistant (branch `claude/workspace-agent`, not merged)

For founder review. Backend change: `server.py` (`/api/v2/chat`), new `workspace_agent.py`, new `model_invoke.py`, tests in `tests/test_workspace_agent.py`, and a small dashboard change (sources and honest fallback note in the chat).

## What it does
The Workspace chat now calls the model the platform is configured with (Ollama, OpenAI-compatible, Anthropic, Gemini) through a bounded loop. The model can use four **read-only** tools on the signed-in workspace: `search_archive`, `read_conversation`, `list_findings`, `list_ideas`. It answers from what it read and the page lists the conversations it actually read as sources.

## Rules it enforces (tested)
- **Read only.** It cannot accept, edit, delete or export. Findings still become project memory only when the user accepts them.
- **Workspace comes from the session**, never from the model. A hosted workspace cannot read another's archive through chat (test: tenant isolation).
- **Archive text is untrusted data.** It is wrapped as data, unknown tools are refused, and since nothing can write, a hostile passage cannot change anything (test).
- **Bounded:** 5 tool steps, capped result sizes (6,000 characters), last 6 turns of history, 1,200-token replies.
- **Existing controls apply:** the budget cap and kill switch (`check_ai_gateway_status`), usage recorded as `workspace_agent`, optional daily cap per workspace via `SEED_REFLECTIONS_AGENT_DAILY_LIMIT` (0 = no cap).
- **No model, no pretending.** With no model, no key, the kill switch on, a budget stop, or a provider error, the chat returns the old records-only answer plus the reason, and the page says "No model answered this one: <reason>".
- Keys: read through the existing credential path. They are never logged, returned, or placed in a URL (Gemini key is sent in a header). Provider error text never includes the URL or response body.
- Model text is shown through the dashboard's escaping markdown renderer (no raw HTML, no links or images).

## Not done (needs your decisions)
- **Plan-based limits.** Only a single env cap exists. Per-plan numbers (Free/Pro/Master) are your call.
- **One provider connection per deployment/workspace.** Choosing a model from a different provider than the configured one needs a multi-provider setup. `model_id` in the request selects among the configured provider's models.
- **Streaming**, a model picker in the chat, and chat persistence across reloads.
- **Writing tools** (draft an artifact, propose a finding). Deliberately left out of the first slice; they should create drafts or proposals only.
- **Code execution / file editing** like a coding assistant: needs sandboxing; not in scope.
- Hosted BYO key handling depends on the deployment's secret master key (existing behaviour); not changed.
- The platform AI budget counter (`TELEMETRY_LOG`) is process-local (existing behaviour); the daily cap counter is too.

## Checked
16 new tests (loop, hostile text, step cap, history bounds, provider request shapes, key never in errors, tenant isolation, endpoint modes). End to end with a stand-in Ollama server and the real dashboard: the model asked for a search, got archive results, answered with sources, usage was recorded.
Not checked: a real provider (Anthropic, OpenAI, Gemini, a real Ollama model). The request shapes are tested against fakes only.

## Bring your own assistant (MCP) — added on this branch
Fallback for when plan limits run out, or for people who prefer their own tool. An outside assistant (Claude Code, Codex, any MCP client) connects to `POST /mcp` and gets the same four read-only tools.

- **Tokens:** created in Settings → "Connect your own assistant" (or `POST /api/v2/agent-tokens`). Shown once, stored only as a SHA-256 digest, tied to the creating session's workspace, 90-day expiry, revocable, at most 10 active per workspace. A viewer role cannot create tokens.
- **Only valid on `/mcp`.** The server never accepts an agent token as a login session.
- **Protocol:** MCP over HTTP (JSON-RPC 2.0, plain JSON replies): `initialize`, `ping`, `tools/list`, `tools/call`; notifications get 202; GET returns 405. Every tool is marked read-only.
- **Limits:** 64 KB request body, 60 calls per minute per token, results capped at 6,000 characters, cross-origin requests refused (and local mode keeps its loopback Host/Origin rule).
- **Same rules as the built-in assistant:** the workspace comes from the token, never from the client; archive text is returned as data and nothing can write, so a hostile passage cannot change anything.
- **Not covered:** per-tool permissions beyond read-only, token scopes by project, an audit log beyond `last used` and a use count, and the Streamable-HTTP streaming/session features (replies are plain JSON).
- **Checked:** 10 new tests (token store, protocol, every rejection path over real HTTP, 188 total pass); a real handshake and tool calls against the running server using a token created in the page; revoke through the real button gives 401.
- **Not checked:** a real MCP client (for example Claude Code itself). The protocol is implemented to the spec as I understand it and tested with plain HTTP; client quirks may show up on first real use.
