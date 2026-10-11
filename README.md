# DEVOPS-AGENT

## Package layout

The repository has three independently packageable modules:

```text
agent_protocol/  # shared validated wire messages
agent_cli/       # local executor and WebSocket client shipped to users
agent_server/    # cloud-side agent and FastAPI transport
```

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
module.
