# Git

The `git` adapter runs Git in the CLI launch directory by default. Relative
paths and repository discovery therefore use the current workspace.

## Usage

```bash
devops-agent --tool git -- status --short --branch
devops-agent --tool git -- log -5 --oneline
devops-agent --tool git -- diff --stat
```

Use `--` to pass Git flags to the executable. The local process inherits the
terminal environment and runs with the current OS user's filesystem
permissions.

## Benefits and safety

- Uses existing local Git configuration and repository credentials.
- Requires explicit approval before running any Git command.
- Passes argv directly rather than through a shell.

Review the repository and current branch before approving operations that
modify history, the index, or the worktree. Avoid credentials in remote URLs or
arguments.

## Output

The JSON result contains redacted arguments, exit code, stdout, stderr, and
duration. Git output is returned as text; the CLI does not automatically alter
the repository.
