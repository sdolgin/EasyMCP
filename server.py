"""Easynews MCP server — SSE/HTTP transport for Claude Desktop over the LAN.

Exposes three MCP tools (search_usenet, get_nzb_url, download_nzb) plus two
plain HTTP routes: GET /health for the Docker healthcheck and GET /nzb/{id},
which proxies Easynews's POST-only NZB endpoint so NZBs are fetchable from a
plain URL.
"""

import json
import os
import sys

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import easynews_client
from easynews_client import EasynewsAuthError

load_dotenv()

HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8765"))
DOWNLOAD_PATH = os.environ.get("EASYNEWS_DOWNLOAD_PATH", "/downloads/nzb")
PUBLIC_URL = os.environ.get("MCP_PUBLIC_URL", f"http://localhost:{PORT}")
CREDS_OK = bool(os.environ.get("EASYNEWS_USERNAME") and os.environ.get("EASYNEWS_PASSWORD"))

mcp = FastMCP("easynews", host=HOST, port=PORT)


def _human_size(size_bytes):
    size = float(size_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@mcp.tool()
def search_usenet(query: str, file_type: str | None = None, max_results: int = 25) -> str:
    """Search Usenet via Easynews. Returns matching files with metadata
    (filename, size, age, newsgroup) and result IDs needed for NZB generation.

    file_type optionally narrows results to one of: video, audio, image,
    text, archive.
    """
    try:
        results = easynews_client.search(query, file_type=file_type, max_results=max_results)
    except EasynewsAuthError:
        return "Error: Easynews rejected the configured credentials (HTTP 401). Check EASYNEWS_USERNAME/EASYNEWS_PASSWORD on the server."
    except ValueError as exc:
        return f"Error: {exc}"

    if not results:
        return f"No results found for {query!r}."

    lines = [
        "| # | Filename | Size | Age (days) | Newsgroup |",
        "|---|----------|------|------------|-----------|",
    ]
    for i, r in enumerate(results, 1):
        age = r["age_days"] if r["age_days"] is not None else "?"
        lines.append(
            f"| {i} | {r['filename']} | {_human_size(r['size_bytes'])} | {age} | {r['newsgroup']} |"
        )

    payload = [
        {k: r[k] for k in ("id", "filename", "size_bytes", "age_days", "newsgroup",
                           "extension", "yenc", "par2", "direct_url")}
        for r in results
    ]
    return (
        f"{len(results)} results for {query!r}:\n\n"
        + "\n".join(lines)
        + "\n\nFull result data (use `id` for get_nzb_url / download_nzb):\n```json\n"
        + json.dumps(payload, indent=2)
        + "\n```"
    )


@mcp.tool()
def get_nzb_url(result_id: str) -> str:
    """Get the direct NZB download URL for an Easynews search result.
    Use the result ID from a prior search_usenet call."""
    return easynews_client.get_nzb_url(result_id, base_url=PUBLIC_URL)


@mcp.tool()
def download_nzb(result_id: str, filename_hint: str | None = None) -> str:
    """Download an NZB file and save it to the NZBGet watch folder on the NAS.
    NZBGet will pick it up automatically. Use the result ID from a prior
    search_usenet call."""
    try:
        path = easynews_client.download_nzb(result_id, DOWNLOAD_PATH, filename=filename_hint)
    except EasynewsAuthError:
        return "Error: Easynews rejected the configured credentials (HTTP 401). Check EASYNEWS_USERNAME/EASYNEWS_PASSWORD on the server."
    except (ValueError, OSError) as exc:
        return f"Error: could not download NZB: {exc}"
    return f"NZB saved to {path}. NZBGet will pick it up from its watch folder automatically."


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/nzb/{result_id:path}", methods=["GET"])
async def nzb_proxy(request: Request) -> Response:
    """GET proxy for Easynews's POST-only NZB endpoint."""
    result_id = request.path_params["result_id"]
    try:
        content, filename = easynews_client.fetch_nzb(result_id)
    except EasynewsAuthError:
        return JSONResponse({"error": "Easynews rejected the configured credentials"}, status_code=502)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:  # network failures etc.
        return JSONResponse({"error": f"NZB fetch failed: {exc}"}, status_code=502)
    return Response(
        content,
        media_type="application/x-nzb",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    print(f"[easynews-mcp] Transport: SSE  Host: {HOST}  Port: {PORT}", file=sys.stderr)
    print(f"[easynews-mcp] NZB download path: {DOWNLOAD_PATH}", file=sys.stderr)
    print(f"[easynews-mcp] Public URL for NZB links: {PUBLIC_URL}", file=sys.stderr)
    print(f"[easynews-mcp] Credentials loaded: {'yes' if CREDS_OK else 'NO — set EASYNEWS_USERNAME/EASYNEWS_PASSWORD'}", file=sys.stderr)
    mcp.run(transport="sse")
