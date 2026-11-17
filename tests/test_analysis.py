import pytest

from agent_server.investigations.analysis import analyze_context
from agent_server.investigations.evidence import ContextPack, Evidence
from agent_server.investigations.hypotheses import HypothesisResponse
from agent_server.investigations.llm import FakeLLMClient


def _pack():
    return ContextPack(
        investigation_id="i",
        alertname="KubeContainerOOMKilled",
        namespace="boutique",
        workload="recommendationservice",
        severity="critical",
        summary="memory pressure",
        evidence=[
            Evidence(
                id="ev-oom",
                investigation_id="i",
                source="kubernetes.pod_status",
                query="pod/recommendationservice",
                fetched_at="2026-11-15T09:00:00Z",
                summary="recommendationservice last terminated reason OOMKilled",
                raw_ref="evidence:i:pod",
            )
        ],
    )


@pytest.mark.asyncio
async def test_verifier_keeps_grounded_claim_and_drops_unknown_evidence():
    client = FakeLLMClient(
        [
            HypothesisResponse(
                hypotheses=[
                    {
                        "id": "h1",
                        "title": "Memory limit caused OOMKilled",
                        "root_cause_category": "resource",
                        "claims": [
                            {"text": "recommendationservice was OOMKilled", "evidence_ids": ["ev-oom"]},
                            {"text": "unsupported claim", "evidence_ids": ["missing"]},
                        ],
                    }
                ]
            )
        ]
    )

    outcome = await analyze_context(_pack(), client)

    assert outcome.verifier.claims_kept == 1
    assert outcome.verifier.claims_dropped == 1
    assert outcome.ranked[0][1].level in {"low", "medium", "high"}
