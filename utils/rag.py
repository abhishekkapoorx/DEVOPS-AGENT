"""Utility helpers for retrieving contextual information from Pinecone."""

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
#
# This module encapsulates the Retrieval Augmented Generation (RAG) plumbing
# that our supervisor agent relies on to enrich user conversations with
# context retrieved from the Pinecone vector store.  The high-level flow is:
#
#   1. ``get_pinecone_retriever`` boots a cached LangChain retriever, wiring it
#      up to the Pinecone index created by the indexing pipeline.
#   2. ``create_rag_context_hook`` wraps that retriever in a LangGraph-compatible
#      pre-model hook.  Just before the LLM is invoked we fetch the most similar
#      documents and append a formatted summary to the conversation state.
#   3. Downstream components (planning hook, agents, etc.) can read the
#      ``rag_context`` field in the state if they need direct access to the
#      retrieved snippets.
#
# The intent of the comments sprinkled throughout the file is to help future
# contributors reason about the control flow quickly when debugging or making
# improvements.

from __future__ import annotations

import os
from functools import lru_cache
from typing import Callable, Dict, Any, Optional, Iterable

from langchain_pinecone import PineconeVectorStore
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return the trimmed environment variable or the provided default."""
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


@lru_cache(maxsize=1)
def get_pinecone_retriever(
    index_name: Optional[str] = None,
    top_k: int = 3,
) -> Optional[BaseRetriever]:
    """Return a cached LangChain retriever backed by Pinecone.

    Parameters
    ----------
    index_name
        Optional override for the Pinecone index name; defaults to
        ``PINECONE_INDEX_NAME`` env var or ``"codebase-index"``.
    top_k
        Number of results to retrieve per query. Defaults to 3 to avoid
        token limit issues.

    Returns
    -------
    BaseRetriever | None
        A configured retriever when Pinecone is available, otherwise ``None``.
    """

    # Bail out early if the API key is missing; this keeps the supervisor
    # functional even when Pinecone is not configured.

    api_key = _get_env("PINECONE_API_KEY")
    if not api_key:
        return None

    index = index_name or _get_env("PINECONE_INDEX_NAME", "codebase-index")
    if not index:
        return None

    model_name = _get_env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    embedding = HuggingFaceEmbeddings(model_name=model_name)
    try:
        # ``from_existing_index`` does not create the index; it simply connects
        # to an index that should have been provisioned by the indexing flow.
        vectorstore = PineconeVectorStore.from_existing_index(
            index_name=index,
            embedding=embedding,
        )
    except Exception:
        return None

    return vectorstore.as_retriever(search_kwargs={"k": top_k})


def create_rag_context_hook(
    retriever: BaseRetriever,
    *,
    context_prefix: str = "Retrieved context:\n",
    max_docs: Optional[int] = 3,
    max_chunk_length: int = 1500,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Produce a LangGraph pre-model hook that injects Pinecone context.

    Parameters
    ----------
    retriever
        The LangChain retriever responsible for returning similar documents.
    context_prefix
        Text prepended to the generated system message. Defaults to
        ``"Retrieved context:"``.
    max_docs
        Maximum number of documents to include in the formatted output. When
        ``None`` all retrieved documents are used. Defaults to 3 to avoid
        token limit issues.
    max_chunk_length
        Maximum number of characters per document chunk. Longer chunks will
        be truncated. Defaults to 1500 to keep token usage reasonable.

    Returns
    -------
    Callable[[dict], dict]
        A hook that appends a formatted Markdown system message and stores the
        combined context inside the state as ``rag_context``.
    """

    def _format_documents(docs: Iterable[Document]) -> str:
        """Convert raw ``Document`` objects into Markdown with metadata."""
        sections = []
        # Use max_chunk_length from closure

        for idx, doc in enumerate(docs):
            if max_docs is not None and idx >= max_docs:
                break

            metadata = doc.metadata or {}
            # The title is derived from the richest metadata we have; fall back
            # to a generic label if none is available.
            title = metadata.get("title") or metadata.get("filename") or metadata.get("file_path") or metadata.get("relative_path") or "Retrieved Document"
            section_lines = [f"### {title}"]

            info_items = []
            location = metadata.get("file_path") or metadata.get("path") or metadata.get("source") or metadata.get("relative_path")
            if location:
                info_items.append(f"- Location: `{location}`")

            score = metadata.get("score") or metadata.get("vector_score")
            if score is not None:
                try:
                    info_items.append(f"- Similarity: {float(score):.4f}")
                except (TypeError, ValueError):
                    info_items.append(f"- Similarity: {score}")

            chunk_index = metadata.get("chunk_index")
            if chunk_index is not None:
                info_items.append(f"- Chunk: {chunk_index}")

            language = metadata.get("extension") or metadata.get("language")
            if language:
                info_items.append(f"- Language: {language}")

            if info_items:
                section_lines.extend(info_items)

            content = (doc.page_content or "").strip()
            if not content:
                content = "(No content returned)"
            elif len(content) > max_chunk_length:
                # Truncate content to avoid token limit issues
                content = content[:max_chunk_length] + "\n... (truncated)"

            section_lines.append("\n```markdown\n" + content + "\n```")

            sections.append("\n".join(section_lines))

        combined = "\n\n".join(sections)
        return combined

    def _hook(state: Dict[str, Any]) -> Dict[str, Any]:
        """Augment state with Markdown-formatted RAG context."""
        messages = state.get("messages", []) or []
        if not messages:
            return state

        last_message = messages[-1]

        if not isinstance(last_message, HumanMessage):
            return state

        query = getattr(last_message, "content", None)
        if not query:
            return state

        try:
            # Fetch the most relevant documents.  The retriever encapsulates
            # batching and similarity search mechanics.
            documents: list[Document] = retriever.get_relevant_documents(query)
        except Exception:
            return state

        if not documents:
            return state

        combined_context = _format_documents(documents)
        if not combined_context:
            return state

        # The formatted context is appended as a system message so the core LLM
        # can treat it as non-user guidance while still having the conversation
        # history available for reference.
        context_message = SystemMessage(content=f"{context_prefix}{combined_context}")

        new_messages = list(messages) + [context_message]

        return {
            **state,
            "messages": new_messages,
            "rag_context": combined_context,
        }

    return _hook


