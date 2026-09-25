from __future__ import annotations

import argparse
import webbrowser

import uvicorn

from .config import get_settings, with_overrides


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vibrato", description="Run the Vibrato vocal analysis workstation."
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--open", action="store_true", help="Open the browser after starting.")
    parser.add_argument("--reload", action="store_true", help="Reload the server when backend code changes.")
    args = parser.parse_args()
    settings = get_settings()
    if args.host or args.port:
        settings = with_overrides(host=args.host or settings.host, port=args.port or settings.port)
    url = f"http://{settings.host}:{settings.port}"
    if args.open:
        webbrowser.open(url)
    uvicorn.run(
        "vibrato.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
