# kubectl

The `kubectl` adapter runs the locally installed Kubernetes CLI. It uses the
current kubeconfig, context, namespace, and environment, just as `kubectl`
does in the same terminal.

## Usage

```bash
devops-agent --tool kubectl -- config current-context
devops-agent --tool kubectl -- get pods --namespace production
devops-agent --tool kubectl -- describe deployment checkout --namespace production
```

Use `kubectl config use-context` before execution if a different cluster is
intended. Put `--` before kubectl arguments, especially when the command
contains flags such as `--namespace`.

## Benefits and safety

- Keeps cluster access in the user's local kubeconfig and does not upload that
  file to the agent service.
- Requires explicit approval before running commands, including commands that
  appear read-only.
- Does not invoke a shell. A command is restricted by the local OS account and
  the permissions of the selected Kubernetes context.

Confirm the active context and review write operations carefully. Avoid
including credentials or Secret data in command arguments or copied output.

## Output

The JSON execution result includes redacted arguments, exit code, stdout,
stderr, and duration. The body of stdout is kubectl's output; for automation,
consider its `-o json` or `-o yaml` modes and validate the result.
