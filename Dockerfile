FROM ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8 AS uv
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    CHEM_HOST=0.0.0.0 \
    CHEM_PORT=7860 \
    PATH=/app/.venv/bin:$PATH

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY data ./data
COPY examples ./examples
COPY scripts/demo_offline.py ./scripts/demo_offline.py
COPY app.py cli.py ./
RUN uv sync --locked --no-dev \
    && mkdir -p runs build .local \
    && chown -R 10001:10001 runs build .local

USER 10001:10001
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/health', timeout=3)"
CMD ["python", "app.py"]
