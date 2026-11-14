# Plan My Tomorrow — Pakistan (Backend v0.1)

A small, independent backend prototype based on the existing Google Colab notebook. It does NOT require Google Colab; it does require a network connection to the free Open-Meteo forecast and air-quality APIs to serve live requests.

## What it does

- Search geocoded Pakistan place names (`GET /locations?q=Lahore`)
- Fetch *tomorrow's* hourly forecast in Pakistan time (temperature, feels-like, rain, wind, gusts, UV, weather code, day/night)
- Attempt a separate modeled AQI/PM2.5 forecast; if unavailable, disclose this rather than invent a value
- Rank outdoor activity windows by individual comfort preferences, excluding forecast thunderstorm/strong wind/intense rain/very high heat/unhealthy AQI windows (all app-defined heuristic rules)
- Show clothing/items, backup slot and evidence behind each recommendation
- Optional `POST /parse-preferences` with Gemini for natural-language input (requires a **server-side** secret)

## Start on your own computer (VS Code terminal)

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Then visit `http://127.0.0.1:8000/docs` to try endpoints interactively.

1. Open `GET /locations`, click **Try it out**, enter `Lahore`, execute. Copy one of the returned matches' `name`, `latitude`, `longitude`, `country_code` and `admin1`.
2. Open `POST /plan`, click **Try it out**, and use those values:

```json
{
  "location": {
    "name": "Lahore", "latitude": 31.558, "longitude": 74.351,
    "country_code": "PK", "admin1": "Punjab"
  },
  "activity": "walk", "earliest_start_hour": 16,
  "latest_finish_hour": 20, "duration_hours": 1,
  "comfort_min_c": 18, "comfort_max_c": 26,
  "avoid_rain": true, "daylight_only": false
}
```

## Optional pretrained Gemini

```bash
pip install "google-genai>=2.12,<3"
# Use a server-side environment variable called GEMINI_API_KEY.
```

**Never put your key in the browser, repository, screenshots or this chat.** You can leave Gemini out initially: the manual structured `POST /plan` request still works. The LLM extracts preferences only; the deterministic planner must evaluate real weather data independently.

## Automated tests (work offline)

```bash
pip install pytest
python -m pytest -q
```

## Important distinctions / limitations

- Data is retrieved fresh on each `/plan` request, not streamed minute-by-minute; Open-Meteo is principally a forecast service, **not an official severe-weather warning feed**.
- [Pakistan Meteorological Department](https://weather.gov.pk/) is linked for checking **official warnings**. We have **not** implemented an automated, verified official warning parser or API. Do not label weather-derived flags as official alerts.
- Air-quality forecasts over Pakistan use broad regional model grids. They are **not street-level pollution measurements**.
- The app's weather hazard indicators (thunderstorm codes, 8 mm/hour rainfall, 55 km/h gust, feels-like >=40°C, US AQI >=151) are **prototype heuristics**, not safety standards, validated warning thresholds or an official risk determination. A seemingly suitable window is not a guarantee of safety.
- Location search is not a complete registry of every Pakistani settlement. Coordinates are broadly validated to the region but not precise border verification. A map-based point picker may be added without GPS.
- Some networks (including prior Colab runs) blocked backend weather requests; network errors return HTTP 503, not fake sample data. Offline tests cover code paths only.
- Scores measure user preference only, not scientific weather forecasting skill. The AI component should be evaluated against an explicit baseline.

## References

- https://open-meteo.com/en/docs
- https://open-meteo.com/en/docs/air-quality-api
- https://open-meteo.com/en/docs/geocoding-api
- https://ai.google.dev/gemini-api/docs/structured-output
- https://weather.gov.pk/
