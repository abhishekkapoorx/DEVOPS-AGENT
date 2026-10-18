"""ASGI entry point and console command for the Tool Service."""
from .deployment import create_tool_service_from_environment
app = create_tool_service_from_environment()


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
