"""ASGI entry point and console command for the API."""
from .deployment import create_api_from_environment
app = create_api_from_environment()


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
