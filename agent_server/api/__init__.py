"""Modular REST application for authenticated agent conversations."""

from .app import AuthenticatedPrincipal, create_app

__all__ = ["AuthenticatedPrincipal", "create_app"]
