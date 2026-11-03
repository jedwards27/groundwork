# The web app: static files, built here and served by the API (no Node at runtime).
FROM node:24-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.6.3 /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY fixtures/ /app/fixtures/
COPY --from=web /web/dist /app/web/dist
RUN uv sync --frozen --no-dev
ENV PATH="/app/backend/.venv/bin:$PATH" \
    GROUNDWORK_FIXTURES_DIR=/app/fixtures \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["groundwork", "serve", "--host", "0.0.0.0", "--port", "8000"]
