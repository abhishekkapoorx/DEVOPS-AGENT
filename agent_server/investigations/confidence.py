"""Rule-based hypothesis confidence; model confidence is never trusted."""

from __future__ import annotations

from dataclasses import dataclass

from agent_server.investigations.evidence import Evidence
from agent_server.investigations.hypotheses import Hypothesis


@dataclass(frozen=True)
class Confidence:
    level: str
    reasons: list[str]
    score: int


def compute_confidence(
    hypothesis: Hypothesis,
    evidence: list[Evidence],
    collection_errors: list[dict[str, str]],
    verifier_drop_ratio: float = 0,
) -> Confidence:
    cited = {item for claim in hypothesis.claims for item in claim.evidence_ids}
    sources = {item.source for item in evidence if item.id in cited}
    reasons: list[str] = []
    score = 0
    direct_sources = {"kubernetes.pod_status", "kubernetes.events", "kubernetes.endpoints", "kubernetes.rollout_history"}
    if sources & direct_sources:
        score += 2
        reasons.append("direct Kubernetes signal cited")
    if len(sources) >= 2:
        score += 2
        reasons.append("independent evidence sources cited")
    if collection_errors:
        score -= 1
        reasons.append("collection errors reduce confidence")
    if verifier_drop_ratio > 0.5:
        score -= 1
        reasons.append("more than half of model claims were dropped")
    if len(hypothesis.claims) >= 2:
        score += 1
        reasons.append("multiple supported claims")
    level = "high" if score >= 4 else "medium" if score >= 2 else "low"
    return Confidence(level, reasons, score)


def rank_hypotheses(
    hypotheses: list[Hypothesis],
    evidence: list[Evidence],
    errors: list[dict[str, str]],
    verifier_drop_ratio: float = 0,
) -> list[tuple[Hypothesis, Confidence]]:
    ranked = [(item, compute_confidence(item, evidence, errors, verifier_drop_ratio)) for item in hypotheses]
    return sorted(ranked, key=lambda pair: (pair[1].score, len(pair[0].claims)), reverse=True)


__all__ = ["Confidence", "compute_confidence", "rank_hypotheses"]
