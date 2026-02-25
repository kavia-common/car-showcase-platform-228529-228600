import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router


def _build_openapi_tags() -> list[dict]:
    return [
        {
            "name": "public",
            "description": "Public catalog endpoints for browsing, searching, comparison, and lead submission.",
        },
        {
            "name": "admin",
            "description": (
                "Admin CRUD endpoints secured via HTTP Basic auth. "
                "Set ADMIN_USERNAME and ADMIN_PASSWORD in environment."
            ),
        },
    ]


def _get_cors_allow_origins() -> list[str]:
    """
    Resolve CORS allowed origins.

    We default to "*" for broad compatibility in development, but browsers do not allow
    "*" together with credentials. When credentials are allowed, we must return explicit
    origins.

    Env:
      - CORS_ALLOW_ORIGINS: comma-separated list of allowed origins.
        Example: "http://localhost:3000,https://my-frontend.example.com"
    """
    raw = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(
    title="Car Brochure Backend API",
    description="Backend API for car catalog browsing, comparison, lead submission, and admin management.",
    version="0.3.0",
    openapi_tags=_build_openapi_tags(),
)

_allow_origins = _get_cors_allow_origins()
_allow_credentials = True if _allow_origins != ["*"] else False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get(
    "/",
    tags=["public"],
    summary="Health check",
    description="Simple health check endpoint.",
    operation_id="health_check",
)
def health_check():
    """Health check endpoint.

    Returns:
        JSON object indicating service is healthy.
    """
    return {"message": "Healthy"}
