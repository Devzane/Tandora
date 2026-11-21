"""FastAPI application initialization, lifecycle management, and core endpoints."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api.v1 import api_v1_router
from app.ui import ui_router

# Configure local logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("tandora")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    settings = get_settings()
    logger.info(
        "Starting Tandora Local Hub on http://%s:%d (Dry Run: %s)",
        settings.fastapi_host,
        settings.fastapi_port,
        settings.dry_run
    )
    yield
    logger.info("Tandora Local Hub shutting down.")


app = FastAPI(
    title="Tandora Local Hub",
    description="Local-first AI-powered lead management and personalized outreach application.",
    version="1.0.0",
    lifespan=lifespan
)

# Restrict CORS to local development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets
static_path = Path(__file__).resolve().parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Mount API Routers
app.include_router(api_v1_router)

# Mount Local Web UI Routers
app.include_router(ui_router)


@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint returning system status and current timestamp."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "tandora",
        "version": "1.0.0"
    }
