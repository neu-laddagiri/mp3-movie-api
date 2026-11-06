import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def log_requests(request: Request, call_next):
    """Log one request and attach its request ID to the response."""
    request_id = uuid.uuid4().hex[:8]
    request.state.request_id = request_id
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        # Unexpected crash: the full traceback goes to the server log, the client gets a short message
        logger.error(f"Unexpected failure: request_id={request_id}", exc_info=True)
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

    duration_ms = (time.perf_counter() - started) * 1000

    # One summary line per request, with the log level picked from the status code
    message = (
        f"request_id={request_id} {request.method} {request.url.path} "
        f"status={response.status_code} duration={duration_ms:.1f}ms"
    )
    if response.status_code >= 500:
        logger.error(message)
    elif response.status_code >= 400:
        logger.warning(message)
    else:
        logger.info(message)

    response.headers["X-Request-ID"] = request_id
    return response