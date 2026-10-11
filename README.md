# DEVOPS-AGENT

## Package layout

The repository has three independently packageable modules:

```text
agent_protocol/  # shared validated wire messages
agent_cli/       # local executor and WebSocket client shipped to users
agent_server/    # cloud-side agent and FastAPI transport
```

Server-only implementation details live below `agent_server/`:

```text
agent_server/
├── agents/       # provider and workflow agents
├── tools/        # deployment, terminal, and handoff tools
├── llms/         # server-side model configuration
├── utils/        # context, planning, and shared server helpers
└── indexing/     # optional Pinecone/Neo4j code indexing
```

Examples are grouped by deployment target under `examples/server/`. The
root-level `dummy_projects/` directory is sample data for those examples;
`vectordbs/` is reserved for local indexing data and is not part of either
installed package.

Install only the local CLI:

```bash
python -m pip install ".[cli]"
devops-agent --help
```

Install the cloud-side transport:

```bash
python -m pip install ".[server]"
uvicorn agent_server.transport:app
```

The old `cli`, `server_agent`, and `transport` import paths remain thin
compatibility wrappers. New code should import from the package that owns the
module. The compatibility paths can be removed in a future breaking release.
