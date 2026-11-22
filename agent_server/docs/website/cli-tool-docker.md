# Docker CLI

The `docker` adapter runs the locally installed Docker CLI. It targets the
active Docker context and daemon available to the user's OS account.

## Usage

```bash
devops-agent --tool docker -- version
devops-agent --tool docker -- ps --all
devops-agent --tool docker -- compose ps
```

The Docker CLI must be installed and its daemon/context configured locally.
Arguments after `--` are passed directly to `docker`.

## Benefits and safety

- Uses local Docker authentication and context without uploading credential
  files to the agent service.
- Requires explicit approval before running a command.
- Avoids shell parsing and runs with the privileges of the local Docker user.

Access to a Docker daemon can provide broad host-level control. Verify the
context and review potentially destructive commands before approval. Do not
put registry passwords or access tokens in command arguments.

## Output

The result is JSON with redacted arguments, exit code, stdout, stderr, and
duration. Docker decides the stdout format; use `--format` for structured
output where supported.
