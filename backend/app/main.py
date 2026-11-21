"""FastAPI application initialization, lifecycle management, and core endpoints."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings

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


@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint returning system status and current timestamp."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "tandora",
        "version": "1.0.0"
    }
