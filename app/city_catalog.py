
import gzip
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/catalog")

DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "data" / "pk_places.json.gz"
)

@lru_cache(maxsize=1)
def load_catalog():
    with gzip.open(DATA_FILE, "rt", encoding="utf-8") as f:
        return json.load(f)

@router.get("/provinces")
def provinces():
    data = load_catalog()
    active = {p[3] for p in data["places"]}
    return sorted(
        [
            {"code": code, "name": data["regions"].get(code, code)}
            for code in active
        ],
        key=lambda p: p["name"]
    )

@router.get("/districts")
def district_options(province: str):
    data = load_catalog()
    return sorted({
        p[4]
        for p in data["places"]
        if p[3] == province
    })

@router.get("/places")
def place_options(province: str, district: str):
    data = load_catalog()

    matches = [
        p for p in data["places"]
        if p[3] == province and p[4] == district
    ]

    matches.sort(key=lambda p: (-p[5], p[0].casefold()))

    return {
        "matches": [
            {
                "name": p[0],
                "latitude": p[1],
                "longitude": p[2],
                "country_code": "PK",
                "admin1": data["regions"].get(province, province),
                "district": p[4]
            }
            for p in matches
        ]
    }
