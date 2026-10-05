"""
Voice Search Endpoints ("Tasmeea")
Recite (or type) a Quran fragment and find the matching ayah/surah, so a
frontend mushaf view can jump straight to it. Speech-to-text itself is a
later phase -- this endpoint takes the transcript text directly, same as a
future ASR step would hand it off.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.database import User
from app.core.security import get_optional_user, RateLimiter
from app.core.dependencies import get_voice_search_service
from app.services.voice_search_service import VoiceSearchService

router = APIRouter()


class VoiceSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Recited/typed Quran fragment")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum ayah matches")


class AyahMatch(BaseModel):
    surah_number: int
    surah_name_ar: str
    surah_name_en: str
    surah_name_translation_en: str
    ayah_number: int
    key: str
    text_uthmani: str
    translation_en: str
    juz: int
    page: int
    fused_score: float


class VoiceSearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[AyahMatch]


@router.post("/", response_model=VoiceSearchResponse)
async def voice_search(
    search_request: VoiceSearchRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    voice_search_service: VoiceSearchService = Depends(get_voice_search_service),
):
    """Find the ayah(s) matching a recited/typed Quran fragment."""
    if not settings.ENABLE_VOICE_SEARCH:
        raise HTTPException(status_code=503, detail="Voice search is currently disabled")

    if user:
        if not RateLimiter.check_rate_limit(str(user.id), user.rate_limit):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    else:
        client_ip = request.client.host if request.client else "unknown"
        if not RateLimiter.check_rate_limit(f"ip:{client_ip}", 20):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        search_results = await voice_search_service.search(
            query=search_request.query,
            top_k=search_request.limit,
        )

        results = [
            AyahMatch(
                surah_number=r["surah_number"],
                surah_name_ar=r["surah_name_ar"],
                surah_name_en=r["surah_name_en"],
                surah_name_translation_en=r["surah_name_translation_en"],
                ayah_number=r["ayah_number"],
                key=r["key"],
                text_uthmani=r["text_uthmani"],
                translation_en=r["translation_en"],
                juz=r["juz"],
                page=r["page"],
                fused_score=r.get("fused_score", 0.0),
            )
            for r in search_results.get("results", [])
        ]

        return VoiceSearchResponse(
            query=search_request.query,
            total_results=len(results),
            results=results,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice search failed: {str(e)}")
