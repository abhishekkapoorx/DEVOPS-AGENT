FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY agent_core agent_core
COPY agent_protocol agent_protocol
COPY agent_server agent_server
RUN pip install --no-cache-dir "alembic>=1.16,<2" "argon2-cffi>=23.1,<26" "asyncpg>=0.30,<1" "fastapi>=0.119,<1" "langchain>=1,<2" "langchain-core>=1,<2" "langchain-google-genai>=3,<4" "langchain-groq>=1,<2" "langchain-ollama>=1,<2" "langchain-openai>=1,<2" "langgraph-checkpoint-postgres>=3,<4" "psycopg[binary]>=3.2,<4" "pydantic>=2.11,<3" "python-multipart>=0.0.20,<1" "sqlalchemy[asyncio]>=2.0,<3" "uvicorn>=0.35,<1"
COPY alembic.ini ./
COPY migrations migrations
EXPOSE 8000
