# Local execution client

The distributable package is `agent_cli`; install it with
`python -m pip install ".[cli]"` and invoke it as `devops-agent`.

The local client executes approved requests without importing LangGraph or the
server-side agent. It preserves the user's environment so AWS, gcloud, and
Kubernetes CLIs use local authentication.

For an authenticated remote agent, use the WebSocket transport (use `wss://`
in production):

```bash
devops-agent --remote-url wss://agent.example.com/ws \
  --token "$DEVOPS_AGENT_AUTH_TOKEN" --ask "Check git status"
```

One-shot execution:

```bash
devops-agent --tool aws sts get-caller-identity
devops-agent --tool kubectl get pods
devops-agent --tool shell "git status --short"
```

Interactive execution:

```bash
devops-agent --interactive
```

Programmatic callers use `LocalExecutionClient.execute()` with an
`ExecutionRequest` or a mapping containing `tool`, `args`, and optional `cwd`.
Every execution returns an `ExecutionResult` with exit code, stdout, stderr,
duration, and JSON serialization.
