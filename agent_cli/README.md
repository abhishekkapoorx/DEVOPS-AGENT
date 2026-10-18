# Local execution client

The distributable package is `agent_cli`; install it with
`python -m pip install ".[cli]"` and invoke it as `devops-agent`.

The local client executes policy-approved requests without importing LangGraph
or the server-side agent. Commands are always passed as structured argv lists;
there is no shell execution path. Cloud credentials remain in the local
process and are never included in transport messages.

Sign in or create an account through the Textual browser-assisted flow. The
CLI stores only its rotating refresh credential in the system keyring (with a
protected local fallback where no keyring is available). Launch the full
conversation interface with `--tui` (or run the CLI without a local tool
command):

```bash
devops-agent --api-url https://agent.example.com --tui
```

The Textual interface lists and reopens server-side conversations, streams
agent progress, and can cancel an active run. It remembers the selected
conversation ID locally; conversation messages remain on the backend.
`--auth` opens the standalone sign-in/sign-up screen.

Ask the agent through the REST API. If the browser session is missing, the CLI
starts sign-in automatically; use `--session-id` to continue a conversation:

```bash
devops-agent --api-url https://agent.example.com \
  --ask "Check git status"
```

One-shot execution:

```bash
devops-agent --tool aws sts get-caller-identity
devops-agent --tool kubectl get pods
```

Interactive execution:

```bash
devops-agent --interactive
```

Programmatic callers use `LocalExecutionClient.execute()` with an
`ExecutionRequest` or a mapping containing `tool`, `args`, and optional `cwd`.
Destructive operations return a denied result unless an explicit approval
callback is supplied. Every execution can be sent to an audit sink, and
secrets are redacted from results and audit records.
