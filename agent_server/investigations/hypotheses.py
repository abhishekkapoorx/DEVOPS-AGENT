"""Structured hypothesis output and deterministic claim verification."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from agent_server.investigations.evidence import Evidence


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    id: str
    title: str
    root_cause_category: str
    claims: list[Claim] = Field(default_factory=list)
    suggested_next_checks: list[str] = Field(default_factory=list)


class HypothesisResponse(BaseModel):
    hypotheses: list[Hypothesis] = Field(default_factory=list)


class VerifierReport(BaseModel):
    claims_total: int = 0
    claims_kept: int = 0
    claims_dropped: int = 0
    grounded_claim_rate: float = 0
    dropped: list[dict[str, str]] = Field(default_factory=list)


_STOPWORDS = {
    "the", "and", "was", "is", "are", "with", "from", "that", "this", "for", "because", "has", "had", "to", "of", "in", "on", "a", "an", "as", "by", "it", "its", "not", "due", "failed", "failure",
}


def _concrete_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_.:-]{2,}|\b\d+(?:\.\d+)?\b", text)
        if token.lower() not in _STOPWORDS
    }


def verify_hypotheses(
    response: HypothesisResponse,
    evidence: list[Evidence],
) -> tuple[HypothesisResponse, VerifierReport]:
    evidence_by_id = {item.id: item for item in evidence}
    kept_hypotheses: list[Hypothesis] = []
    report = VerifierReport()
    evidence_text = {
        key: (item.summary + " " + str(item.raw)).lower()
        for key, item in evidence_by_id.items()
    }
    for hypothesis in response.hypotheses:
        kept_claims: list[Claim] = []
        for claim in hypothesis.claims:
            report.claims_total += 1
            missing = [item for item in claim.evidence_ids if item not in evidence_by_id]
            if not claim.evidence_ids:
                reason = "claim has no evidence ids"
            elif missing:
                reason = "claim cites unknown evidence ids"
            else:
                tokens = _concrete_tokens(claim.text)
                cited_text = " ".join(evidence_text[item] for item in claim.evidence_ids)
                reason = "" if tokens and all(token in cited_text for token in tokens) else "claim is not grounded in cited evidence"
            if reason:
                report.claims_dropped += 1
                report.dropped.append({"hypothesis_id": hypothesis.id, "claim": claim.text, "reason": reason})
            else:
                report.claims_kept += 1
                kept_claims.append(claim)
        if kept_claims:
            kept_hypotheses.append(hypothesis.model_copy(update={"claims": kept_claims}))
    if report.claims_total:
        report.grounded_claim_rate = report.claims_kept / report.claims_total
    return HypothesisResponse(hypotheses=kept_hypotheses), report


__all__ = ["Claim", "Hypothesis", "HypothesisResponse", "VerifierReport", "verify_hypotheses"]
