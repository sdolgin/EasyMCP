# easynews-mcp

A Dockerized MCP server that wraps the [Easynews](https://www.easynews.com/) Usenet
service and exposes it as tools in Claude Desktop. Runs as a persistent container on
a Synology NAS (DSM 7.x); Claude Desktop on Windows connects to it over the LAN via
SSE, bridged through [`mcp-remote`](https://www.npmjs.com/package/mcp-remote).

```
Windows 11 Claude Desktop ──(stdio)── npx mcp-remote ──(SSE, LAN)──► NAS container :8765
                                                                        │  volume mount
                                                                        ▼
                                                          NZBGet watch folder ──► NZBGet
```

## Tools

| Tool | What it does | Example prompt |
|---|---|---|
| `search_usenet` | Search Easynews; returns a table + JSON with result IDs | *"Search Usenet for Ubuntu 24.04 ISO, show me 10 results"* |
| `get_nzb_url` | Returns a GET-able NZB link served by this container | *"Get the NZB URL for the first result"* |
| `download_nzb` | Saves the NZB straight into the NZBGet watch folder | *"Download the NZB for result 3"* |

`search_usenet` accepts an optional `file_type` (video, audio, image, text, archive)
and `max_results`. Result IDs are self-contained tokens (`hash|b64(name):b64(ext)&sig=…`);
no state is kept between calls.

Plain HTTP routes on the same port: `GET /health` (Docker healthcheck, no auth) and
`GET /nzb/{id}` (proxies Easynews's POST-only NZB endpoint — this is what `get_nzb_url`
links point at). **Neither requires authentication — keep port 8765 LAN-only.**

## Prerequisites

- Easynews account
- Synology NAS with Container Manager (provides `docker` and `docker-compose` —
  note DSM ships compose as the **hyphenated** `docker-compose`, not `docker compose`)
- Claude Desktop on Windows 11, plus Node.js (for the `mcp-remote` bridge)
- NZBGet (or similar) watching a folder on the NAS

## Setup

### 1. Files onto the NAS

From the project directory on Windows (DSM has SFTP disabled by default, so force
the legacy scp protocol with `-O`; `-P` is your SSH port):

```powershell
scp -O -P <ssh-port> Dockerfile docker-compose.yml requirements.txt easynews_client.py server.py .dockerignore <user>@<nas-ip>:/volume1/tools/easynews-mcp/
```

### 2. Configuration

Create `.env` on the NAS (never copy your local one; never commit it):

```
EASYNEWS_USERNAME=...
EASYNEWS_PASSWORD=...
EASYNEWS_DOWNLOAD_PATH=/downloads/nzb
MCP_HOST=0.0.0.0
MCP_PORT=8765
MCP_PUBLIC_URL=http://<nas-ip>:8765
```

```bash
chmod 600 .env
```

`MCP_PUBLIC_URL` is the address *clients* use to reach the server — `get_nzb_url`
builds its links from it.

### 3. docker-compose.yml — two values to check

- **Volume:** the left side of the volume mapping must be your actual NZBGet watch
  folder (NZBGet Settings → Paths → NzbDir):

  ```yaml
  volumes:
    - /volume1/Incoming/nzbget/downloads/nzb:/downloads/nzb
  ```

- **User:** the container must run as a uid that Synology's ACLs allow to write to
  that folder. Mode bits lying to you (`777` but writes fail) means ACLs — check with
  `synoacltool -get <watch-folder>` and `id <user>`, then set:

  ```yaml
  user: "1028:100"   # uid:gid of a DSM user the ACL allows
  ```

### 4. Build and run

```bash
cd /volume1/tools/easynews-mcp
sudo docker-compose up -d --build
sudo docker-compose ps          # expect: Up (healthy)
curl http://localhost:8765/health
```

### 5. Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json` — the config file only supports stdio
servers (a bare `"url"` entry is ignored), so use the `mcp-remote` bridge.
`--allow-http` is required for a plain-HTTP LAN URL:

```json
{
  "mcpServers": {
    "easynews": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://<nas-ip>:8765/sse", "--transport", "sse-only", "--allow-http"]
    }
  }
}
```

Fully quit Claude Desktop (system tray → Quit) and relaunch.

## Maintenance runbook

| Task | Command (on the NAS) |
|---|---|
| View logs | `sudo docker logs easynews-mcp -f` |
| Update after code changes | scp the changed files over, then `sudo docker-compose up -d --build` |
| Rotate credentials | edit `.env`, then `sudo docker-compose up -d --force-recreate` |
| Restart | `sudo docker-compose restart` |
| Health from Windows | `curl.exe http://<nas-ip>:8765/health` |

Gotchas learned the hard way:

- **`--force-recreate` is required** after `.env` or compose edits — DSM's compose v1
  won't recreate the container on env-file changes by itself.
- **Container restarts drop live SSE sessions.** The first tool call afterwards may
  fail (`Invalid request parameters`); the bridge reconnects on the next call. No
  Claude Desktop restart needed.
- **The NZB `sig` is mandatory.** Easynews's `dl-nzb` endpoint returns HTTP 200 with
  an *empty* `<nzb/>` skeleton when the sig is missing — the client embeds the sig in
  every result ID and rejects empty NZBs, so "file has no content" errors in NZBGet
  mean a stale ID from an old search: just search again.

## Development

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # fill in credentials
python test_client.py     # 4 smoke tests against the live API
python server.py          # local server on :8765
npx -y @modelcontextprotocol/inspector --cli http://localhost:8765/sse --transport sse --method tools/list
```

## Known limitations

- Search uses Easynews's 1.0 RSS output (`sS=5`); very old posts may lack a parseable
  timestamp (`age_days: null`) or newsgroup.
- `/nzb/{id}` and `/health` are unauthenticated by design — do not port-forward 8765
  to the internet.
- Easynews caps page size server-side; very large `max_results` values are clamped.
- No retry/rate-limit handling — Easynews hasn't shown limits in practice, but bulk
  automation may want backoff.
