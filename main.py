"""FastAPI routes for a local / hosted server. No precise GPS permission required."""
from fastapi import FastAPI, HTTPException, Query
import httpx
from app.forecast import DataUnavailable, fetch_tomorrow, search_pakistan
from app.schemas import PlanRequest, PreferencesText
from app.planner import make_plan
from app.ai import parse_preferences

app = FastAPI(title="Plan My Tomorrow — Pakistan", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "phase": "backend-prototype"}


@app.get("/locations")
async def locations(q: str = Query(min_length=2, max_length=100)):
    try:
        async with httpx.AsyncClient() as client:
            return {"matches": await search_pakistan(q, client)}
    except DataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/plan")
async def plan(req: PlanRequest):
    try:
        async with httpx.AsyncClient() as client:
            forecast = await fetch_tomorrow(req.location.latitude,
                                            req.location.longitude, client)
        return make_plan(req, forecast)
    except DataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/parse-preferences")
def parse_text(req: PreferencesText):
    try:
        return parse_preferences(req.text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
