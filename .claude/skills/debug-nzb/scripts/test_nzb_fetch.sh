#!/usr/bin/env bash
# Quick NZB fetch diagnostic — searches, grabs the first result ID, fetches
# its NZB, and reports whether the NZB has actual file entries.
#
# Usage: test_nzb_fetch.sh [search_query]
# Requires: EASYNEWS_USERNAME and EASYNEWS_PASSWORD in environment or .env

set -euo pipefail

QUERY="${1:-linux mint iso}"

if [ -f .env ]; then
  set -a; source .env; set +a
fi

: "${EASYNEWS_USERNAME:?Set EASYNEWS_USERNAME}"
: "${EASYNEWS_PASSWORD:?Set EASYNEWS_PASSWORD}"

echo "==> Running search for '${QUERY}'..."
python -c "
from easynews_client import search, fetch_nzb
results = search('${QUERY}', max_results=1)
if not results:
    print('No results found'); exit(1)
r = results[0]
print(f'Result: {r[\"filename\"]}')
print(f'ID: {r[\"id\"][:80]}...')
token, _, sig = r['id'].partition('&sig=')
print(f'Sig present: {bool(sig)}')
print(f'Sig value: {sig[:20]}...' if sig else 'Sig: MISSING')
content, name = fetch_nzb(r['id'])
print(f'NZB size: {len(content)} bytes')
print(f'Has <nzb>: {b\"<nzb\" in content[:1024]}')
print(f'Has <file>: {b\"<file\" in content}')
if b'<file' in content:
    print('OK — NZB is valid with file entries')
else:
    print('FAIL — NZB is an empty skeleton (sig may be invalid)')
    exit(1)
"
