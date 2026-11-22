# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
WORKDIR /app

COPY requirements-server.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -r requirements-server.txt

COPY pyproject.toml README.md ./
COPY agent_core agent_core
COPY agent_protocol agent_protocol
COPY agent_server agent_server
COPY alembic.ini ./
COPY migrations migrations

CMD ["python", "-m", "agent_server.investigations.worker_main"]
