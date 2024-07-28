from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from adapters.inbound.controllers.prompt_controller import router as prompt_router

app = FastAPI()

app.include_router(prompt_router)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="LLM API",
        version="1.0.0",
        description="API para interação com diferentes modelos de LLM",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
