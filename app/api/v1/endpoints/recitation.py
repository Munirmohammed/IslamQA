"""
Recitation Check Endpoints
Upload a recitation audio clip and get back: the transcript, the ayah it
was matched against, and a word-level mistake report (incorrect/missed/
extra words) -- the Tarteel-parity feature.

Two modes:
- `surah`/`ayah` provided: diff directly against that ayah ("practice this
  ayah" mode).
- Omitted: locate the ayah first via VoiceSearchService (Phase 1's engine),
  then diff against the best match ("just recite and find it" mode).
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import User
from app.core.dependencies import get_recitation_asr_service, get_voice_search_service
from app.core.security import RateLimiter, get_optional_user
from app.services.quran_corpus_service import QuranCorpusService
from app.services.recitation_asr_service import RecitationASRService, UnreadableAudioError
from app.services.recitation_diff_service import diff_recitation
from app.services.voice_search_service import VoiceSearchService

router = APIRouter()

# Shared corpus loader (lightweight: reads the already-cached corpus file
# built by VoiceSearchService's initialization; no network/model loading).
_corpus_service = QuranCorpusService()


class Mistake(BaseModel):
    type: str  # "incorrect" | "missed" | "extra"
    expected: str
    recited: str
    position: int


class RecitationCheckResponse(BaseModel):
    transcript: str
    surah_number: int
    surah_name_en: str
    ayah_number: int
    key: str
    text_uthmani: str
    translation_en: str
    mistakes: List[Mistake]
    is_correct: bool


@router.post("/check", response_model=RecitationCheckResponse)
async def check_recitation(
    request: Request,
    audio: UploadFile = File(..., description="WAV, MP3, FLAC, or OGG recitation clip"),
    surah: Optional[int] = Form(default=None, description="Target surah number (omit to auto-locate)"),
    ayah: Optional[int] = Form(default=None, description="Target ayah number (omit to auto-locate)"),
    user: Optional[User] = Depends(get_optional_user),
    asr_service: RecitationASRService = Depends(get_recitation_asr_service),
    voice_search_service: VoiceSearchService = Depends(get_voice_search_service),
):
    """Check a recited ayah against the canonical text."""
    if not settings.ENABLE_RECITATION_CHECKER:
        raise HTTPException(status_code=503, detail="Recitation checking is currently disabled")

    if user:
        if not RateLimiter.check_rate_limit(str(user.id), user.rate_limit):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    else:
        client_ip = request.client.host if request.client else "unknown"
        if not RateLimiter.check_rate_limit(f"ip:{client_ip}", 10):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    audio_bytes = await audio.read()

    try:
        transcript = asr_service.transcribe(audio_bytes)
    except UnreadableAudioError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

    try:
        if surah is not None and ayah is not None:
            _corpus_service.load_or_fetch()
            target_ayah = _corpus_service.get_ayah(surah, ayah)
            if not target_ayah:
                raise HTTPException(status_code=404, detail=f"Ayah {surah}:{ayah} not found")
        else:
            located = await voice_search_service.search(query=transcript, top_k=1)
            results = located.get("results", [])
            if not results:
                raise HTTPException(
                    status_code=404,
                    detail="Could not identify which ayah was recited -- try again or specify surah/ayah",
                )
            target_ayah = results[0]

        mistakes = diff_recitation(target_ayah["text_simple"], transcript)

        return RecitationCheckResponse(
            transcript=transcript,
            surah_number=target_ayah["surah_number"],
            surah_name_en=target_ayah["surah_name_en"],
            ayah_number=target_ayah["ayah_number"],
            key=target_ayah["key"],
            text_uthmani=target_ayah["text_uthmani"],
            translation_en=target_ayah["translation_en"],
            mistakes=[Mistake(**m) for m in mistakes],
            is_correct=len(mistakes) == 0,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recitation check failed: {str(e)}")
