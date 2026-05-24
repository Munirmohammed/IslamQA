"""
Islamic utility tool endpoints — prayer times, qibla, hijri converter, zakat.
"""

from datetime import date as _date
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.islamic_tools import (
    calc_prayer_times,
    calc_qibla,
    calc_zakat,
    gregorian_from_hijri,
    hijri_from_gregorian,
)

router = APIRouter()


class PrayerTimesRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    date: Optional[_date] = Field(default=None)
    timezone_offset: float = Field(default=0.0, ge=-12, le=14)
    method: str = Field(default="MWL")
    asr_method: str = Field(default="shafi")


class CoordsRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class HijriFromGregorianRequest(BaseModel):
    date: Optional[_date] = Field(default=None)


class HijriToGregorianRequest(BaseModel):
    year: int = Field(..., ge=1, le=2000)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=30)


class ZakatRequest(BaseModel):
    cash: float = Field(default=0.0, ge=0)
    gold_grams: float = Field(default=0.0, ge=0)
    silver_grams: float = Field(default=0.0, ge=0)
    business_assets: float = Field(default=0.0, ge=0)
    debts: float = Field(default=0.0, ge=0)
    gold_price_per_gram: float = Field(default=65.0, gt=0)
    silver_price_per_gram: float = Field(default=0.85, gt=0)


@router.post("/prayer-times")
def prayer_times(req: PrayerTimesRequest) -> Dict[str, Any]:
    return calc_prayer_times(
        lat=req.lat,
        lon=req.lon,
        g_date=req.date,
        timezone_offset=req.timezone_offset,
        method=req.method,
        asr_method=req.asr_method,
    )


@router.post("/qibla")
def qibla(req: CoordsRequest) -> Dict[str, Any]:
    return calc_qibla(req.lat, req.lon)


@router.post("/hijri/from-gregorian")
def hijri_from(req: HijriFromGregorianRequest) -> Dict[str, Any]:
    return hijri_from_gregorian(req.date)


@router.post("/hijri/to-gregorian")
def hijri_to(req: HijriToGregorianRequest) -> Dict[str, Any]:
    try:
        return gregorian_from_hijri(req.year, req.month, req.day)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Hijri date: {e}")


@router.post("/zakat")
def zakat(req: ZakatRequest) -> Dict[str, Any]:
    return calc_zakat(
        cash=req.cash,
        gold_grams=req.gold_grams,
        silver_grams=req.silver_grams,
        business_assets=req.business_assets,
        debts=req.debts,
        gold_price_per_gram=req.gold_price_per_gram,
        silver_price_per_gram=req.silver_price_per_gram,
    )
