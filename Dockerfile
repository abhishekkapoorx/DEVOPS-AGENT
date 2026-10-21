FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY agent_core agent_core
COPY agent_protocol agent_protocol
COPY agent_server agent_server
RUN pip install --no-cache-dir ".[server]"
COPY alembic.ini ./
COPY migrations migrations
EXPOSE 8000
