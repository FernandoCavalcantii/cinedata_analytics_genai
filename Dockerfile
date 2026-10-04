FROM python:3.11-slim

WORKDIR /app

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

COPY pyproject.toml README.md ./
COPY src ./src

# O extra instala o Logfire. Sem LOGFIRE_TOKEN a API sobe e não envia trace.
RUN pip install --no-cache-dir ".[observability]"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]

CMD ["uvicorn", "cinedata.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
