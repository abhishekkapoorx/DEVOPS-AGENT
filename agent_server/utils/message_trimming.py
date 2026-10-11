"""
Message trimming and summarization utilities for managing conversation history.

This module provides hooks to trim conversation history to a fixed number of
most recent messages, optionally summarizing older messages to preserve context
while reducing token usage.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    get_buffer_string,
)
from langchain_core.language_models import LanguageModelLike
from loguru import logger


def create_message_trimming_hook(
    model: Optional[LanguageModelLike] = None,
    max_messages: int = 5,
    summarize_old: bool = False,
    summary_prefix: str = "Previous conversation summary:",
) -> callable:
    """
    Create a pre-model hook that trims messages to keep only the most recent ones.

    Parameters
    ----------
    model
        Language model to use for summarization (if enabled).
        Required only if summarize_old is True.
    max_messages
        Maximum number of recent messages to keep. Defaults to 5.
    summarize_old
        If True, summarize older messages into a single system message.
        If False, older messages are simply discarded. Defaults to False
        to avoid extra API calls.
    summary_prefix
        Prefix text for the summary message.

    Returns
    -------
    Callable[[dict], dict]
        A hook function that can be used as a pre_model_hook in LangGraph.
    """

    def _summarize_messages(messages: List[BaseMessage]) -> str:
        """
        Summarize a list of messages into a concise summary.

        Parameters
        ----------
        messages
            List of messages to summarize.

        Returns
        -------
        str
            A summary of the conversation.
        """
        if not messages:
            return "No previous conversation."

        try:
            # Convert messages to a readable format
            conversation_text = get_buffer_string(messages)

            # Create a prompt for summarization with actionable structure
            summary_prompt = f"""You are assisting a multi-agent DevOps supervisor.
Provide a concise yet actionable briefing of earlier dialogue to guide planning.

Summarize using the following structure:
- **Objective:** Primary user goal or request.
- **Actions:** Key steps that were attempted (agents/tools/commands invoked).
- **Findings:** Important outputs, intermediate results, or observations.
- **Open Items:** Remaining tasks, blockers, or decisions still pending.

Conversation:
{conversation_text}

Briefing:"""

            # Generate summary using the model
            response = model.invoke(summary_prompt)
            summary = (
                response.content
                if hasattr(response, "content")
                else str(response)
            )
            return summary.strip()
        except Exception:
            # Fallback to a simple summary if summarization fails
            return (
                "Conversation summary unavailable. Earlier discussion covered "
                f"{len(messages)} message(s); recall prior objectives, actions, findings, "
                "and blockers if needed."
            )

    def _trim_messages(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trim messages to keep only the most recent ones.

        Parameters
        ----------
        state
            Current agent state containing messages.

        Returns
        -------
        dict
            Updated state with trimmed messages.
        """
        messages = state.get("messages", []) or []
        if not messages:
            return state

        # If we have fewer messages than the limit, no trimming needed
        if len(messages) <= max_messages:
            return state

        # Separate system messages from other messages
        system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
        non_system_messages = [
            msg for msg in messages if not isinstance(msg, SystemMessage)
        ]

        # Keep only the first system message (usually the supervisor prompt)
        # Discard old RAG context and other system messages to save tokens
        initial_system_message = system_messages[0] if system_messages else None

        # Keep the most recent non-system messages
        messages_to_keep = non_system_messages[-max_messages:]
        messages_to_remove = non_system_messages[:-max_messages]

        # Log trimming activity
        if messages_to_remove:
            logger.info(
                f"Trimming conversation: keeping {len(messages_to_keep)} most recent messages, "
                f"removing {len(messages_to_remove)} older messages"
            )

        # Build the new message list
        new_messages: List[BaseMessage] = []
        conversation_summary: Optional[str] = None

        # Add the initial system message if it exists (supervisor prompt)
        if initial_system_message:
            new_messages.append(initial_system_message)

        # Add summary of old messages if requested
        if summarize_old and messages_to_remove:
            if model is None:
                # Fallback if model not provided
                summary_text = (
                    "Earlier discussion reference: "
                    f"{len(messages_to_remove)} trimmed message(s) summarised."
                )
            else:
                summary_text = _summarize_messages(messages_to_remove)
            conversation_summary = summary_text
            summary_message = SystemMessage(
                content=f"{summary_prefix}\n{summary_text}"
            )
            new_messages.append(summary_message)

        # Add the recent messages we're keeping
        new_messages.extend(messages_to_keep)

        new_state = {
            **state,
            "messages": new_messages,
        }
        if summarize_old and conversation_summary:
            new_state["conversation_summary"] = conversation_summary

        return new_state

    return _trim_messages

