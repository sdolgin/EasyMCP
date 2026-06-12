import os
import tempfile

from dotenv import load_dotenv

from easynews_client import search, download_nzb, EasynewsAuthError

load_dotenv()

# Test 1: Basic search
results = search("linux mint iso", max_results=5)
assert len(results) > 0, "Expected results, got none"
assert all(k in results[0] for k in ["id", "filename", "size_bytes"]), "Missing keys"
print(f"OK Search — {len(results)} results, first: {results[0]['filename']}")
print(f"   id={results[0]['id'][:60]}...  size={results[0]['size_bytes']} bytes  "
      f"age={results[0]['age_days']}d  group={results[0]['newsgroup']}")

# Test 2: Auth failure
try:
    search("test", username="baduser", password="badpass")
    print("FAIL Auth test — should have raised EasynewsAuthError")
except EasynewsAuthError:
    print("OK Auth error handling")

# Test 3: No results
empty = search("asdfjkl1234567890xyz_noresults_test")
assert empty == [], f"Expected [], got {empty}"
print("OK Empty results")

# Test 4: NZB download (full pipeline: RSS-derived ID -> dl-nzb POST -> file)
with tempfile.TemporaryDirectory() as tmp:
    path = download_nzb(results[0]["id"], tmp)
    assert os.path.isfile(path), f"NZB file not written: {path}"
    with open(path, "rb") as handle:
        content = handle.read()
    assert b"<nzb" in content[:1024], f"Saved file is not an NZB: {content[:100]!r}"
    assert b"<file" in content, "NZB has no <file> entries (empty skeleton)"
    print(f"OK NZB download — {os.path.basename(path)} ({os.path.getsize(path)} bytes)")
