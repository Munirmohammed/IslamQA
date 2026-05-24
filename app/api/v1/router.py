"""
API v1 Router
Main router for API version 1
"""

from fastapi import APIRouter
from app.api.v1.endpoints import (
    admin,
    ai_chat,
    analytics,
    auth,
    daily,
    duas,
    names,
    quran,
    questions,
    search,
    tools,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(questions.router, prefix="/questions", tags=["Questions"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(ai_chat.router, prefix="/ai", tags=["AI Chat"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(daily.router, prefix="/daily", tags=["Daily Content"])
api_router.include_router(tools.router, prefix="/tools", tags=["Islamic Tools"])
api_router.include_router(quran.router, prefix="/quran", tags=["Quran"])
api_router.include_router(names.router, prefix="/names", tags=["Asma ul-Husna"])
api_router.include_router(duas.router, prefix="/duas", tags=["Adhkar"])
