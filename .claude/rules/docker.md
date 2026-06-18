---
description: Rules for editing Docker and CI configuration
globs: Dockerfile,docker-compose.yml,.github/workflows/*.yml
---

# Docker & CI rules

- Dockerfile base image is `python:3.11-slim`. No curl available — healthcheck uses stdlib `urllib.request`.
- The Dockerfile creates a non-root user `mcpuser` (uid 1000). Never run as root.
- `docker-compose.yml` overrides the container user to `1028:100` for Synology NAS ACL compatibility. Do not change this without confirming the target NAS uid/gid.
- The volume mount maps the NAS NZBGet watch folder. The left side (`/volume1/Incoming/...`) is NAS-specific.
- `.env` is loaded via `env_file:` — never inline credentials in compose or Dockerfile.
- CI builds multi-arch (amd64 + arm64) via QEMU + Buildx. Do not remove arm64 — the Synology NAS may be ARM-based.
- CI uses GHA cache (`cache-from: type=gha`). Preserve this for build speed.
- Only pushes to `main` and semver tags publish images. PRs build-only (no push).
