import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.logging import configure_logging
from app.web.routes import router as web_router

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="InsightQuery",
    description=(
        "AI-powered data investigation and analytics platform. Structured questions "
        "are answered by validated, read-only SQL; document questions are answered by "
        "retrieval; the LLM only synthesizes evidence it is explicitly given."
    ),
    version="0.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)

app.include_router(router)
app.include_router(web_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error_code": "internal_error", "message": "An unexpected error occurred."},
    )
