# DevOps Agent CLI

The CLI provides an authenticated chat interface and a local execution helper
for common DevOps command-line tools. Tool processes run on the user's machine;
the agent service does not receive the local shell or cloud credential store.

## Tools Available

| Tool | Purpose | Documentation |
| --- | --- | --- |
| `aws` | Run the AWS CLI with the local AWS profile and environment. | [AWS CLI](/docs/cli/tools/aws) |
| `az` | Run the Azure CLI with the local Azure login. | [Azure CLI](/docs/cli/tools/az) |
| `gcloud` | Run the Google Cloud CLI with local configuration. | [Google Cloud CLI](/docs/cli/tools/gcloud) |
| `kubectl` | Run kubectl against the active local kubeconfig context. | [kubectl](/docs/cli/tools/kubectl) |
| `docker` | Run Docker CLI commands against the local Docker context. | [Docker CLI](/docs/cli/tools/docker) |
| `git` | Run Git commands in the CLI workspace. | [Git](/docs/cli/tools/git) |
| `files` | List workspace files and search workspace text. | [Workspace files](/docs/cli/tools/files) |

These are adapters to installed local executables, not cloud SDK wrappers. The
CLI passes arguments as an argv list and does not invoke a shell. The command
tools require explicit approval; file listing and text search are read-only.

## Usage

Install the CLI extras from a repository checkout:

```bash
python -m pip install ".[cli]"
```

Run a local tool command. Add `--` before provider flags so the argument parser
passes them to the selected executable:

```bash
devops-agent --tool kubectl -- get pods --namespace production
devops-agent --tool aws -- sts get-caller-identity
devops-agent --tool files list /absolute/path/to/workspace
```

The current directory when the CLI starts is the local workspace boundary for
file access and command working directories. `files list` takes an absolute
path inside that workspace. `files grep` is available on Linux; `files ripgrep`
uses the bundled ripgrep executable on Windows.

Open an authenticated chat, or ask one question without opening the full TUI:

```bash
devops-agent --api-url https://agent.example.com --tui
devops-agent --api-url https://agent.example.com --ask "Check deployment health"
```

See [Authentication](/docs/cli/authentication) for sign-in and credential
storage details, and [Slash commands](/docs/cli/slash-commands) for conversation
management inside the chat interface.

## Benefits

- **Local execution:** supported CLIs use the machine's configured credentials
  and contexts; those credential stores are not uploaded to the agent service.
- **Explicit command approval:** command tools ask for local approval before
  execution. A denied request is not run.
- **No shell interpolation:** arguments are passed separately to the selected
  executable rather than assembled into a shell command.
- **Workspace boundary:** file listing and search stay inside the directory
  where the CLI was launched.
- **Bounded, redacted results:** arguments and output are redacted, and output
  size is limited before being displayed or transported.

## Outputs

One-shot tool execution prints a JSON object with the tool name, redacted
arguments, the executable's exit code, standard output, standard error, and
elapsed time. A non-zero `exit_code` indicates that the executable or local
tool operation failed; inspect `stderr` for details. Long outputs are capped,
and secret-like values are redacted.

The Textual chat interface renders assistant Markdown and run status in the
transcript. A local tool request shows its name, status, and a bounded result
preview. Agent responses are not a substitute for checking the underlying
command output before taking operational action.

## Tool reference

- [AWS CLI](/docs/cli/tools/aws)
- [Azure CLI](/docs/cli/tools/az)
- [Google Cloud CLI](/docs/cli/tools/gcloud)
- [kubectl](/docs/cli/tools/kubectl)
- [Docker CLI](/docs/cli/tools/docker)
- [Git](/docs/cli/tools/git)
- [Workspace files](/docs/cli/tools/files)
