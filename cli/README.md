# Local execution client

The local client executes approved requests without importing LangGraph or the
server-side agent. It preserves the user's environment so AWS, gcloud, and
Kubernetes CLIs use local authentication.

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
