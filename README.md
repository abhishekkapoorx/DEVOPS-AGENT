# DEVOPS-AGENT

The product has two runtime parts:

- **User machine:** a Python package with the CLI and local Tool Service helper. The helper runs commands and reads or edits files in the directory where `devops-agent` was started.
- **Server:** one private backend with authentication, conversations, LangGraph, model prompts, and Postgres persistence.

The user package contains `agent_cli` and the small shared security module only. It does not package server agents, prompts, or orchestration code.

## Requirements

- Python 3.12 or newer
- Docker with the Docker Compose plugin
- An API key for the model provider selected in `.env`

Install the command line tools you want the agent to use (for example, AWS CLI,
Azure CLI, Google Cloud CLI, `kubectl`, Docker CLI, or Git) on the same machine
where you run the user CLI.

## Start the backend

From the repository root, create the local environment file:

```powershell
Copy-Item .env.example .env
```

Generate a secret and copy its output into `DEVOPS_AGENT_ACCESS_TOKEN_SECRET`
in `.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

In `.env`, select the model provider and set its API key. The example is
configured for OpenAI; keys for OpenAI, Groq, and Google have corresponding
variables in the file. Keep `DEVOPS_AGENT_ENABLE_MCP_AGENTS=false`.

Build and start Postgres, run database migrations, and start the API:

```powershell
docker compose --env-file .env up --build -d
docker compose --env-file .env ps
docker compose --env-file .env logs -f api
```

The API is available at `http://127.0.0.1:8000`. Compose does not mount your
workspace into the backend. Stop the stack with `docker compose --env-file .env down`.

## Install and run the user CLI

In a second terminal, from the repository root, create and activate a virtual
environment, then install the CLI and its local Tool Service helper:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[cli]"
```

For a non-editable install from the checkout, use
`python -m pip install ".[cli]"` instead of the editable install command.

Sign in, then open the chat interface:

```powershell
devops-agent --auth --api-url http://127.0.0.1:8000
devops-agent --api-url http://127.0.0.1:8000
```

Run the CLI from the directory you want the agent to access. It starts the
local helper automatically; the helper executes tools on your machine. Shell
commands require approval, file reads stay inside the launch directory, and
file writes or deletes require approval. The helper stores credentials through
the operating system credential store.

To ask one question without opening the chat interface:

```powershell
devops-agent --api-url http://127.0.0.1:8000 --ask "Check git status"
```

The CLI can also connect to a deployed backend by replacing the API URL with
that backend's HTTPS address. See [the architecture overview](docs/specs/09-client-local-tool-service.md)
and [local run guide](docs/local-run.md) for more detail.

## Current boundaries

- Supported local tool families: `aws`, `az`, `gcloud`, `kubectl`, `docker`, `git`, and `files`.
- AWS and GCP specialist agents remain as source but are not registered. Setting `DEVOPS_AGENT_ENABLE_MCP_AGENTS=true` makes the server fail at startup because MCP support is future work.
- The indexing and RAG code remains in the repository but is not imported or started by the active application.
- The old WebSocket transport and server-hosted Tool Service have been removed.

See [the current architecture spec](docs/specs/09-client-local-tool-service.md) and [local run guide](docs/local-run.md).
