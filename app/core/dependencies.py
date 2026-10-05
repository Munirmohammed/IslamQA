"""
Shared FastAPI Dependencies
Provides request-scoped access to services initialized once at app startup
(see app.main.lifespan), instead of endpoints constructing and re-initializing
their own instances per request.
"""

from fastapi import Request

from app.services.knowledge_service import KnowledgeService
from app.services.ml_service import MLService


def get_knowledge_service(request: Request) -> KnowledgeService:
    """Return the KnowledgeService initialized once at app startup."""
    return request.app.state.knowledge_service


def get_ml_service(request: Request) -> MLService:
    """Return the MLService initialized once at app startup."""
    return request.app.state.ml_service
