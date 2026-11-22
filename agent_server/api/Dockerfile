# syntax=docker/dockerfile:1.7
FROM node:24-alpine AS ui-assets
WORKDIR /ui
COPY package.json package-lock.json ./
RUN npm ci
COPY agent_server/static/src ./agent_server/static/src
COPY agent_server/templates ./agent_server/templates
RUN npm run css:build

FROM python:3.12-slim
WORKDIR /app

COPY requirements-server.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -r requirements-server.txt

COPY pyproject.toml README.md ./
COPY agent_core agent_core
COPY agent_protocol agent_protocol
COPY agent_server agent_server
COPY --from=ui-assets /ui/agent_server/static/app.css agent_server/static/app.css
COPY alembic.ini ./
COPY migrations migrations

EXPOSE 8000
CMD ["uvicorn", "agent_server.api_main:app", "--host", "0.0.0.0", "--port", "8000"]
