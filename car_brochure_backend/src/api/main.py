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


app = FastAPI(
    title="Car Brochure Backend API",
    description="Backend API for car catalog browsing, comparison, lead submission, and admin management.",
    version="0.3.0",
    openapi_tags=_build_openapi_tags(),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
