# Local execution client

The distributable package is `agent_cli`; install it with
`python -m pip install ".[cli]"` and invoke it as `devops-agent`.

The local client executes policy-approved requests without importing LangGraph
or the server-side agent. Commands are always passed as structured argv lists;
there is no shell execution path. Cloud credentials remain in the local
process and are never included in transport messages.

For an authenticated remote agent, use the WebSocket transport (use `wss://`
in production):

```bash
devops-agent --remote-url wss://agent.example.com/ws \
  --token "$DEVOPS_AGENT_ACCESS_TOKEN" --ask "Check git status"
```

One-shot execution:

```bash
devops-agent --tool aws sts get-caller-identity
devops-agent --tool kubectl get pods
```

Interactive execution:

```bash
devops-agent --interactive
```

Programmatic callers use `LocalExecutionClient.execute()` with an
`ExecutionRequest` or a mapping containing `tool`, `args`, and optional `cwd`.
Destructive operations return a denied result unless an explicit approval
callback is supplied. Every execution can be sent to an audit sink, and
secrets are redacted from results and audit records.
