# Local execution client

The local client executes approved requests without importing LangGraph or the
server-side agent. It preserves the user's environment so AWS, gcloud, and
Kubernetes CLIs use local authentication.

Ask the server-side agent a question:

```bash
python -m cli --ask "Show the running Docker containers"
python -m cli --user-id alice --session-id incident-42 --ask "Check git status"
```

The final answer is printed as JSON. Local executions stream their tool,
action, and exit code to stderr while the agent is working. The end-to-end
loop accepts a `policy` hook for approval enforcement; production deployments
should provide the restrictive policy from the security layer before accepting
untrusted users.

One-shot execution:

```bash
python -m cli --tool aws sts get-caller-identity
python -m cli --tool kubectl get pods
python -m cli --tool shell "git status --short"
```

Interactive execution:

```bash
python -m cli --interactive
```

Programmatic callers use `LocalExecutionClient.execute()` with an
`ExecutionRequest` or a mapping containing `tool`, `args`, and optional `cwd`.
Every execution returns an `ExecutionResult` with exit code, stdout, stderr,
duration, and JSON serialization.
