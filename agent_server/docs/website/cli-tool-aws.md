# AWS CLI

The `aws` adapter starts the locally installed AWS CLI. It uses the same
credential provider chain, profile, region, and environment as an ordinary
`aws` command in the current terminal.

## Usage

```bash
devops-agent --tool aws -- sts get-caller-identity
devops-agent --tool aws -- ec2 describe-instances --region us-east-1
```

The words after `--` are passed to AWS CLI as separate arguments. Select or
configure a profile using the standard AWS CLI settings before running the
DevOps Agent CLI.

## Benefits and safety

- Reuses local AWS authentication without sending the credential files to the
  agent service.
- Requires explicit approval before running the command.
- Does not add shell operators, pipelines, or interpolation; each argument is
  passed directly to the executable.

Avoid placing access keys, session tokens, or other secrets in command-line
arguments. Use the AWS CLI's normal profile or environment-based credential
configuration instead.

## Output

The result is JSON containing redacted arguments, exit code, stdout, stderr,
and duration. The command's standard output remains AWS CLI output and may be
JSON, text, or another format depending on the selected AWS CLI options.
