"""FastAPI application entrypoint."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from .api import analytics, auth, campaigns, contacts, conversations, media, messages, settings as settings_api, tags, webhook
from .config import settings
from .core.security import decode_token
from .core.websocket_manager import manager
from .database import AsyncSessionLocal, init_db
from .services import queue_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all is idempotent (checkfirst=True): it only adds tables that don't
    # exist yet and never touches existing ones. Safe to run in production so new
    # tables ship without a manual schema.sql re-run.
    try:
        await init_db()
        logger.info("Database initialized (schema up to date)")
    except Exception as exc:  # noqa: BLE001
        logger.error("Database initialization failed: %s", exc)
    logger.info("%s started in %s environment", settings.app_name, settings.environment)
    worker_task = asyncio.create_task(queue_worker.run_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="WhatsApp CRM - manage cold DM conversations via the Meta WhatsApp Cloud API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------- API routers
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(contacts.router, prefix=settings.api_prefix)
app.include_router(tags.router, prefix=settings.api_prefix)
app.include_router(conversations.router, prefix=settings.api_prefix)
app.include_router(messages.router, prefix=settings.api_prefix)
app.include_router(media.router, prefix=settings.api_prefix)
app.include_router(analytics.router, prefix=settings.api_prefix)
app.include_router(settings_api.router, prefix=settings.api_prefix)
app.include_router(campaigns.router, prefix=settings.api_prefix)
app.include_router(webhook.router, prefix=settings.api_prefix)

# ---------------------------------------------------------------- health
@app.get("/health", tags=["System"])
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": "1.0.0"}


# ---------------------------------------------------------------- websocket
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(""),
) -> None:
    """Real-time event stream. Auth via ?token=<jwt>."""
    async with AsyncSessionLocal() as db:  # type: AsyncSession
        if not token:
            await websocket.close(code=4401, reason="Missing token")
            return
        try:
            payload = decode_token(token)
        except Exception:  # noqa: BLE001
            await websocket.close(code=4401, reason="Invalid token")
            return

        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4401, reason="Invalid token")
            return

        await manager.connect(user_id, websocket)
        try:
            while True:
                # We only push; keep the socket alive and swallow incoming text.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            await manager.disconnect(user_id, websocket)


# ---------------------------------------------------------------- static frontend
# Serve the single-page app from the same origin so the deployed frontend and
# API share one HTTPS URL (used for Render / single-service hosting).
_frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="static")
