# Workspace files

The `files` adapter provides bounded read-only directory listing and text
search. Paths are resolved beneath the directory where the DevOps Agent CLI
was started; requests outside that workspace are rejected.

## Usage

```bash
devops-agent --tool files list /absolute/path/to/workspace
devops-agent --tool files grep "TODO|FIXME"
devops-agent --tool files ripgrep "TODO|FIXME"
```

`list` requires an absolute directory path inside the workspace. Use `grep` on
Linux and `ripgrep` on Windows. The Windows build uses the CLI's bundled
ripgrep executable. File listing is available on all supported platforms;
search tools are platform-specific.

## Benefits and safety

- Read-only operations do not require command approval.
- Directory access is checked after path resolution, preventing traversal
  outside the launch workspace.
- Search patterns are passed as an argument, not evaluated by a shell.

## Output

The JSON execution envelope contains exit code, stdout, stderr, and duration.
Listings return sorted entry names; searches return matching lines and
locations. Results are bounded, and no match is a successful empty result.
