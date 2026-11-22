# Slash commands

Slash commands manage the current CLI chat. Enter a command at the beginning
of the composer and press Enter to run it. Command names are case-insensitive.

When `/` is typed in the composer, a filtered suggestion list shows available
commands and their usage. Use Up/Down to move through the list, Enter to insert
the highlighted command into the draft, and Escape to dismiss the list without
changing the draft. Completion only inserts text; it does not run the command.

| Command | Usage | Behavior |
| --- | --- | --- |
| `/help` | `/help` | Show the registered slash commands. |
| `/new` | `/new [title]` | Start a new chat draft. An optional title is used when the first message creates the conversation. |
| `/resume` | `/resume [number\|conversation-id]` | Without an argument, list saved chats. Otherwise select a chat by its displayed number or conversation ID. |
| `/rename` | `/rename <title>` | Rename the selected chat. |
| `/cancel` | `/cancel` | Cancel the active agent run, if one exists. |
| `/logout` | `/logout` | Clear the local sign-in session and start browser sign-in again. |

Commands are dispatched only when the submitted message begins with `/`.
Inline completion is useful while drafting text, but a command intended for the
CLI must remain at the beginning of the input. If the name is unknown, the CLI
reports an error and points to `/help`.

The command registry is the extension point for future commands. The command
names, usage text, and handlers are defined in `TextualAgentApp` in
`agent_cli/textual_app.py`.
