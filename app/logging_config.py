import logging
import sys
import uuid

from fastapi import Request

SMARTRECO_HANDLER_NAME = "smartreco-app"


def configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(level=numeric_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    app_logger = logging.getLogger("app")
    app_logger.setLevel(numeric_level)
    app_logger.disabled = False
    app_logger.propagate = False

    handler = None
    for h in app_logger.handlers:
        if h.name == SMARTRECO_HANDLER_NAME:
            handler = h
            break

    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.name = SMARTRECO_HANDLER_NAME
        app_logger.addHandler(handler)

    handler.setLevel(numeric_level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)


async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response
