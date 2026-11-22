# Google Cloud CLI

The `gcloud` adapter runs the locally installed Google Cloud CLI using its
active local configuration and authentication.

## Usage

```bash
devops-agent --tool gcloud -- auth list
devops-agent --tool gcloud -- projects list --format=json
```

Configure authentication and the active project using the normal `gcloud`
commands before starting a request. Put `--` before Google Cloud CLI flags so
the DevOps Agent parser forwards them unchanged.

## Benefits and safety

- Reuses local gcloud credentials and configuration; credential files are not
  uploaded to the agent service.
- Requires explicit approval before execution.
- Passes arguments directly to `gcloud` without shell interpretation.

Avoid passing service-account private keys or other secrets as command-line
arguments. Use the standard local authentication flow.

## Output

The result is a JSON envelope containing redacted arguments, exit code,
stdout, stderr, and duration. `gcloud` determines the content and format of
stdout; choose a `--format` value when required.
