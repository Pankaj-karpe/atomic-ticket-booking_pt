# Terminal 1: your existing API
# uvicorn app.main:app --reload

import time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .routers import auth, event, reservation, orders, websocket, internal, admin, venue
from .database import engine
import logging
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from . import tracing
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

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "handler", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency", ["method", "handler"]
)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    handler = getattr(route, "path", None) or request.url.path
    REQUEST_COUNT.labels(request.method, handler, str(response.status_code)).inc()
    REQUEST_LATENCY.labels(request.method, handler).observe(time.perf_counter() - start)
    return response

@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


tracing.tracer = tracing.setup_tracing("backend")
FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()
SQLAlchemyInstrumentor().instrument(engine=engine)

app.include_router(auth.router)
app.include_router(event.router)
app.include_router(orders.router)
app.include_router(reservation.router)
app.include_router(websocket.router)
app.include_router(internal.router)  
app.include_router(admin.router)
app.include_router(venue.router)