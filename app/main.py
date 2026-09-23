# Terminal 1: your existing API
# uvicorn app.main:app --reload

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .routers import auth, event, reservation, orders, websocket, internal, admin, venue
from .database import engine
import logging
from . import models, utils

models.Base.metadata.create_all(bind=engine)


# Define lifespan context manager for startup and shutdown events
# ============================================================================
# LOG SANITIZATION MIDDLEWARE
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    sanitizer = utils.TokenSanitizerFilter()

    for logger_name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.addFilter(sanitizer)
        for handler in logger.handlers:
            handler.addFilter(sanitizer)

    yield  # Application runs while yielded


app = FastAPI(lifespan=lifespan)

origins = ["*"]

@app.get("/")
async def root():
    return {"message": "this is root endpoint"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(event.router)
app.include_router(orders.router)
app.include_router(reservation.router)
app.include_router(websocket.router)
app.include_router(internal.router)  
app.include_router(admin.router)
app.include_router(venue.router)