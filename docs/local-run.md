# Local end-to-end run

This repository includes a deliberately scoped development identity page. It
is for a disposable local stack only; production must supply a real website
approval provider before it can start.

1. Copy `.env.example` to `.env.compose` and replace the access-token secret
   with a random value of at least 32 characters. The explicit env-file name
   avoids conflicts with shell-style `.env` files used by other local tools.
2. Start the complete stack with `docker compose --env-file .env.compose up --build`. The `migrate`
   service applies Alembic migrations before the API and Tool Service start.
3. In another shell install the CLI (`python -m pip install -e ".[cli]"`) and
   run `devops-agent --auth --api-url http://127.0.0.1:8000`. Open the printed
   page, enter the displayed eight-character code, and approve. The CLI then
   stores its rotated refresh credential locally.
4. Run `devops-agent --ask "git status workspace" --api-url http://127.0.0.1:8000`.
   With the supplied `echo` runtime this requests `git.status` from the
   separate Tool Service, persists the result, resumes the agent turn, and
   prints its final answer. Use `devops-agent --tui` to exercise the same API
   through the Textual client.

Useful readiness checks are `GET /health/live`, `GET /health/ready`, and
`GET /metrics` on the API. To use a real model, set
`DEVOPS_AGENT_RUNTIME=langgraph`, choose a provider and model, and provide its
API key. The database is intentionally retained in the named `postgres-data`
volume; remove that volume only when discarding local test data.

The Tool Service accepts only the configured repository identifiers in
`DEVOPS_AGENT_TOOL_REPOSITORIES`; it never accepts an arbitrary filesystem path
or shell command.
