"""
99 Names of Allah (Asma ul-Husna) endpoints.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

router = APIRouter()

_DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "names" / "asma_ul_husna.json"
with open(_DATA, "r", encoding="utf-8") as _f:
    _NAMES: List[Dict[str, Any]] = json.load(_f)


@router.get("/")
def list_names() -> List[Dict[str, Any]]:
    return _NAMES


@router.get("/{number}")
def get_name(number: int) -> Dict[str, Any]:
    if number < 1 or number > 99:
        raise HTTPException(status_code=404, detail="Name number must be between 1 and 99")
    return _NAMES[number - 1]
