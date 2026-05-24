"""
Adhkar / duas endpoints — browse the dua collection by occasion.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "daily" / "dua_pool.json"
with open(_DATA, "r", encoding="utf-8") as _f:
    _DUAS: List[Dict[str, Any]] = json.load(_f)


@router.get("/")
def list_duas(
    occasion: Optional[str] = Query(default=None, description="Substring match on occasion"),
) -> List[Dict[str, Any]]:
    if occasion:
        needle = occasion.lower()
        return [d for d in _DUAS if needle in d["occasion"].lower()]
    return _DUAS


@router.get("/occasions")
def list_occasions() -> List[Dict[str, Any]]:
    counts = Counter(d["occasion"] for d in _DUAS)
    return [{"occasion": name, "count": n} for name, n in sorted(counts.items())]


@router.get("/{dua_id}")
def get_dua(dua_id: int) -> Dict[str, Any]:
    for d in _DUAS:
        if d["id"] == dua_id:
            return d
    raise HTTPException(status_code=404, detail=f"Dua {dua_id} not found")
