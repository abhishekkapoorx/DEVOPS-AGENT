"""
Shared helpers for building reusable pre-model hooks across agents.

Each combined hook typically orchestrates a sequence of pre-processing steps
before the underlying language model is called. Centralizing this logic keeps
`agent.py` and the supervisor/agent modules focused on configuration rather
than plumbing.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.language_models import LanguageModelLike
from langchain_core.retrievers import BaseRetriever
from loguru import logger

from .message_trimming import create_message_trimming_hook
from .planning import create_planning_hook
from .rag import create_rag_context_hook


def build_combined_pre_model_hook(
    *,
    model: LanguageModelLike,
    rag_retriever: Optional[BaseRetriever] = None,
    trim_kwargs: Optional[Dict[str, Any]] = None,
    planning_kwargs: Optional[Dict[str, Any]] = None,
    enable_trimming: bool = True,
    enable_planning: bool = True,
    drop_remaining_steps: bool = True,
) -> callable:
    """
    Construct a reusable pre-model hook that applies (optionally) trimming,
    retrieval augmented generation (RAG) context injection, and planning.

    Parameters
    ----------
    model
        The language model instance used for summarisation/planning steps.
    rag_retriever
        Optional retriever used to fetch additional context. When ``None`` the
        RAG step is skipped automatically.
    trim_kwargs
        Keyword arguments passed to ``create_message_trimming_hook``.
    planning_kwargs
        Keyword arguments passed to ``create_planning_hook``.
    enable_trimming
        Toggle for the trimming phase (enabled by default).
    enable_planning
        Toggle for the planning phase (enabled by default).
    drop_remaining_steps
        Whether to remove ``remaining_steps`` from the state returned to the
        supervisor or agent. LangGraph manages this channel internally.

    Returns
    -------
    callable
        A function compatible with ``pre_model_hook`` that can be plugged into
        supervisors or standard agents constructed via LangGraph helpers.
    """

    trim_kwargs = trim_kwargs or {
        "max_messages": 5,
        "summarize_old": True,
    }
    planning_kwargs = planning_kwargs or {
        "min_messages_for_update": 5,
        "max_plan_versions": 3,
    }

    message_trimming_hook = (
        create_message_trimming_hook(model=model, **trim_kwargs)
        if enable_trimming
        else None
    )
    rag_hook = (
        create_rag_context_hook(rag_retriever)
        if rag_retriever is not None
        else None
    )
    planning_hook = (
        create_planning_hook(model=model, **planning_kwargs)
        if enable_planning
        else None
    )

    enabled_steps = [
        step_name
        for step_name, hook in [
            ("trimming", message_trimming_hook),
            ("rag", rag_hook),
            ("planning", planning_hook),
        ]
        if hook is not None
    ]

    logger.debug(
        "Configured combined pre-model hook with steps: {}", enabled_steps
    )

    def _combined_hook(state: Dict[str, Any]) -> Dict[str, Any]:
        updated_state = state

        if message_trimming_hook is not None:
            updated_state = message_trimming_hook(updated_state)

        if rag_hook is not None:
            updated_state = rag_hook(updated_state)

        if planning_hook is not None:
            updated_state = planning_hook(updated_state)

        if drop_remaining_steps and "remaining_steps" in updated_state:
            updated_state = dict(updated_state)
            updated_state.pop("remaining_steps", None)

        return updated_state

    return _combined_hook


