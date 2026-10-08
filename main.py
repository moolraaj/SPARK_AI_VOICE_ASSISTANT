from contextlib import asynccontextmanager
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, HTTPException
from app.database.mongodb import mongodb
from app.database.redis import redis_client
from app.rag.vectorstore.qdrant_store import qdrant_store
from app.api.api_collections import api_router
from app.common.error_handler.handlers import (
    validation_exception_handler,
    http_exception_handler,
    global_exception_handler
)
from app.seeds.seed_super_admin import seed_super_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Spark AI Assistant Backend...")
    await mongodb.connect()

    try:
        await redis_client.connect()
    except Exception:
        print("⚡ Redis not running. Auto-starting redis-server daemon...")
        import subprocess, asyncio
        subprocess.run(["redis-server", "--daemonize", "yes"], check=False)
        await asyncio.sleep(1)
        try:
            await redis_client.connect()
        except Exception as re_err:
            print(f"⚠️ Redis connection warning: {re_err}")

    try:
        await qdrant_store.connect()
    except Exception as e:
        print(f"⚠️ Qdrant Store Connect Warning: {e}")

    yield

    # Shutdown
    await mongodb.disconnect()
    await redis_client.disconnect()
    try:
        await qdrant_store.disconnect()
    except Exception:
        pass


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Spark AI Assistant",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.voice.telephony.hardware_websocket import router as hardware_websocket_router

app.include_router(api_router)
app.include_router(hardware_websocket_router)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler
)
app.add_exception_handler(
    HTTPException,
    http_exception_handler
)
app.add_exception_handler(
    Exception,
    global_exception_handler
)

@app.get("/healthy")
async def home():
    return {
        "message": "Spark AI Assistant Running"
    }


if __name__ == "__main__":
    import os
    import uvicorn
    # reload=True restarts the server on every file save, which drops the ESP32
    # WebSocket mid-call. Opt in with UVICORN_RELOAD=1 for pure API development.
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("UVICORN_RELOAD", "0") == "1",
        ws_ping_interval=30,
        ws_ping_timeout=30,
    )