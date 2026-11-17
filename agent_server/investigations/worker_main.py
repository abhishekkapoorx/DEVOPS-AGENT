"""Standalone entry point for the durable investigation worker."""

from __future__ import annotations

import asyncio
import os
import signal

from agent_server.investigations.worker import InvestigationWorker
from agent_server.persistence.postgres import create_session_factory


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
        await InvestigationWorker(sessions).run_forever(stopping)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
