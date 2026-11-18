"""Alertmanager webhook models and deterministic alert normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


AlertStatus = Literal["firing", "resolved"]


class AlertmanagerAlert(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: AlertStatus
    labels: dict[str, str]
    annotations: dict[str, str]
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime = Field(alias="endsAt")
    generator_url: str = Field(default="", alias="generatorURL")
    fingerprint: str | None = None


class AlertmanagerWebhook(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str
    group_key: str = Field(default="", alias="groupKey")
    truncated_alerts: int | None = Field(default=None, alias="truncatedAlerts")
    status: AlertStatus
    receiver: str = ""
    group_labels: dict[str, str] = Field(default_factory=dict, alias="groupLabels")
    common_labels: dict[str, str] = Field(default_factory=dict, alias="commonLabels")
    common_annotations: dict[str, str] = Field(
        default_factory=dict, alias="commonAnnotations"
    )
    external_url: str = Field(default="", alias="externalURL")
    # Raw dictionaries preserve per-alert fault isolation: one malformed alert
    # must not invalidate the rest of a grouped webhook.
    alerts: list[Any]


@dataclass(frozen=True)
class AlertNormalizationContext:
    common_labels: Mapping[str, str]
    common_annotations: Mapping[str, str]
    received_at: datetime


class NormalizedAlert(BaseModel):
    source: Literal["alertmanager"] = "alertmanager"
    owner_user_id: str = "system"
    source_fingerprint: str | None = None
    alertname: str
    severity: str = "unknown"
    status: AlertStatus
    namespace: str | None = None
    workload: str | None = None
    pod: str | None = None
    container: str | None = None
    service: str | None = None
    node: str | None = None
    summary: str
    description: str
    labels: dict[str, str]
    annotations: dict[str, str]
    started_at: datetime | None
    ended_at: datetime | None
    received_at: datetime
    generator_url: str | None = None
    raw: dict[str, Any]


_POD_HASH_SUFFIX = re.compile(
    r"(?:-[a-z0-9]{9,10}-[a-z0-9]{5}|-[a-z0-9]{9,10})$", re.IGNORECASE
)


def _strip_pod_hash(value: str | None) -> str | None:
    if not value:
        return value
    return _POD_HASH_SUFFIX.sub("", value)


def _value(labels: Mapping[str, str], context: Mapping[str, str], key: str) -> str | None:
    return labels.get(key) or context.get(key) or None


def _zero_time(value: datetime) -> datetime | None:
    if value.year == 1 and value.month == 1 and value.day == 1:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_alert(
    raw_alert: Mapping[str, Any], payload_context: AlertNormalizationContext
) -> NormalizedAlert:
    """Normalize one validated Alertmanager alert without side effects."""

    alert = AlertmanagerAlert.model_validate(raw_alert)
    labels = dict(alert.labels)
    annotations = dict(alert.annotations)
    common_labels = payload_context.common_labels
    common_annotations = payload_context.common_annotations
    alertname = _value(labels, common_labels, "alertname") or "unknown"
    pod = _value(labels, common_labels, "pod")
    workload = next(
        (
            _value(labels, common_labels, key)
            for key in ("deployment", "statefulset", "daemonset")
            if _value(labels, common_labels, key)
        ),
        _strip_pod_hash(pod),
    )
    summary = annotations.get("summary") or common_annotations.get("summary") or alertname
    description = (
        annotations.get("description")
        or common_annotations.get("description")
        or alertname
    )

    return NormalizedAlert(
        source_fingerprint=alert.fingerprint,
        alertname=alertname,
        severity=_value(labels, common_labels, "severity") or "unknown",
        status=alert.status,
        namespace=_value(labels, common_labels, "namespace"),
        workload=_strip_pod_hash(workload),
        pod=pod,
        container=_value(labels, common_labels, "container"),
        service=_value(labels, common_labels, "service"),
        node=_value(labels, common_labels, "node"),
        summary=summary,
        description=description,
        labels=labels,
        annotations=annotations,
        started_at=_zero_time(alert.starts_at),
        ended_at=_zero_time(alert.ends_at),
        received_at=payload_context.received_at.astimezone(timezone.utc),
        generator_url=alert.generator_url or None,
        raw=dict(raw_alert),
    )


__all__ = [
    "AlertNormalizationContext",
    "AlertmanagerAlert",
    "AlertmanagerWebhook",
    "NormalizedAlert",
    "normalize_alert",
]
