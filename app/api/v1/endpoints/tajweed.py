"""
Tajweed Endpoints
Rule-based tajweed annotation for any ayah -- which letters carry which
rule (qalqalah, madd, idgham, ...), for a frontend to color/highlight.
Public: reference content, not personal state (same reasoning as Phase 1's
voice-search and Phase 4's mutashabihat lookup).
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.tajweed_service import TAJWEED_RULE_INFO, tajweed_service

router = APIRouter()


class TajweedRule(BaseModel):
    rule: str
    name: str
    description: str | None
    start: int
    end: int
    text: str


class TajweedAyahResponse(BaseModel):
    surah: int
    ayah: int
    plain_text: str
    rules: List[TajweedRule]


class TajweedRuleInfo(BaseModel):
    rule: str
    name: str
    description: str


@router.get("/rules", response_model=List[TajweedRuleInfo])
async def get_tajweed_rule_legend():
    """The full tajweed rule legend (color key), for a frontend to fetch
    once and cache."""
    return [
        TajweedRuleInfo(rule=code, name=info["name"], description=info["description"])
        for code, info in TAJWEED_RULE_INFO.items()
    ]


@router.get("/{surah}/{ayah}", response_model=TajweedAyahResponse)
async def get_ayah_tajweed(surah: int, ayah: int):
    """That ayah's text with tajweed rule spans."""
    annotated = tajweed_service.get_ayah_tajweed(surah, ayah)
    if not annotated:
        raise HTTPException(status_code=404, detail=f"Ayah {surah}:{ayah} not found")

    return TajweedAyahResponse(
        surah=surah,
        ayah=ayah,
        plain_text=annotated["plain_text"],
        rules=[TajweedRule(**r) for r in annotated["rules"]],
    )
