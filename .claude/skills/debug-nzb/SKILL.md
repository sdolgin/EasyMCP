# Skill: Debug NZB Download Failures

## When to invoke

Use this skill when:
- An NZB download produces an empty or invalid file
- NZBGet reports "file has no content" or similar errors
- `download_nzb` or `fetch_nzb` returns an error about empty NZBs
- The user reports that a download "didn't work" after a successful search

## Background

Easynews's `dl-nzb` endpoint has a subtle failure mode: it returns HTTP 200 with a valid XML skeleton (`<nzb xmlns="..."></nzb>`) but **zero `<file>` entries** when the request signature (`sig`) is missing or stale. This looks like success to naive HTTP-level checks.

The result ID format is: `hash|b64(stem):b64(ext)&sig=<sig_value>`

The `sig` is a session-scoped token from the original search RSS response. It expires, and there is no refresh mechanism — the only fix is to re-run the search.

## Diagnostic sequence

### Step 1: Reproduce and inspect

```python
from easynews_client import fetch_nzb
content, filename = fetch_nzb("<result_id>")
print(f"Size: {len(content)} bytes")
print(f"Has <nzb>: {b'<nzb' in content[:1024]}")
print(f"Has <file>: {b'<file' in content}")
print(content[:500].decode(errors='replace'))
```

### Step 2: Parse the result ID

```python
token, _, sig = "<result_id>".partition("&sig=")
print(f"Token: {token}")
print(f"Sig: {sig}")
print(f"Sig present: {bool(sig)}")
```

If `sig` is empty → the result ID was constructed without a sig. Check `_parse_item()` in `easynews_client.py` — the sig is extracted from the enclosure URL's query string.

### Step 3: Check sig freshness

Re-run the same search and compare the sig in the new results to the old one. If they differ, the old sig expired — this is expected behavior.

### Step 4: Verify the POST payload

The `dl-nzb` endpoint expects form data: `{"autoNZB": "1", "0&sig=<sig>": "<token>"}`. The form key itself contains `&sig=`. Run `scripts/test_nzb_fetch.sh` or:

```python
import requests
from easynews_client import _credentials
auth = _credentials(None, None)
token, _, sig = "<result_id>".partition("&sig=")
form_key = f"0&sig={sig}" if sig else "0"
r = requests.post("https://members.easynews.com/2.0/api/dl-nzb",
                   data={"autoNZB": "1", form_key: token}, auth=auth, timeout=60)
print(r.status_code, len(r.content), r.content[:300])
```

## Resolution

| Finding | Fix |
|---|---|
| Sig is empty in result ID | Bug in `_parse_item()` — the sig extraction from the enclosure URL query string is broken |
| Sig is present but expired | Expected. Re-run the search to get fresh result IDs with new sigs |
| POST returns HTML login page | Credentials invalid — check `EASYNEWS_USERNAME` / `EASYNEWS_PASSWORD` |
| POST returns valid NZB with `<file>` entries | The download pipeline works; issue is downstream (NZBGet config, file permissions) |
