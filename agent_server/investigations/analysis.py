"""Bounded LLM hypothesis loop followed by deterministic verification."""

from __future__ import annotations

import json
from dataclasses import dataclass

from agent_server.investigations.confidence import Confidence, rank_hypotheses
from agent_server.investigations.evidence import ContextPack
from agent_server.investigations.hypotheses import HypothesisResponse, VerifierReport, verify_hypotheses
from agent_server.investigations.llm import LLMClient, LLMBudget, LLMResult, prompt_hash
from agent_server.investigations.redaction import redact


@dataclass(frozen=True)
class AnalysisOutcome:
    response: HypothesisResponse
    verifier: VerifierReport
    ranked: list[tuple[object, Confidence]]
    llm_result: LLMResult
    prompt_hash: str


def _messages(pack: ContextPack) -> list[dict[str, str]]:
    evidence = [
        {"id": item.id, "source": item.source, "summary": item.summary, "raw": item.raw}
        for item in pack.evidence
    ]
    return [
        {
            "role": "system",
            "content": (
                "You are a read-only incident investigator. Produce only grounded hypotheses. "
                "Every claim must cite one or more evidence IDs. Suggested checks must be read-only. "
                "Do not invent evidence or claim remediation was performed."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                redact(
                    {
                        "alert": pack.model_dump(exclude={"evidence"}),
                        "evidence": evidence,
                    }
                ),
                sort_keys=True,
            ),
        },
    ]


async def analyze_context(
    pack: ContextPack,
    client: LLMClient,
    *,
    budget: LLMBudget | None = None,
) -> AnalysisOutcome:
    messages = _messages(pack)
    result = await client.complete(messages, schema=HypothesisResponse, budget=budget)
    response = result.parsed
    if not isinstance(response, HypothesisResponse):
        try:
            response = HypothesisResponse.model_validate(response)
        except Exception:
            repair_messages = messages + [
                {
                    "role": "user",
                    "content": "Repair the previous response. Return only the required structured hypothesis schema.",
                }
            ]
            result = await client.complete(repair_messages, schema=HypothesisResponse, budget=budget)
            response = result.parsed
            if not isinstance(response, HypothesisResponse):
                response = HypothesisResponse.model_validate(response)
    verified, verifier = verify_hypotheses(response, pack.evidence)
    drop_ratio = verifier.claims_dropped / verifier.claims_total if verifier.claims_total else 0
    ranked = rank_hypotheses(verified.hypotheses, pack.evidence, pack.collection_errors, drop_ratio)
    return AnalysisOutcome(verified, verifier, ranked, result, prompt_hash(messages))


__all__ = ["AnalysisOutcome", "analyze_context"]
