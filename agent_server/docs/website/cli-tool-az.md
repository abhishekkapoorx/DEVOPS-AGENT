# Azure CLI

The `az` adapter runs the locally installed Azure CLI with the current user's
Azure CLI login, subscription selection, and environment.

## Usage

```bash
devops-agent --tool az -- account show
devops-agent --tool az -- group list --output table
```

Run `az login` and select a subscription with the standard Azure CLI commands
before using this adapter. Flags after the `--` separator are passed to `az`.

## Benefits and safety

- Uses local Azure CLI authentication instead of sending credential material
  to the agent service.
- Requires explicit approval before running the command.
- Passes argv directly and does not invoke a shell.

Do not put passwords, tokens, or client secrets in command arguments. Prefer
Azure CLI's established local authentication and credential mechanisms.

## Output

The CLI returns a JSON execution envelope with redacted arguments, exit code,
stdout, stderr, and duration. Azure CLI controls the format of stdout; use its
`--output` option when a particular format is needed.
