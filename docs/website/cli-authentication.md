# CLI authentication

The CLI uses a short-lived device approval flow. The CLI displays a code and opens the browser. Approve the request only when the code and account are familiar.

The browser session and CLI session are separate surfaces. A website login does not expose CLI credentials, and secrets are never printed after they are stored.

## Safety

- Keep access tokens out of shell history.
- Use the account page to review your profile.
- Revoke a webhook token when a cluster is decommissioned.
