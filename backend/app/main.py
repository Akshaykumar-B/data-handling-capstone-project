"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .core.config import settings
from .services.data_access import data_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    missing = data_store.missing_runtime_files()
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(
            "Missing required processed runtime files: "
            f"{missing_list}. Set TRANSIT_PROCESSED_DIR to the mounted data directory."
        )
    yield


app = FastAPI(title="Public Transit Dashboard API", version="0.3.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(router)
