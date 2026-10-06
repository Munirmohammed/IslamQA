"""
API v1 Router
Main router for API version 1
"""

from fastapi import APIRouter
from app.api.v1.endpoints import auth, questions, search, admin, analytics, ai_chat, voice_search, recitation, gamification, memorization, tajweed

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(questions.router, prefix="/questions", tags=["Questions"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
api_router.include_router(ai_chat.router, prefix="/ai", tags=["AI Chat"])  # New AI chat endpoints
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(voice_search.router, prefix="/voice-search", tags=["Quran Voice Search"])
api_router.include_router(recitation.router, prefix="/recitation", tags=["Quran Recitation Check"])
api_router.include_router(gamification.router, prefix="/gamification", tags=["Gamification"])
api_router.include_router(memorization.router, prefix="/memorization", tags=["Memorization"])
api_router.include_router(tajweed.router, prefix="/tajweed", tags=["Tajweed"])
