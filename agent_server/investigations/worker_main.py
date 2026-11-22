"""Standalone entry point for the durable investigation worker."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from agent_server.integrations import IntegrationSlackDestinationResolver
from agent_server.investigations.worker import InvestigationWorker
from agent_server.investigations.runner import InvestigationRunner
from agent_server.investigations.llm import LLMBudget, client_from_environment
from agent_server.persistence.postgres import create_session_factory
from agent_server.persistence.secrets import SecretRepository
from agent_server.secrets import SecretBox, SecretConfigurationError


logger = logging.getLogger(__name__)


async def _main() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine, sessions = create_session_factory(database_url)
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stopping.set)
        except NotImplementedError:
            pass
    try:
        budget = LLMBudget(
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2000")),
            max_cost_usd=float(os.getenv("LLM_MAX_COST_USD", "0.25")),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        )
        secret_repository = None
        if os.getenv("ENCRYPTION_KEY"):
            try:
                secret_repository = SecretRepository(sessions, SecretBox.from_environment())
            except SecretConfigurationError as error:
                raise RuntimeError(f"Invalid ENCRYPTION_KEY configuration: {error}") from error
        if secret_repository is None:
            logger.warning("ENCRYPTION_KEY is unset; Slack integrations are unavailable")
        runner = InvestigationRunner(
            sessions,
            slack_destination=(
                IntegrationSlackDestinationResolver(secret_repository)
                if secret_repository is not None
                else None
            ),
            llm_client=client_from_environment(),
            llm_budget=budget,
        )
        await InvestigationWorker(sessions, runner).run_forever(stopping)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
