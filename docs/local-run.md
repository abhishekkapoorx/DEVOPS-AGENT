# Local end-to-end run

1. Copy `.env.example` to `.env` and set a random token secret of at least 32 characters.
2. Start Postgres, migrations, and the single backend with `docker compose --env-file .env up --build`.
3. Install the user package with `python -m pip install -e ".[cli]"`.
4. Sign in with `devops-agent --auth --api-url http://127.0.0.1:8000`, then start the chat with `devops-agent --api-url http://127.0.0.1:8000`.

The CLI starts the local helper in the current directory. The helper receives tool requests over SSE, asks for approval before shell commands and file changes, executes locally, and returns results to the backend. No workspace mount is configured in Compose.

Select a model provider in `.env` and provide its key. `DEVOPS_AGENT_ENABLE_MCP_AGENTS` must remain false; enabling it exits with an unsupported-feature message.
