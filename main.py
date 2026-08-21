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
    await redis_client.connect()
    try:
        await qdrant_store.connect()
    except Exception as e:
        print(f"⚠️  Qdrant Store Connect Warning: {e}")

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

app.include_router(api_router)

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
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)