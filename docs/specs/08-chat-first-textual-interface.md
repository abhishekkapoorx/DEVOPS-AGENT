# Chat-first Textual interface

## Problem Statement

The current Textual client exposes authentication actions and a conversation
list as permanent sidebar controls. It renders transcript content as plain
text, while the API does not publish intermediate model or Tool Call activity.
This makes the terminal experience feel like an administration screen rather
than a focused agent chat.

## Solution

Make the CLI a keyboard-first, chat-only interface. Restore an existing session
on launch; if no session is available, start browser-assisted sign-in
automatically and keep the TUI open with a waiting status. The browser
verification page offers sign-in and account creation, so authentication
buttons are not needed in the chat UI. After authentication, show only the
conversation transcript, composer, and concise status. Manage conversations
through an extensible slash-command registry.

The client renders assistant Markdown incrementally and displays sanitized
Tool Call started/completed events as they arrive over the existing SSE run
stream. Tool execution remains on the backend through the registered Tool
Service; the TUI is only a presentation and command surface.

## User Stories

1. As a signed-out user, I want the CLI to open browser sign-in and wait in the
   TUI, so that I can complete onboarding without navigating an auth screen.
2. As a signed-in user, I want a minimal chat screen without persistent sign-in
   or conversation-list controls.
3. As a user, I want `/new`, `/resume`, and `/rename` so that conversation
   management is available without adding permanent UI chrome.
4. As a user, I want `/help`, `/cancel`, and `/logout`, with future commands
   registered through one command interface.
5. As a user, I want assistant Markdown and Tool Call activity to appear while
   the run is in progress, so that long tasks remain understandable.
6. As a keyboard user, I want the composer focused by default and all chat
   actions available without a mouse.

## Functional Requirements

- Restore credentials on startup. If absent or expired, initiate device
  sign-in and keep a clear waiting/error status in the TUI. The browser page
  must let the user switch between sign-in and sign-up for that authorization.
- Do not render sign-in, sign-up, sign-out, or a conversation sidebar in the
  authenticated chat view. `/logout` clears credentials and immediately starts
  browser sign-in again.
- Automatically resume the last locally selected conversation when it belongs
  to the signed-in user; otherwise create a new conversation.
- Implement `/help`, `/new [title]`, `/resume [number|conversation-id]`,
  `/rename <title>`, `/cancel`, and `/logout`. `/resume` without an argument
  prints a numbered list. Commands are case-insensitive and unknown commands
  produce help-oriented feedback. A command registry is the extension point
  for future commands.
- Persist renamed conversation titles through the REST API and repository
  implementations, with ownership checks and title length validation.
- Stream assistant text deltas, Tool Call start events, and Tool Call result
  events through persisted run events and SSE. Render Markdown safely as
  Markdown (not terminal markup injection); do not expose credentials or
  unredacted tool arguments/results.
- Keep one transcript for the selected conversation, append the user's message
  once, update the in-progress assistant response as deltas arrive, and retain
  completed messages on reconnect by loading persisted conversation history.
- Preserve Enter-to-send, terminal scrolling, keyboard focus, and cancellation.

## Testing Decisions

- Use Textual pilot tests with fake authentication and ConversationClient
  implementations; no live browser or Docker service is required.
- Verify automatic auth wait, post-auth chat-only layout, command dispatch,
  conversation resume/rename, Markdown rendering, and tool event rendering.
- Verify worker event order/payload redaction and SSE replay using repository
  contract tests.
- Keep the API contract tests for conversation ownership and title validation.

## Out of Scope

- A graphical/web frontend or editor pane.
- Arbitrary shell execution from the TUI.
- Approval UI for destructive tools; current registered tools remain governed
  by server-side policy and the existing approval lifecycle.
- Model selection, tool configuration, file browsing, and diff editing in this
  first chat-first release. These can be added as slash commands or dedicated
  views without restoring permanent sidebar controls.

## Further Notes

The Textual client must not own conversation persistence or tool execution.
The REST API remains the conversation boundary; SSE carries durable run
progress; the Tool Service remains the only registered-tool executor.
