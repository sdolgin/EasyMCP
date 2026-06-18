# Skill: Deploy to Synology NAS

## When to invoke

Use this skill when:
- Deploying a new version of the MCP server to the Synology NAS
- Rotating Easynews credentials on the NAS
- Troubleshooting a container that won't start or fails healthchecks
- The user says "deploy", "push to NAS", "update the NAS", or "rotate credentials"

## Prerequisites

- SSH access to the NAS (port and user from memory/user context)
- `.env` file exists on NAS at `/volume1/tools/easynews-mcp/.env`
- Docker and docker-compose available on the NAS

## Execution sequence

### Option A: Update via GHCR pull (preferred — no build on NAS)

1. Ensure the latest image is published: check that the most recent push to `main` has a passing CI run.
2. SSH into the NAS and run:
   ```bash
   cd /volume1/tools/easynews-mcp
   sudo docker-compose pull
   sudo docker-compose up -d --force-recreate
   sudo docker-compose ps   # expect: Up (healthy)
   ```
3. Verify health from Windows:
   ```powershell
   curl.exe http://<nas-ip>:8765/health
   ```

### Option B: Build on the NAS (when compose/Dockerfile changed)

1. SCP the changed files (use `-O` flag for DSM compatibility):
   ```powershell
   scp -O -P <ssh-port> Dockerfile docker-compose.yml requirements.txt easynews_client.py server.py .dockerignore <user>@<nas-ip>:/volume1/tools/easynews-mcp/
   ```
2. SSH into the NAS and run:
   ```bash
   cd /volume1/tools/easynews-mcp
   sudo docker-compose up -d --build --force-recreate
   sudo docker-compose ps
   ```

### Credential rotation

1. SSH into the NAS.
2. Edit `/volume1/tools/easynews-mcp/.env` with new credentials.
3. `sudo docker-compose up -d --force-recreate` — **`--force-recreate` is required**, compose v1 does not detect env-file changes.
4. Verify: `curl http://localhost:8765/health`

## Triage

| Symptom | Cause | Fix |
|---|---|---|
| Container exits immediately | Missing `.env` or bad credentials | Check `.env` exists and has both `EASYNEWS_USERNAME` and `EASYNEWS_PASSWORD` |
| Health endpoint unreachable | Port not mapped or firewall | Check `docker-compose ps` shows port 8765, check DSM firewall |
| `Up (unhealthy)` | Server crashes on startup | `sudo docker logs easynews-mcp -f` — look for import errors or missing deps |
| NZB writes fail with permission denied | uid/gid mismatch with NAS ACLs | Run `id <user>` and `synoacltool -get /volume1/Incoming/nzbget/downloads/nzb`, update `user:` in compose to match |
| `--build` fails on ARM NAS | Missing QEMU/Buildx on NAS | Use Option A (pull from GHCR) instead — CI already builds arm64 |
