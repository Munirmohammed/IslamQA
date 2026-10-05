"""
Memorization (Hifz) Endpoints
SM-2 spaced-repetition scheduling for Quran memorization, gradeable either
directly or from a Phase 2 recitation-check's mistake count, plus a
mutashabihat (confusable-verse) lookup that reuses Phase 1's voice-search
engine as a similarity index -- no new infrastructure needed for it.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.database import User, get_db
from app.core.security import get_current_user
from app.core.dependencies import get_voice_search_service
from app.services import srs_service
from app.services.quran_corpus_service import QuranCorpusService
from app.services.voice_search_service import VoiceSearchService

router = APIRouter()

_corpus_service = QuranCorpusService()


class AddCardsRequest(BaseModel):
    surah: int = Field(..., ge=1, le=114)
    ayah_from: int = Field(..., ge=1)
    ayah_to: int = Field(..., ge=1)


class CardResponse(BaseModel):
    surah_number: int
    ayah_number: int
    ease_factor: float
    interval_days: int
    repetitions: int
    due_date: str


class DueCardResponse(CardResponse):
    text_uthmani: str
    translation_en: str


def _to_card_response(card) -> CardResponse:
    return CardResponse(
        surah_number=card.surah_number,
        ayah_number=card.ayah_number,
        ease_factor=card.ease_factor,
        interval_days=card.interval_days,
        repetitions=card.repetitions,
        due_date=card.due_date.isoformat(),
    )


@router.post("/add", response_model=List[CardResponse])
async def add_to_memorization(
    request: AddCardsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add an ayah range to the user's memorization plan. Idempotent:
    ayahs already being tracked keep their existing SM-2 state."""
    if request.ayah_from > request.ayah_to:
        raise HTTPException(status_code=400, detail="ayah_from must be <= ayah_to")

    _corpus_service.load_or_fetch()
    cards = []
    for ayah_number in range(request.ayah_from, request.ayah_to + 1):
        if not _corpus_service.get_ayah(request.surah, ayah_number):
            raise HTTPException(status_code=404, detail=f"Ayah {request.surah}:{ayah_number} not found")
        card = srs_service.get_or_create_card(db, user.id, request.surah, ayah_number)
        cards.append(card)

    return [_to_card_response(c) for c in cards]


@router.get("/due", response_model=List[DueCardResponse])
async def get_due_cards(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cards due for review today, with ayah text joined in."""
    _corpus_service.load_or_fetch()
    cards = srs_service.get_due_cards(db, user.id, limit=limit)

    results = []
    for card in cards:
        ayah = _corpus_service.get_ayah(card.surah_number, card.ayah_number)
        if not ayah:
            continue
        results.append(DueCardResponse(
            **_to_card_response(card).model_dump(),
            text_uthmani=ayah["text_uthmani"],
            translation_en=ayah["translation_en"],
        ))
    return results


class ReviewRequest(BaseModel):
    surah: int = Field(..., ge=1, le=114)
    ayah: int = Field(..., ge=1)
    quality: Optional[int] = Field(default=None, ge=0, le=5)
    mistake_count: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _exactly_one_grading_input(self):
        if (self.quality is None) == (self.mistake_count is None):
            raise ValueError("provide exactly one of quality or mistake_count")
        return self


@router.post("/review", response_model=CardResponse)
async def review_card(
    request: ReviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Grade a card's review, either directly (quality) or derived from a
    recitation-check's mistake_count."""
    card = srs_service.get_card(db, user.id, request.surah, request.ayah)
    if card is None:
        raise HTTPException(
            status_code=404,
            detail="This ayah isn't in your memorization plan yet -- add it via /add first",
        )

    quality = (
        request.quality
        if request.quality is not None
        else srs_service.quality_from_mistake_count(request.mistake_count)
    )
    srs_service.grade_review(card, quality)
    db.commit()
    db.refresh(card)

    return _to_card_response(card)


class SimilarAyah(BaseModel):
    surah_number: int
    ayah_number: int
    key: str
    text_uthmani: str
    translation_en: str


class SimilarAyahsResponse(BaseModel):
    surah: int
    ayah: int
    similar: List[SimilarAyah]


@router.get("/similar/{surah}/{ayah}", response_model=SimilarAyahsResponse)
async def get_similar_ayahs(
    surah: int,
    ayah: int,
    limit: int = 5,
    voice_search_service: VoiceSearchService = Depends(get_voice_search_service),
):
    """Mutashabihat lookup: ayahs that sound/look similar to this one, so a
    user can drill the specific confusion rather than just being told
    'wrong'. Reuses Phase 1's voice-search engine with the ayah's own text
    as the query -- no separate similarity index needed."""
    _corpus_service.load_or_fetch()
    source_ayah = _corpus_service.get_ayah(surah, ayah)
    if not source_ayah:
        raise HTTPException(status_code=404, detail=f"Ayah {surah}:{ayah} not found")

    located = await voice_search_service.search(query=source_ayah["text_simple"], top_k=limit + 1)
    similar = [
        SimilarAyah(
            surah_number=r["surah_number"], ayah_number=r["ayah_number"],
            key=r["key"], text_uthmani=r["text_uthmani"], translation_en=r["translation_en"],
        )
        for r in located.get("results", [])
        if r["key"] != source_ayah["key"]
    ][:limit]

    return SimilarAyahsResponse(surah=surah, ayah=ayah, similar=similar)
