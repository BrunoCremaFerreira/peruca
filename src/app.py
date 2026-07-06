import logging
from contextlib import asynccontextmanager

from domain.exceptions import ValidationError
from fastapi import Depends, FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from infra.logging_config import configure_logging
from infra.security import require_api_key
from infra.settings import Settings
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from routes import public_router, router

logger = logging.getLogger(__name__)
settings = Settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging(settings.log_level)
    if not settings.peruca_api_key.get_secret_value():
        logger.warning(
            "PERUCA_API_KEY is not set - the API is running WITHOUT authentication. "
            "Set PERUCA_API_KEY and send it as the X-API-Key header."
        )
    yield


app = FastAPI(lifespan=lifespan)
# /health stays public; every other route requires the API key when configured.
app.include_router(public_router)
app.include_router(router, dependencies=[Depends(require_api_key)])

# CORS configuration. allow_credentials must be False when origins is the "*"
# wildcard, otherwise the browser rejects the response and the pairing is
# meaningless (SEC-003).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],  # CORS origin
    allow_credentials=settings.cors_origin != "*",
    allow_methods=["*"],  # Allow all HTTP Methods (GET, POST, etc)
    allow_headers=["*"],  # Allow all headers
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Peruca - LLM Virtual Assistant",
        version="1.0.0",
        description="Peruca is an advanced virtual assistant that utilizes large language models (LLMs) such as ChatGPT and Local AI. This repository contains everything you need to set up, integrate, and use Peruca as a virtual assistant, compatible with Node-RED and Virtual Assistant.",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


@app.exception_handler(ValidationError)
async def app_validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": str(exc), "errors": exc.errors},
    )


app.openapi = custom_openapi

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
