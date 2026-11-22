# CLI authentication

The CLI uses a device approval flow rather than asking for an account password
in the terminal. The CLI displays a verification URL and code; open the URL,
sign in or create an account, and approve only if the code shown in the browser
matches the one shown in the CLI.

## Sign in

Start the Textual interface or an agent request with the server URL:

```bash
devops-agent --api-url https://agent.example.com --tui
devops-agent --api-url https://agent.example.com --ask "Summarize the deployment issue"
```

The CLI can also read `DEVOPS_AGENT_API_URL`. If no valid session exists, it
starts browser-assisted sign-in. The `--auth` option opens the standalone
authentication screen. A website login and a CLI session are separate; the
website does not expose the CLI refresh credential.

## Credential storage and lifecycle

After approval, the CLI stores its rotating refresh credential in the operating
system keyring when available. On systems without a keyring, it uses the CLI's
protected local fallback. Access tokens are short-lived and refreshed through
the authentication client; they are not written to shell arguments. Use
`/logout` in chat to clear the local session and begin browser sign-in again.

## Safety checklist

- Verify the server URL before authenticating.
- Compare the verification code in the terminal and browser before approval.
- Do not paste access tokens, refresh tokens, or passwords into command
  arguments, chat messages, or shell history.
- Use the account settings page to review the signed-in identity.
- Revoke webhook tokens from Integrations when they are no longer needed; this
  is separate from logging out of the CLI.

## Troubleshooting

- **No browser opens:** open the printed verification URL manually.
- **Code expired:** restart the CLI sign-in flow to request a new code.
- **Wrong API URL:** set `--api-url` or `DEVOPS_AGENT_API_URL` to the intended
  server and restart.
- **Keyring unavailable:** the CLI falls back to protected local storage; use
  the operating system's account protections and file permissions.
