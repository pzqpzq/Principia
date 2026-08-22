from __future__ import annotations

import socket
import webbrowser
from typing import Any

import uvicorn

from ..application.facade import Principia
from .app import create_app


def run_server(
    principia: Principia,
    *,
    port: int = 0,
    browser: bool = True,
) -> str:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(128)
    resolved_port = int(listener.getsockname()[1])
    url = f"http://127.0.0.1:{resolved_port}/research/new"
    app = create_app(principia, bound_port=resolved_port)
    print(f"Principia {__import__('principia').__version__}: {url}", flush=True)
    print(f"Workspace: {principia.workspace.path}", flush=True)
    if browser:
        webbrowser.open(url)
    config = uvicorn.Config(app, host="127.0.0.1", port=resolved_port, log_level="info")
    server = uvicorn.Server(config)
    try:
        server.run(sockets=[listener])
    except KeyboardInterrupt:
        pass
    finally:
        listener.close()
    return url


def app_for_testing(principia: Principia) -> Any:
    return create_app(
        principia,
        bound_port=None,
        test_mode=True,
    )
