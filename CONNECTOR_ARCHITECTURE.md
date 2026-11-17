# SeedReflections connection architecture

**Status:** Founder-directed target architecture, not a list of live connectors.
**Decision:** Build one provider-neutral connection system. Claude is one compatibility target, not a one-off integration or the limit of the system.

## Purpose

People should be able to bring authorized work into SeedReflections, use external tools while continuing a project, and let supported assistants work with SeedReflections context. The connection layer must preserve source provenance, workspace ownership, scope, revocation, and the difference between a provider's model API and access to its consumer account history.

## Three connection directions

| Direction | SeedReflections role | Example | Result |
|---|---|---|---|
| Connect a source or service into SeedReflections | OAuth client or MCP client | User authorizes a supported Drive, GitHub, design, or AI-work service | Read only the resources and operations the provider actually grants; normalize selected content into sources or use it as a scoped project tool. |
| Connect an assistant to SeedReflections | OAuth-protected MCP server | User adds SeedReflections as a custom connector in Claude or another MCP client | Assistant searches permitted SeedReflections content and, with explicit write scope, saves selected work into a project. |
| Use an AI model inside SeedReflections | Model API client | Local open model or configured hosted model | Model inference for selected tasks. Model authorization is separate from source access and tool authorization. |

The MyDesigns example demonstrates the second row: MyDesigns exposes an MCP server; Claude connects as the client; the user authorizes access to MyDesigns. The same pattern can expose SeedReflections to Claude and other compatible assistants. It does not grant SeedReflections the user's historical Claude chats. Those require a supported export, local source, explicit delivery, or a provider-authorized history interface if one exists.

## Common connector contract

Every adapter must declare a stable provider ID, transport, authentication method, supported capabilities, requested scopes, identity and workspace mapping, data types, cursor or sync behavior, rate limits, and disconnect behavior. The UI must show **available**, **configuration required**, **authorization required**, **connected**, **limited**, or **unavailable** based on an actual capability probe. A catalog entry is never represented as a live connection.

Authentication methods are selected per provider: OAuth authorization code with PKCE where supported; MCP authorization for remote MCP servers; OS-protected local credentials for local companions; and scoped API tokens where OAuth is unavailable and permitted. Open-source and local models may need no account authorization at all. One shared OAuth framework does not make every platform expose the same resources.

For OAuth connections, bind state and PKCE to the initiating user, workspace, provider, and short-lived transaction. Use exact registered redirect URIs; validate issuer, audience/resource, scopes, and callback parameters; encrypt access and refresh tokens; rotate or replace refreshed tokens; never return them to the browser. Record granted scopes and expiry, support reconnect and revocation, and keep source records after disconnect unless the user separately deletes them. Apply tenant and role authorization to every tool call and imported item.

## SeedReflections as an MCP server

Expose a hosted HTTPS MCP endpoint with OAuth resource discovery and per-user authorization. Begin with narrow tools: search permitted conversations, fetch cited source passages, get project context, and create or revise an artifact in a selected project. Read tools and write tools must have separate scopes. A tool response includes source IDs and links where applicable. A write records actor, client, target workspace, source references, and result. The server never returns an entire archive just because a client connected.

The local-only product needs a local MCP transport or the desktop companion for compatible desktop clients. Do not advertise a loopback URL as a working remote Claude web connector; that requires a reachable HTTPS service. Keep local files under the user's selected scope.

## SeedReflections as an OAuth and MCP client

Provide a single **Connections** experience inside Workspace and Settings. The user chooses a provider, sees its actual read/write capabilities, signs in, chooses the permitted project or source scope, tests the connection, and can revoke it. A connector can import data, provide tools during a working conversation, or both. Tool results that matter become inspectable sources or durable artifacts with provenance.

Implement provider adapters behind the common contract. Migrate the existing Google Drive connection into that contract, then prove portability with another OAuth-backed service and an external MCP server. Add providers according to their published permissions. Claude-specific support should include the inbound SeedReflections MCP connection and any separately authorized Claude-related data path that actually exists. Do not promise a universal pull of private conversation histories or treat an Anthropic model API key as a history token.

## Current implementation versus target

Today the repository has SeedBridge local-source intake, a scoped integration-delivery token, and a Google Drive OAuth connection for read-only folder review, import, sync, and disconnect. Google Drive is a provider-specific implementation; it does not establish a reusable OAuth connector framework. `tool_store.py` lists other external tools, but their connection route in `server.py` returns `authorization_handoff_unavailable` after provider configuration. The current `/mcp` endpoint offers read-only workspace tools using a SeedReflections bearer grant. It does not yet provide OAuth discovery/consent for remote MCP clients or scoped write tools. The provider-neutral OAuth lifecycle, additional provider adapters, and OAuth-protected MCP server remain work items.

## Acceptance evidence

1. A user connects one real OAuth provider, sees the exact scopes, imports or uses one selected resource, reconnects after expiry, and revokes access without losing previously imported evidence.
2. A second provider with different scopes and data shapes uses the same lifecycle without copying the first provider's auth logic.
3. A supported MCP client connects to the hosted SeedReflections MCP endpoint through OAuth, searches only its authorized workspace, receives cited context, and writes an artifact only with the proper scope and project target.
4. A local MCP client uses the local transport without exposing the local HTTP server to remote hosts or broad browser origins.
5. Cross-tenant, wrong-scope, expired, replayed, and revoked requests fail. Logs and API responses contain no tokens. Capability status reflects actual connection state.
6. The public UI and documentation distinguish model access, source access, and tool access and show the fallback import path when a provider offers no supported OAuth resource.

## Standards and provider references

- [MCP authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- [OAuth 2.0 Security Best Current Practice, RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [Claude custom connector instructions](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [MyDesigns MCP documentation](https://mydesigns.io/docs/integrations/mcp)
