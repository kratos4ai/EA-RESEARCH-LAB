"""Disposable command-capable stdio server backed by the portable test fake."""

from apps.mcp_adapter.server import ServerMode, create_server
from tests.test_mcp_adapter import _RecordingApi, _logger


if __name__ == "__main__":
    create_server(
        _RecordingApi(), mode=ServerMode.COMMAND_CAPABLE, logger=_logger()
    ).run()
