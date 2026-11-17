"""Small LangChain adapter; no LangChain types escape this module."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class LLMBudget:
    max_tokens: int = 2_000
    max_cost_usd: float = 0.25
    timeout_seconds: float = 30


@dataclass(frozen=True)
class LLMResult:
    parsed: BaseModel | dict[str, Any] | None
    text: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str
    latency_ms: float


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        budget: LLMBudget | None = None,
    ) -> LLMResult: ...


def _price_table() -> dict[str, tuple[float, float]]:
    default = {"gpt-4o-mini": (0.00015, 0.0006)}
    raw = os.getenv("LLM_PRICE_TABLE_JSON")
    if not raw:
        return default
    try:
        values = json.loads(raw)
        return {
            name: (float(price.get("input_per_1k", 0)), float(price.get("output_per_1k", 0)))
            for name, price in values.items()
        }
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage_metadata", None) or {}
    if not usage:
        usage = getattr(response, "response_metadata", {}).get("token_usage", {})
    return int(usage.get("input_tokens", usage.get("prompt_tokens", 0))), int(
        usage.get("output_tokens", usage.get("completion_tokens", 0))
    )


def _text(response: Any) -> str | None:
    value = getattr(response, "content", response if isinstance(response, str) else None)
    return value if isinstance(value, str) else None


class LangChainLLMClient:
    def __init__(self, model: Any, *, model_name: str, prices: dict[str, tuple[float, float]] | None = None) -> None:
        self.model = model
        self.model_name = model_name
        self.prices = prices or _price_table()

    async def complete(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        budget: LLMBudget | None = None,
    ) -> LLMResult:
        from langchain_core.messages import HumanMessage, SystemMessage

        budget = budget or LLMBudget()
        converted = [
            SystemMessage(content=item["content"])
            if item["role"] == "system"
            else HumanMessage(content=item["content"])
            for item in messages
        ]
        chain = (
            self.model.with_structured_output(schema, include_raw=True)
            if schema is not None
            else self.model
        )
        started = time.perf_counter()
        response = await asyncio.wait_for(chain.ainvoke(converted), timeout=budget.timeout_seconds)
        latency_ms = (time.perf_counter() - started) * 1000
        raw_response = response.get("raw") if isinstance(response, dict) else response
        parsed = response.get("parsed") if isinstance(response, dict) else None
        tokens_in, tokens_out = _usage(raw_response)
        if tokens_in + tokens_out > budget.max_tokens:
            raise RuntimeError("LLM token budget exceeded")
        input_price, output_price = self.prices.get(self.model_name, (0, 0))
        cost = (tokens_in / 1000 * input_price) + (tokens_out / 1000 * output_price)
        if cost > budget.max_cost_usd:
            raise RuntimeError("LLM cost budget exceeded")
        return LLMResult(
            parsed=parsed,
            text=_text(raw_response),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            model=self.model_name,
            latency_ms=latency_ms,
        )


class FakeLLMClient:
    def __init__(self, scripted: list[LLMResult | BaseModel | dict[str, Any] | Exception]) -> None:
        self.scripted = list(scripted)
        self.calls: list[list[dict[str, str]]] = []

    async def complete(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        budget: LLMBudget | None = None,
    ) -> LLMResult:
        self.calls.append(messages)
        if not self.scripted:
            raise RuntimeError("FakeLLMClient has no scripted response")
        value = self.scripted.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, LLMResult):
            return value
        return LLMResult(value, None, 10, 20, 0.001, "fake", 1)


def prompt_hash(messages: list[dict[str, str]]) -> str:
    return sha256(json.dumps(messages, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def client_from_environment() -> LLMClient | None:
    """Build the configured provider client, or return None for deterministic mode."""

    provider = os.getenv("DEVOPS_AGENT_MODEL_PROVIDER", "openai")
    model_name = os.getenv("DEVOPS_AGENT_MODEL_NAME", "gpt-4o-mini")
    try:
        if provider == "openai":
            if not os.getenv("OPENAI_API_KEY") and not os.getenv("DEVOPS_AGENT_MODEL_BASE_URL"):
                return None
            from langchain_openai import ChatOpenAI

            kwargs = {"model": model_name}
            if os.getenv("DEVOPS_AGENT_MODEL_BASE_URL"):
                kwargs["base_url"] = os.environ["DEVOPS_AGENT_MODEL_BASE_URL"]
            model = ChatOpenAI(**kwargs)
        elif provider == "groq":
            if not os.getenv("GROQ_API_KEY"):
                return None
            from langchain_groq import ChatGroq

            model = ChatGroq(model=model_name)
        elif provider == "gemini":
            if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
                return None
            from langchain_google_genai import ChatGoogleGenerativeAI

            model = ChatGoogleGenerativeAI(model=model_name)
        else:
            from langchain_ollama import ChatOllama

            model = ChatOllama(model=model_name)
        return LangChainLLMClient(model, model_name=model_name)
    except Exception:
        return None


__all__ = [
    "FakeLLMClient",
    "LLMBudget",
    "LLMClient",
    "LLMResult",
    "LangChainLLMClient",
    "client_from_environment",
    "prompt_hash",
]
