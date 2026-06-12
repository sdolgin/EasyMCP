"""Easynews API client — pure business logic, no MCP knowledge.

Search uses the 1.0 global5 endpoint with ``sS=5``, which switches the response
to RSS 2.0 XML (parsed with stdlib ElementTree). NZB generation uses the 2.0
``dl-nzb`` endpoint, which only accepts POST requests; the result ID returned
by :func:`search` is the self-contained Easynews "value token"
(``hash|b64(filename):b64(ext)``) that endpoint expects, so no per-session
state is needed between calls.
"""

import base64
import os
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote, unquote, urlsplit

import requests

BASE_URL = "https://members.easynews.com"
SEARCH_URL = f"{BASE_URL}/1.0/global5/search.html"
NZB_POST_URL = f"{BASE_URL}/2.0/api/dl-nzb"
REQUEST_TIMEOUT = 60

# Easynews file-type classes accepted by the fty[] search parameter.
FILE_TYPES = {
    "video": "VIDEO",
    "audio": "AUDIO",
    "image": "IMAGE",
    "text": "TEXT",
    "archive": "ARCHIVE",
}

_SIZE_UNITS = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024**2,
    "MB": 1024**2,
    "G": 1024**3,
    "GB": 1024**3,
    "T": 1024**4,
    "TB": 1024**4,
}


class EasynewsAuthError(Exception):
    """Raised when Easynews returns HTTP 401."""


def _credentials(username, password):
    """Resolve credentials from arguments or environment variables."""
    username = username or os.environ.get("EASYNEWS_USERNAME")
    password = password or os.environ.get("EASYNEWS_PASSWORD")
    if not username or not password:
        raise ValueError(
            "Easynews credentials missing: set EASYNEWS_USERNAME and "
            "EASYNEWS_PASSWORD or pass username/password explicitly."
        )
    return username, password


def _b64(value):
    return base64.b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _b64_decode(value):
    return base64.b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")


def _parse_size(text):
    """Convert an Easynews human-readable size ('468.1 K', '430.0 MB') to bytes."""
    if not text:
        return 0
    match = re.match(r"\s*([\d.]+)\s*([A-Za-z]*)", text)
    if not match:
        return 0
    number, unit = match.groups()
    multiplier = _SIZE_UNITS.get(unit.upper())
    if multiplier is None:
        return 0
    try:
        return int(float(number) * multiplier)
    except ValueError:
        return 0


def _sanitize_filename(name):
    """Strip characters that are illegal on common filesystems."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "easynews"


def _parse_item(item):
    """Convert one RSS <item> element into a result dict, or None if malformed."""
    title = item.findtext("title") or ""
    description = item.findtext("description") or ""
    enclosure = item.find("enclosure")
    if enclosure is None:
        return None
    direct_url = enclosure.get("url") or ""

    # Enclosure path: /dl/<farm>/<port>/<hash+suffix><ext>/<quoted filename><ext>
    path_parts = urlsplit(direct_url).path.rstrip("/").split("/")
    if len(path_parts) < 2:
        return None
    filename = unquote(path_parts[-1])
    hash_with_suffix, extension = os.path.splitext(path_parts[-2])
    stem = filename[: -len(extension)] if extension and filename.endswith(extension) else filename

    # The plain content hash (needed for the NZB token) appears in the
    # description's archview link; the enclosure hash carries a 4-char suffix.
    hash_match = re.search(r"archview\.html\?f=([0-9a-fA-F]{30,})", description)
    plain_hash = hash_match.group(1) if hash_match else hash_with_suffix[:-4]

    timestamp_match = re.search(r"archview\.html\?[^\"]*?&(?:amp;)?t=(\d+)", description)
    if timestamp_match:
        age_days = max(0, int((time.time() - int(timestamp_match.group(1))) // 86400))
    else:
        age_days = None

    group_match = re.search(r"idx\.html\?group=([^\"&]+)", description)

    # The dl-nzb endpoint silently returns an EMPTY nzb document unless the
    # item's sig accompanies the token, so the sig must travel inside the id.
    sig = parse_qs(urlsplit(direct_url).query).get("sig", [""])[0]

    return {
        "id": f"{plain_hash}|{_b64(stem)}:{_b64(extension)}&sig={sig}",
        "filename": filename,
        "subject": title,
        "size_bytes": _parse_size(enclosure.get("length")),
        "age_days": age_days,
        "newsgroup": group_match.group(1) if group_match else "",
        "extension": extension,
        "yenc": "yenc" in title.lower(),
        "par2": "par2" in filename.lower(),
        "nzb_url": None,  # Easynews NZBs are POST-only; see get_nzb_url()
        "direct_url": direct_url,
    }


def search(query, file_type=None, max_results=25, username=None, password=None):
    """Search Easynews and return a list of result dicts.

    ``file_type`` may be one of: video, audio, image, text, archive
    (case-insensitive). Returns ``[]`` when nothing matches.
    Raises :class:`EasynewsAuthError` on HTTP 401.
    """
    auth = _credentials(username, password)
    params = {"gps": query, "pby": str(max_results), "sS": "5"}
    if file_type:
        normalized = FILE_TYPES.get(file_type.strip().lower())
        if normalized is None:
            raise ValueError(
                f"Unknown file_type {file_type!r}; expected one of {sorted(FILE_TYPES)}"
            )
        params["fty[]"] = normalized

    response = requests.get(SEARCH_URL, params=params, auth=auth, timeout=REQUEST_TIMEOUT)
    if response.status_code == 401:
        raise EasynewsAuthError("Easynews rejected the credentials (HTTP 401).")
    response.raise_for_status()

    root = ET.fromstring(response.content)
    results = []
    for item in root.findall(".//item"):
        parsed = _parse_item(item)
        if parsed is not None:
            results.append(parsed)
    return results


def get_nzb_url(result_id, username=None, password=None, base_url=None):
    """Return a GET-able NZB download URL for ``result_id``.

    Easynews itself only serves NZBs via POST, so there is no native download
    URL. The MCP server therefore exposes a GET proxy route (``/nzb/{id}``)
    and this function builds that URL. ``base_url`` defaults to the
    ``MCP_PUBLIC_URL`` environment variable, falling back to localhost.
    """
    base = (base_url or os.environ.get("MCP_PUBLIC_URL") or "http://localhost:8765").rstrip("/")
    return f"{base}/nzb/{quote(result_id, safe='')}"


def fetch_nzb(result_id, username=None, password=None):
    """Fetch the NZB for ``result_id`` and return ``(content_bytes, filename)``.

    Raises :class:`EasynewsAuthError` on HTTP 401 and ``ValueError`` if
    Easynews does not return an NZB document for the given ID.
    """
    auth = _credentials(username, password)
    token, _, sig = result_id.partition("&sig=")
    form_key = f"0&sig={sig}" if sig else "0"
    response = requests.post(
        NZB_POST_URL,
        data={"autoNZB": "1", form_key: token},
        auth=auth,
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 401:
        raise EasynewsAuthError("Easynews rejected the credentials (HTTP 401).")
    response.raise_for_status()
    if b"<nzb" not in response.content[:1024]:
        raise ValueError(
            f"Easynews did not return an NZB for result ID {result_id!r}: "
            f"{response.text[:200]}"
        )
    if b"<file" not in response.content:
        # Without a valid sig Easynews returns a hollow <nzb/> skeleton.
        raise ValueError(
            f"Easynews returned an empty NZB (no file entries) for result ID "
            f"{result_id!r}; the ID may be stale — re-run the search."
        )

    try:
        stem = _b64_decode(token.split("|", 1)[1].rsplit(":", 1)[0])
    except (IndexError, ValueError):
        stem = "easynews"
    return response.content, f"{_sanitize_filename(stem)}.nzb"


def download_nzb(result_id, destination_path, username=None, password=None, filename=None):
    """Download the NZB for ``result_id`` into directory ``destination_path``.

    ``filename`` optionally overrides the name derived from the result ID
    (a ``.nzb`` suffix is added if missing). Returns the absolute path of
    the saved file.
    """
    content, derived_name = fetch_nzb(result_id, username, password)
    if filename:
        name = _sanitize_filename(filename)
        if not name.lower().endswith(".nzb"):
            name += ".nzb"
    else:
        name = derived_name

    os.makedirs(destination_path, exist_ok=True)
    full_path = os.path.abspath(os.path.join(destination_path, name))
    with open(full_path, "wb") as handle:
        handle.write(content)
    return full_path
