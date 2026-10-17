# Authentication and CLI sessions

## Problem Statement

The CLI currently requires a pre-issued token and does not own user identity, refresh sessions, logout, or persisted conversations.

## Solution

Implement browser-assisted device authorization. The CLI displays sign-in and sign-up screens, opens the verification URL, polls for completion, securely stores the resulting refresh session, and refreshes access tokens automatically.

## User Stories

1. As a new user, I want to start sign-up from the CLI, so that I do not need to copy tokens manually.
2. As an existing user, I want the CLI to open the website for sign-in, so that credentials are handled by the browser authentication surface.
3. As a returning user, I want the CLI to restore my session, so that I do not sign in every time.
4. As a user, I want logout to revoke the local session and server refresh session, so that a lost machine can be invalidated.
5. As a user, I want the CLI to display the authenticated user identity, so that I know which account owns my conversations.
6. As a security operator, I want refresh-token rotation and reuse detection, so that stolen sessions have limited value.
7. As a user, I want expired or revoked sessions to return to the sign-in screen without losing local UI state.

## Implementation Decisions

- Use short-lived access tokens and rotated refresh sessions.
- Use a device authorization record with expiration, polling interval, approval state, and one-time completion semantics.
- Persist secrets in the operating system credential store where available; use an explicit protected fallback for unsupported systems.
- Never accept access tokens through ordinary command-line arguments.
- Bind the authenticated user ID from verified token claims, not from untrusted request fields.
- Support sign-in, sign-up, refresh, logout, current-user, device-start, and device-poll operations.
- Keep browser authentication separate from the Textual presentation layer.

## Testing Decisions

- Test expired, denied, approved, reused, and rate-limited device authorizations.
- Test refresh rotation, reuse detection, logout, and access-token expiry.
- Test that user identity cannot be changed through request payloads.
- Test the CLI with an in-memory credential store and fake browser opener.
- Test terminal behavior when the browser cannot be opened.

## Out of Scope

- Social login provider selection.
- Password collection inside the CLI.
- Building the full account-management website.

## Further Notes

The browser flow is the authentication mechanism; Textual provides the CLI experience around that mechanism.
