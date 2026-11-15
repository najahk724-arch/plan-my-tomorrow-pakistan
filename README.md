# Plan My Tomorrow — Pakistan 🌤️🇵🇰

**Veritas AI International High School Hackathon 2026 | AI + Climate**

A browser-based prototype that helps people in Pakistan plan outdoor activities for tomorrow using forecast weather, modeled air quality, and an **experimental machine-learning forecast of next-day PM2.5 pollution**.

The website is served by a **FastAPI Python backend**. This GitHub repository contains the source code; it is **not a hosted live website**.

## Features

- Browse places by **province/region → district → locality** using a GeoNames-derived Pakistan catalogue.
- Choose from **running, cycling, picnic, driving, hiking, outdoor sports, or camping**.
- Select a start and finish hour on an interactive timeline (up to 24 hours; times shown in 24-hour format).
- Set preferred minimum and maximum feels-like temperatures.
- See hourly forecast-based activity matching, temperature, modeled US AQI, wind and hourly rain probabilities.
- See forecast-based concern indicators, what-to-wear/bring suggestions, and an experimental daily PM2.5 outlook.
- A Random Forest model predicts **tomorrow's daily mean PM2.5** from prior modeled pollution, seasonality and geographic features.

**Important:** Activity match scores are **preferences, not safety ratings**. The PM2.5 estimate is a *daily pollution prediction*, not a live sensor reading or an hourly AQI prediction.

## Run the website locally

Requirements: **Python 3.10+**, internet access for the Open-Meteo APIs.

From the repository's top-level folder:

```bash
python -m venv .venv
```

Activate the virtual environment:

- **Windows PowerShell:** `.venv\Scripts\Activate.ps1`
- **macOS/Linux:** `source .venv/bin/activate`

Install dependencies and launch:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/** in a browser.

The interactive API reference is at **http://127.0.0.1:8000/docs** and the health check is at `GET /health`. The website needs the Python server running; opening the HTML file alone does not provide the live API.

### Example API request

`POST /plan` with JSON:

```json
{
  "location": {
    "name": "Lahore",
    "latitude": 31.55,
    "longitude": 74.35,
    "country_code": "PK",
    "admin1": "Punjab"
  },
  "activity": "run",
  "earliest_start_hour": 18,
  "latest_finish_hour": 21,
  "duration_hours": 3,
  "comfort_min_c": 18,
  "comfort_max_c": 26,
  "avoid_rain": false,
  "daylight_only": false
}
```

A start of 18 and finish of 21 specify a **6 PM–9 PM** window; the frontend shows times in **24-hour format**. If the entire chosen period has a flagged condition, the planner may return no suitable window.

### Tests

```bash
python -m pip install pytest pytest-asyncio
python -m pytest -q
```

The included tests mock the weather service and exercise backend logic; they are not a substitute for a live network test. You can inspect the app's responses using `/docs`.

## How the AI was evaluated

The experimental **Random Forest regressor** uses modeled daily PM2.5 data collected from Open-Meteo for 12 Pakistani cities. The training setup used nine cities and held out Karachi, Quetta and Skardu to examine geographic generalization. The saved model is `pakistan_ai_candidate.joblib`.

The baseline was **persistence**: reuse the most recent complete day's average PM2.5 as the forecast. Error was measured as mean absolute error (**MAE**, µg/m³; **lower is better**).

| Evaluation group | Samples | Persistence MAE | Random Forest MAE | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Validation, training cities | 495 | 8.79 | **8.03** | AI better |
| Final held-out dates, training cities | 504 | 12.27 | **11.09** | AI better |
| Final held-out cities (Karachi, Quetta, Skardu) | 168 | **5.83** | 5.98 | AI slightly worse |
| Fresh tests in four additional cities | 224 | 12.76 | **12.06** | AI better overall, but mixed by city |

These figures are calculated from `data/pakistan_multicity_evaluation.csv` and `data/fresh_city_test_results.csv`. **The model does not outperform the baseline in every city or every split.** Do not interpret these test results as real-time accuracy guarantees.

Dataset and saved outputs:

- `data/pakistan_multicity_pm25.csv`: modeled daily city PM2.5 observations
- `data/pakistan_multicity_evaluation.csv`: validation and final held-out comparisons
- `data/fresh_city_test_results.csv`: tests on Abbottabad, Bahawalpur, Gwadar and Sialkot
- `data/pk_places.json.gz`: compressed location catalogue
- `pakistan_ai_candidate.joblib`: trained multi-city model

The evaluation data and trained model are included. **The original multi-city model-training scripts are not yet included in this repository**, so retraining the saved model from scratch is not currently fully reproducible from GitHub alone.

## Technical approach

1. `app/forecast.py` requests tomorrow's hourly weather and air-quality data from Open-Meteo.
2. `app/planner.py` applies transparent forecast heuristics, checks candidate windows, and calculates a preference match score.
3. `app/pakistan_pm25_ai.py` uses the saved Random Forest model and recent *completed* daily modeled PM2.5 values for an experimental daily forecast.
4. `app/city_catalog.py` supplies the province/district/place dropdowns.
5. `static/index.html` renders the interface and sends requests to `POST /plan`.

The **weather-based planner is deterministic**; the **PM2.5 prediction is machine learning**. They are separate components. The historical pollution data and forecast inputs come from *models*, not independent ground-truth air-monitor stations.

## Limitations and responsible use

- Weather and air-quality data are modeled forecasts, **not guaranteed local observations**.
- Air-quality models can represent wide geographic cells and may miss neighborhood-level differences.
- Automated official Pakistan Meteorological Department warnings, live traffic/road conditions and trail risks are **not integrated**.
- The app uses experimental, app-defined thresholds to exclude some concerning conditions, but even an accepted time is **not certified safe**.
- Extreme weather or pollution should be checked against official guidance. See [Pakistan Meteorological Department](https://weather.gov.pk/) and [AirNow AQI basics](https://www.airnow.gov/aqi/aqi-basics/).
- The 24-hour planning interface considers only **tomorrow's calendar day**; it is not an overnight/multi-day itinerary planner.
- The optional Gemini text parser at `POST /parse-preferences` requires a **server-side** `GEMINI_API_KEY` and `google-genai`; the primary website does not need that feature.

## Data sources and attribution

- [Open-Meteo Weather API](https://open-meteo.com/en/docs)
- [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api)
- [GeoNames](https://www.geonames.org/) location data, **CC BY 4.0**
- Additional location searches may reference © OpenStreetMap contributors.
- Project design and implementation used AI-assisted development. Experimental results and limitations are documented above.

This repository is an **educational hackathon prototype**, not an official weather, medical or air-quality advisory service.
