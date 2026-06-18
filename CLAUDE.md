# EasyMCP — Easynews MCP Server

## Stack

- Python 3.11 (Docker base), FastMCP (`mcp[cli]>=1.6.0`), Starlette, Uvicorn
- Transport: streamable-http on port 8765
- Docker multi-arch (amd64/arm64), deployed on Synology NAS (DSM 7.x)
- CI: GitHub Actions → GHCR (`ghcr.io/sdolgin/easymcp`)

## Source files (entire codebase)

| File | Role |
|---|---|
| `server.py` | MCP server: 3 tools + 2 HTTP routes. Entry point. |
| `easynews_client.py` | Pure API client. No MCP imports. All Easynews HTTP logic lives here. |
| `test_client.py` | Integration smoke tests (hits live Easynews API). Requires `.env` credentials. |
| `Dockerfile` | Single-stage slim image. Non-root `mcpuser` (uid 1000). |
| `docker-compose.yml` | Production config for Synology NAS. Pulls from GHCR. |
| `.github/workflows/docker-publish.yml` | Builds + pushes multi-arch image on push to main or semver tags. |

## Build & test

```bash
# Local dev
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill EASYNEWS_USERNAME, EASYNEWS_PASSWORD (Windows: copy .env.example .env)
python test_client.py    # 4 smoke tests (live API — needs real credentials)
python server.py         # starts on :8765

# Docker
docker build -t easymcp .
docker run --env-file .env -p 8765:8765 easymcp

# MCP Inspector
npx -y @modelcontextprotocol/inspector --cli http://localhost:8765/sse --transport sse --method tools/list
```

## Architecture constraints

- `easynews_client.py` MUST NOT import from `mcp`, `starlette`, or `server`. It is a standalone API client.
- `server.py` is the only file that imports FastMCP and defines MCP tools/routes.
- All Easynews HTTP calls go through `requests` with `auth=(user, pass)` basic auth. Credentials resolve from env vars or explicit args — never hardcoded.
- Result IDs are self-contained tokens: `hash|b64(name):b64(ext)&sig=<sig>`. The `sig` is mandatory — without it, Easynews returns an empty `<nzb/>` skeleton (HTTP 200, not an error).

## Environment variables

| Var | Required | Default | Notes |
|---|---|---|---|
| `EASYNEWS_USERNAME` | yes | — | Easynews account |
| `EASYNEWS_PASSWORD` | yes | — | Easynews account |
| `EASYNEWS_DOWNLOAD_PATH` | no | `/downloads/nzb` | NZB save dir (mapped to NZBGet watch folder) |
| `MCP_HOST` | no | `0.0.0.0` | Bind address |
| `MCP_PORT` | no | `8765` | Bind port |
| `MCP_PUBLIC_URL` | no | `http://localhost:8765` | Used to build NZB download URLs |

## Code style

- No type stubs or mypy. Use `str | None` union syntax (Python 3.10+).
- No classes except `EasynewsAuthError`. Functions only.
- Error returns from MCP tools are plain strings starting with `"Error: "`, not exceptions.
- MCP tools return markdown-formatted strings (tables, code blocks).
- No comments explaining what code does — only why.

## Docker / deployment

- Dockerfile uses `python:3.11-slim`. Healthcheck uses stdlib `urllib` (no curl in slim).
- `docker-compose.yml` sets `user: "1028:100"` to match Synology NAS ACLs. This uid/gid is NAS-specific.
- `.env` is never committed. `.env.example` is the template.
- After `.env` or compose changes on DSM, `--force-recreate` is required — compose v1 won't detect env-file changes.
- DSM ships `docker-compose` (hyphenated, v1), not `docker compose` (v2 subcommand).

## CI pipeline

- Triggers: push to `main`, semver tags (`v*`), PRs against `main`.
- PRs build but do not push. Pushes to `main` publish `latest`. Tags publish semver.
- Multi-arch via QEMU + Buildx. GHA cache enabled.
- GHCR auth uses `GITHUB_TOKEN` (no extra secrets needed).

## Security boundaries

- `/health` and `/nzb/{id}` are unauthenticated. Port 8765 must stay LAN-only.
- Never port-forward 8765 to the internet.
- `.env` contains plaintext credentials — `chmod 600` on the NAS.
