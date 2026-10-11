"""Compatibility entry point for ``python -m cli``."""

from agent_cli import __main__ as _implementation

CommandExecutor = _implementation.CommandExecutor


def main(argv=None):
    # Preserve the old monkeypatch seam while delegating implementation to the
    # independently packageable CLI.
    original = _implementation.CommandExecutor
    _implementation.CommandExecutor = CommandExecutor
    try:
        return _implementation.main(argv)
    finally:
        _implementation.CommandExecutor = original


if __name__ == "__main__":
    raise SystemExit(main())
