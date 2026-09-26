FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies if needed (e.g. for building some python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN python -m pip install --upgrade pip && python -m pip install --no-cache-dir -r requirements.txt

# Expose MCP stdio (default) and FastAPI port
EXPOSE 8000

# Copy application code
COPY . .

# Run as an unprivileged user that owns only the data directory
RUN useradd --create-home --uid 10001 readytrader \
    && mkdir -p data && chown -R readytrader:readytrader /app/data
USER readytrader

# Entry point: the MCP server on stdio.
# Optional API sidecar (approvals + dashboard), from the same image:
#   docker run --rm -p 127.0.0.1:8000:8000 -e API_HOST=0.0.0.0 -v readytrader-forex-data:/app/data readytrader-forex python app/api_server.py
# Give it and the MCP server the same EXECUTION_SESSION_ID and data volume for approvals.
CMD ["python", "app/main.py"]
