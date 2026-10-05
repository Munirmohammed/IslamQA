"""
Shared FastAPI Dependencies
Provides request-scoped access to services initialized once at app startup
(see app.main.lifespan), instead of endpoints constructing and re-initializing
their own instances per request.
"""

from fastapi import Request

from app.services.knowledge_service import KnowledgeService
from app.services.ml_service import MLService
from app.services.recitation_asr_service import RecitationASRService
from app.services.voice_search_service import VoiceSearchService


def get_knowledge_service(request: Request) -> KnowledgeService:
    """Return the KnowledgeService initialized once at app startup."""
    return request.app.state.knowledge_service


def get_ml_service(request: Request) -> MLService:
    """Return the MLService initialized once at app startup."""
    return request.app.state.ml_service


def get_voice_search_service(request: Request) -> VoiceSearchService:
    """Return the VoiceSearchService initialized once at app startup."""
    return request.app.state.voice_search_service


def get_recitation_asr_service(request: Request) -> RecitationASRService:
    """Return the RecitationASRService initialized once at app startup."""
    return request.app.state.recitation_asr_service
