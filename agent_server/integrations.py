"""User-managed integration configuration and destination resolution."""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlsplit

from agent_server.persistence.secrets import SecretRepository


SLACK_PROVIDER = "slack"
SLACK_WEBHOOK_HOST = "hooks.slack.com"
SLACK_WEBHOOK_URL_MAX_LENGTH = 2048


class IntegrationValidationError(ValueError):
    """Raised when an integration's configuration is not usable."""


def validate_slack_webhook_url(value: str) -> str:
    """Validate an incoming webhook URL without contacting Slack."""

    url = value.strip()
    if not url:
        raise IntegrationValidationError("Webhook URL is required")
    if len(url) > SLACK_WEBHOOK_URL_MAX_LENGTH:
        raise IntegrationValidationError("Webhook URL is too long")
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise IntegrationValidationError("Webhook URL is invalid") from error
    if parsed.scheme != "https":
        raise IntegrationValidationError("Webhook URL must use HTTPS")
    if parsed.username or parsed.password:
        raise IntegrationValidationError("Webhook URL must not contain credentials")
    if parsed.hostname != SLACK_WEBHOOK_HOST:
        raise IntegrationValidationError(f"Webhook URL must point to {SLACK_WEBHOOK_HOST}")
    if not parsed.path.startswith("/services/") or len(parsed.path.split("/")) < 4:
        raise IntegrationValidationError("Webhook URL must be a Slack incoming webhook URL")
    if parsed.query or parsed.fragment:
        raise IntegrationValidationError("Webhook URL must not contain a query or fragment")
    return url


class SlackDestinationResolver(Protocol):
    """Resolve the Slack destination for an investigation owner."""

    async def webhook_url_for(self, owner_user_id: str) -> str | None: ...


class IntegrationSlackDestinationResolver:
    """Resolve enabled Slack integrations from the encrypted secret store."""

    def __init__(self, secrets: SecretRepository) -> None:
        self._secrets = secrets

    async def webhook_url_for(self, owner_user_id: str) -> str | None:
        row = await self._secrets.get_integration(owner_user_id, SLACK_PROVIDER)
        if row is None or not row.enabled:
            return None
        return await self._secrets.decrypt_integration_webhook_url(row)


__all__ = [
    "SLACK_PROVIDER",
    "IntegrationSlackDestinationResolver",
    "IntegrationValidationError",
    "SlackDestinationResolver",
    "validate_slack_webhook_url",
]
