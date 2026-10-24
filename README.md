# DEVOPS-AGENT

The product has two runtime parts:

- **User machine:** a Python package with the CLI and local Tool Service helper. The helper runs commands and reads or edits files in the directory where `devops-agent` was started.
- **Server:** one private backend with authentication, conversations, LangGraph, model prompts, and Postgres persistence.

The user package contains `agent_cli` and the small shared security module only. It does not package server agents, prompts, or orchestration code.

## Install the user package

```powershell
python -m pip install ".[cli]"
devops-agent --api-url https://your-agent.example
```

The CLI starts the local helper as a child process. Both use the same OS-stored login. Only one helper can be connected per account at a time so requests cannot be sent to the wrong workspace. Every shell command requires approval. File reads are limited to the launch directory; file writes and deletes require approval.

## Run the server locally

```powershell
docker compose up --build
```

Compose runs Postgres, migrations, and one API backend. The user’s workspace is never mounted into the server. Configure `.env` with the database URL, token secret, public URL, auth mode, model provider, and provider credentials.

## Current boundaries

- Supported local tool families: `aws`, `az`, `gcloud`, `kubectl`, `docker`, `git`, and `files`.
- AWS and GCP specialist agents remain as source but are not registered. Setting `DEVOPS_AGENT_ENABLE_MCP_AGENTS=true` makes the server fail at startup because MCP support is future work.
- The indexing and RAG code remains in the repository but is not imported or started by the active application.
- The old WebSocket transport and server-hosted Tool Service have been removed.

See [the current architecture spec](docs/specs/09-client-local-tool-service.md) and [local run guide](docs/local-run.md).
