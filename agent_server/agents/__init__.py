"""Server-side agent implementations.

Agent modules are loaded lazily because some of them initialize external
providers or MCP clients at import time. Importing the package itself should
not start those integrations or require their credentials.
"""

__all__ = ["CloudAgent"]


def __getattr__(name: str):
    if name == "CloudAgent":
        from .CloudAgent import agent

        return agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
