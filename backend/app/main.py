"""SupportOps AI — FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from backend.app.api import api_router
from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.core.errors import register_error_handlers
from backend.app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_dir).mkdir(parents=True, exist_ok=True)
    init_db()
    logger.info("Starting %s (%s)", settings.app_name, settings.environment)
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Customer Support Operations Platform — Multi-Agent AI",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


app.include_router(api_router)


def _custom_openapi() -> dict:
    """Document the real error envelope.

    FastAPI generates the 422 schema from its own default handler, which we
    override in core/errors.py. Left alone, the spec advertises {"detail": [...]}
    while the API actually returns {"error": {...}} — anyone generating a client
    from this spec would build a parser for a shape that never arrives.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title, version=app.version, description=app.description, routes=app.routes
    )
    schema["components"].setdefault("schemas", {})["ErrorResponse"] = {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Stable machine-readable code."},
                    "message": {"type": "string"},
                    "details": {"type": "object"},
                },
                "required": ["code", "message"],
            }
        },
        "required": ["error"],
    }
    ref = {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}
    for path in schema["paths"].values():
        for op in path.values():
            if not isinstance(op, dict) or "responses" not in op:
                continue
            for code in ("400", "401", "403", "404", "409", "415", "422", "502", "503"):
                if code in op["responses"]:
                    op["responses"][code]["content"] = ref

    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi
