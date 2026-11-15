
"""FastAPI routes for Plan My Tomorrow — Pakistan."""

from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from app.forecast import (
    DataUnavailable,
    fetch_tomorrow,
    search_pakistan,
)
from app.schemas import PlanRequest, PreferencesText
from app.planner import make_plan
from app.ai import parse_preferences

# Original Lahore AI — kept as a fallback
from app.pm25_ai import predict_lahore_pm25

# Experimental Pakistan-wide AI
from app.pakistan_pm25_ai import predict_pakistan_pm25

# Pakistan province, district and locality catalogue
from app.city_catalog import router as catalog_router


# --------------------------------------------------
# APPLICATION SETUP
# --------------------------------------------------

app = FastAPI(
    title="Plan My Tomorrow — Pakistan",
    version="0.2.0",
)

app.include_router(catalog_router)


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "phase": "multi-city-ai-prototype",
    }


# --------------------------------------------------
# ORIGINAL LOCATION SEARCH
# --------------------------------------------------

@app.get("/locations")
async def locations(
    q: str = Query(min_length=2, max_length=100)
):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            return {
                "matches": await search_pakistan(q, client)
            }

    except DataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# --------------------------------------------------
# MAIN ACTIVITY PLANNER + AI
# --------------------------------------------------

@app.post("/plan")
async def plan(req: PlanRequest):
    try:
        async with httpx.AsyncClient(timeout=30) as client:

            # Step 1: Get weather and air-quality forecasts
            forecast = await fetch_tomorrow(
                req.location.latitude,
                req.location.longitude,
                client,
            )

            # Step 2: Generate recommended activity times
            result = make_plan(req, forecast)

            # Step 3: Check whether location is near Lahore
            is_lahore = (
                abs(req.location.latitude - 31.55) < 0.15
                and abs(req.location.longitude - 74.35) < 0.15
            )

            # Step 4: Try experimental Pakistan-wide AI
            try:
                result["ai_pollution_outlook"] = (
                    await predict_pakistan_pm25(
                        client,
                        req.location.latitude,
                        req.location.longitude,
                    )
                )

            except Exception as exc:
                print(
                    "MULTI-CITY AI ERROR:",
                    repr(exc),
                )

                # Step 5: Use original Lahore AI as fallback
                if is_lahore:
                    try:
                        result["ai_pollution_outlook"] = (
                            await predict_lahore_pm25(client)
                        )

                    except Exception as fallback_exc:
                        print(
                            "LAHORE AI ERROR:",
                            repr(fallback_exc),
                        )

                        result["ai_pollution_outlook"] = {
                            "status": "unavailable",
                            "message": (
                                "AI pollution outlook "
                                "is temporarily unavailable."
                            ),
                        }

                else:
                    result["ai_pollution_outlook"] = {
                        "status": "unavailable",
                        "message": (
                            "Experimental AI pollution prediction "
                            "is unavailable for this location."
                        ),
                    }

            # Return complete activity plan and AI outlook
            return result

    except DataUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# --------------------------------------------------
# NATURAL-LANGUAGE PREFERENCE PARSING
# Experimental feature
# --------------------------------------------------

@app.post("/parse-preferences")
def parse_text(req: PreferencesText):
    try:
        return parse_preferences(req.text)

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


# --------------------------------------------------
# ORIGINAL LAHORE AI TEST
# --------------------------------------------------

@app.get("/ai-test")
async def ai_test():
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            return await predict_lahore_pm25(client)

    except Exception as exc:
        print(
            "LAHORE AI TEST ERROR:",
            repr(exc),
        )

        return {
            "status": "unavailable",
            "message": (
                "Check the VS Code terminal for the error."
            ),
        }


# --------------------------------------------------
# NEW PAKISTAN-WIDE AI TEST
# --------------------------------------------------

@app.get("/ai-test-pakistan")
async def ai_test_pakistan(
    latitude: float = Query(
        default=31.55,
        ge=-90,
        le=90,
    ),
    longitude: float = Query(
        default=74.35,
        ge=-180,
        le=180,
    ),
):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            result = await predict_pakistan_pm25(
                client,
                latitude,
                longitude,
            )

            return result

    except Exception as exc:
        print(
            "PAKISTAN AI TEST ERROR:",
            repr(exc),
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Experimental Pakistan AI is unavailable. "
                "Check the server terminal."
            ),
        ) from exc


# --------------------------------------------------
# WEBSITE HOMEPAGE
# --------------------------------------------------

@app.get("/")
def homepage():
    website = (
        Path(__file__).resolve().parent.parent
        / "static"
        / "index.html"
    )

    return FileResponse(website)


# --------------------------------------------------
# PHOTON LOCATION SEARCH
# Kept for compatibility with original search
# --------------------------------------------------

@app.get("/places")
async def places(
    q: str = Query(min_length=2, max_length=100)
):
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(
                "https://photon.komoot.io/api",
                params={
                    "q": q,
                    "limit": 25,
                    "countrycode": "PK",
                    "lang": "en",
                },
                headers={
                    "User-Agent": (
                        "PlanMyTomorrowPakistan/0.1"
                    )
                },
            )

            response.raise_for_status()

            matches = []
            seen = set()

            for feature in response.json().get(
                "features", []
            ):
                props = feature.get(
                    "properties", {}
                )

                coords = feature.get(
                    "geometry", {}
                ).get("coordinates", [])

                if (
                    props.get("countrycode", "").upper()
                    != "PK"
                ):
                    continue

                if (
                    not props.get("name")
                    or len(coords) < 2
                ):
                    continue

                name = props["name"]

                area = [
                    value
                    for value in [
                        props.get("city"),
                        props.get("state"),
                    ]
                    if value and value != name
                ]

                key = (
                    name,
                    round(float(coords[1]), 5),
                    round(float(coords[0]), 5),
                )

                if key in seen:
                    continue

                seen.add(key)

                matches.append({
                    "name": name,
                    "latitude": float(coords[1]),
                    "longitude": float(coords[0]),
                    "country_code": "PK",
                    "admin1": (
                        ", ".join(area)
                        or "Pakistan"
                    ),
                })

            if matches:
                return {
                    "matches": matches
                }

        except (
            httpx.HTTPError,
            ValueError,
            KeyError,
        ):
            pass

        # Fallback to original location search
        try:
            return {
                "matches": await search_pakistan(
                    q,
                    client,
                )
            }

        except DataUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail=str(exc),
            ) from exc
