"""
Islamic Q&A Chatbot Backend - Main Application
Advanced backend system for Islamic knowledge Q&A with ML-powered matching
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import structlog
import time

from app.core.config import settings
from app.core.database import engine, SessionLocal
from app.core.security import get_current_user
from app.api.v1 import api_router
from app.websocket.chat import websocket_router
from app.core.monitoring import PrometheusMiddleware
from app.core.rate_limiting import RateLimitMiddleware

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting Islamic Q&A Chatbot Backend")
    
    # Initialize ML models
    from app.services.ml_service import MLService
    ml_service = MLService()
    await ml_service.initialize_models()
    app.state.ml_service = ml_service
    
    # Initialize knowledge base
    from app.services.knowledge_service import KnowledgeService
    knowledge_service = KnowledgeService()
    await knowledge_service.initialize()
    app.state.knowledge_service = knowledge_service
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Islamic Q&A Chatbot Backend")


app = FastAPI(
    title="Islamic Q&A Chatbot Backend",
    description="Advanced backend system for Islamic knowledge Q&A with ML-powered matching",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Add security middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
if settings.ENABLE_RATE_LIMITING:
    app.add_middleware(RateLimitMiddleware)

if settings.ENABLE_ANALYTICS:
    app.add_middleware(PrometheusMiddleware)


@app.middleware("http")
async def add_process_time_header(request, call_next):
    """Add processing time to response headers"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    logger.error("HTTP exception", status_code=exc.status_code, detail=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler"""
    logger.error("Unhandled exception", error=str(exc), type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "status_code": 500}
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Islamic Q&A Chatbot Backend",
        "version": "1.0.0",
        "timestamp": time.time()
    }


# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Include WebSocket routes
if settings.ENABLE_WEBSOCKETS:
    app.include_router(websocket_router, prefix="/ws")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
