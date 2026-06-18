---
description: Rules for editing the Easynews API client
globs: easynews_client.py
---

# Easynews client rules

- This module is a standalone API client. It MUST NOT import `mcp`, `starlette`, `fastmcp`, or anything from `server.py`.
- All HTTP calls use `requests` with basic auth `(username, password)`. Never use session cookies or tokens.
- Credentials resolve via `_credentials()`: explicit args override env vars. Never hardcode credentials.
- The result ID format is `hash|b64(stem):b64(ext)&sig=<sig>`. The `sig` field is mandatory — without it, `dl-nzb` returns an empty NZB skeleton. Any code that constructs or parses result IDs must preserve the sig.
- Search uses the RSS 2.0 output mode (`sS=5`). The XML is parsed with stdlib `xml.etree.ElementTree` — do not add lxml or beautifulsoup dependencies.
- `_parse_item()` extracts the plain content hash from the description's `archview.html` link, NOT from the enclosure URL (which has a 4-char suffix). Getting this wrong produces invalid NZBs.
- `_sanitize_filename()` strips filesystem-illegal characters. Always use it before writing to disk.
- `fetch_nzb()` validates two things: (1) `<nzb` appears in the first 1024 bytes, (2) `<file` appears anywhere. Both checks are required — an empty skeleton passes check 1 but fails check 2.
