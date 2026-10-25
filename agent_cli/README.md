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
agent and tool progress, and can cancel an active run. The footer shows
keyboard shortcuts to create or change chats and log out. Copy-chat and export
remain available through Ctrl+Alt+C and Ctrl+Alt+E, but are hidden from the
footer. Chat text can be selected with the mouse and the selection copied with
Ctrl+C. Export writes the persisted conversation transcript as readable plain
text. The app remembers the selected conversation ID locally;
conversation messages remain on the backend. A new chat remains a local draft
until the first non-empty prompt is sent. The server generates a title from the
first prompt for new chats with the default title; generated titles are limited
to 10 words. A title supplied with `/new <title>` is kept as entered.
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

The helper uses one `LocalToolExecutor.execute(name, arguments)` entry point.
Each tool has its own implementation and receives named arguments, such as
`files.list_files` with `{"path": "/workspace"}` or `git.command` with
`{"argv": ["status"]}`. Shell commands require approval each time. The helper
also keeps file access inside the launch directory, records audits, and
redacts secrets from results.
