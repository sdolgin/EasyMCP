FROM python:3.11-slim

WORKDIR /app

# Install deps first (layer cache-friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY easynews_client.py server.py ./

# Non-root user; default download dir (overridden by volume mount at runtime)
RUN useradd -m -u 1000 mcpuser \
    && mkdir -p /downloads/nzb \
    && chown -R mcpuser /app /downloads
USER mcpuser

EXPOSE 8765

# python:slim has no curl; probe /health with stdlib urllib instead
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8765/health', timeout=4)"]

CMD ["python", "server.py"]
