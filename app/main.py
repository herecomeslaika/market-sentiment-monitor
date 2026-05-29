from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import deps
from app.api.routes import router as api_router
from app.ws.routes import router as ws_router
from config.settings import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    deps.settings = Settings()
    settings = deps.settings

    deps.news_queue = asyncio.Queue(maxsize=1000)
    deps.scored_queue = asyncio.Queue(maxsize=1000)
    deps.alert_queue = asyncio.Queue(maxsize=500)

    # Initialize SQLite database
    from app.db import init_db, close_db
    await init_db()
    logger.info("Database initialized")

    # Load subscriptions from DB
    from app.subscription.manager import load_subscriptions_from_db
    await load_subscriptions_from_db()

    # Initialize FinBERT process pool at startup
    from app.sentiment.finbert_worker import init_model
    deps.finbert_pool = ProcessPoolExecutor(
        max_workers=settings.process_pool_size,
        initializer=init_model,
        initargs=(settings.model_name,),
    )
    logger.info("Sentiment process pool created (%d workers, model=%s)", settings.process_pool_size, settings.model_name)

    # Start background tasks
    from app.crawler.scheduler import start_crawler
    from app.sentiment.fast_track import fast_track_consumer
    from app.analysis.slow_track import slow_track_consumer
    from app.ws.connection_manager import alert_pusher

    tasks = [
        asyncio.create_task(start_crawler(), name="crawler"),
        asyncio.create_task(fast_track_consumer(), name="fast_track"),
        asyncio.create_task(slow_track_consumer(), name="slow_track"),
        asyncio.create_task(alert_pusher(), name="alert_pusher"),
    ]
    deps.background_tasks = tasks

    logger.info("Background tasks started: %s", [t.get_name() for t in tasks])

    yield

    # --- Shutdown ---
    logger.info("Shutting down...")
    for task in deps.background_tasks:
        task.cancel()
    await asyncio.gather(*deps.background_tasks, return_exceptions=True)
    if deps.finbert_pool:
        deps.finbert_pool.shutdown(wait=False)
    await close_db()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Market Sentiment Monitor",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(ws_router)
    app.include_router(api_router)

    # Serve frontend static files
    from pathlib import Path
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


app = create_app()


def run_server():
    import uvicorn

    settings = Settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
