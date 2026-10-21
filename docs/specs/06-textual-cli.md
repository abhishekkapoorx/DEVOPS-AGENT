# Textual CLI

## Problem Statement

The current CLI is an argument-driven command runner with a WebSocket client. It has no authenticated session lifecycle, conversation navigation, progress rendering, or approval workflow.

## Solution

Build a Textual application with screens for authentication, browser handoff, conversation selection, chat, run progress, approval, settings, and errors. A dedicated client layer handles REST, SSE, retries, token refresh, and reconnect behavior.

## User Stories

1. As a user, I want a sign-in screen, so that authentication is discoverable.
2. As a user, I want a sign-up action, so that I can create an account from the CLI.
3. As a user, I want a conversation list, so that I can reopen previous chats.
4. As a user, I want messages and agent progress rendered incrementally, so that long operations are understandable.
5. As a user, I want to approve or deny risky tool calls, so that I remain in control.
6. As a user, I want reconnect and event replay, so that temporary network failures do not lose the run.
7. As a user, I want keyboard navigation and accessible status messages, so that the CLI remains usable without a mouse.
8. As a developer, I want UI tests to use fake client interfaces, so that Textual tests do not require a live backend.

## Implementation Decisions

- Use Textual screens and workers for UI state and network operations.
- Keep widgets free of HTTP and persistence logic.
- Use an API client with access-token refresh and typed response models.
- Use SSE or event polling for run progress.
- Store only the minimum local state needed to resume authentication and identify the selected conversation.
- Render tool calls with safe names and summaries; do not display secrets or uncontrolled raw output.
- Preserve a non-interactive command mode only for explicitly supported automation use cases.

## Testing Decisions

- Test screens with Textual pilot tests and fake client responses.
- Test authentication transitions, expired sessions, reconnects, approval actions, and error states.
- Test that UI workers cancel when screens are removed.
- Test non-interactive output separately from the Textual application.

## Out of Scope

- A full web frontend.
- Terminal rendering of arbitrary binary artifacts.
- Local credential entry for the browser authentication provider.

## Further Notes

The CLI is a user interface and client, not the owner of backend conversation state or the Tool Service protocol.
