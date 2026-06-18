---
description: Rules for editing the MCP server layer
globs: server.py
---

# MCP server rules

- Every MCP tool is defined with `@mcp.tool()` in `server.py`. Do not create tool definitions anywhere else.
- MCP tools MUST return `str`. On error, return a string starting with `"Error: "` — never raise exceptions through the MCP boundary.
- Catch `EasynewsAuthError` in every tool that calls `easynews_client` and return a credential-check message.
- Custom HTTP routes use `@mcp.custom_route()`. Keep `/health` trivial (no auth, no side effects).
- The `/nzb/{id}` proxy route returns `application/x-nzb` with a `Content-Disposition` header. Preserve this — downstream NZB clients depend on it.
- `PUBLIC_URL` is used solely by `get_nzb_url` to build clickable links. It must not appear in other tool outputs.
- Do not import `easynews_client` internals (private functions, constants). Use only its public API: `search`, `get_nzb_url`, `fetch_nzb`, `download_nzb`, `EasynewsAuthError`.
