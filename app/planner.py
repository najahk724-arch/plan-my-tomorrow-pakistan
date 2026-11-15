"""Transparent activity ranking, plus app-defined forecast concern indicators.

These scores are preferences and prototype heuristics, not calibrated safety ratings,
meteorological severe-weather warnings, or medical guidance.
"""
from app.schemas import PlanRequest

PMD_URL = "https://weather.gov.pk/"
STORM_CODES = {95, 96, 99}  # WMO thunderstorm descriptions.


def concerns(hour: dict) -> list[str]:
    notes = []
    if int(hour["weather_code"]) in STORM_CODES:
        notes.append("Forecast thunderstorm conditions")
    if float(hour["precipitation"]) >= 8.0:
        notes.append("Forecast intense hourly precipitation")
    if float(hour["wind_gusts_10m"]) >= 55:
        notes.append("Forecast strong wind gusts")
    if float(hour["apparent_temperature"]) >= 40:
        notes.append("Forecast very high feels-like temperature")
    if float(hour["apparent_temperature"]) <= -20:
        notes.append("Forecast extreme cold feels-like temperature")
    aqi = hour.get("us_aqi")
    if aqi is not None and aqi >= 151:
        notes.append("Modeled air quality in the unhealthy US AQI category")
    return notes


def wear_and_carry(hours: list[dict]) -> list[str]:
    low = min(float(x["apparent_temperature"]) for x in hours)
    high = max(float(x["apparent_temperature"]) for x in hours)
    peak_rain = max(float(x["precipitation_probability"]) for x in hours)
    peak_uv = max(float(x["uv_index"]) for x in hours)
    clothing = []
    if low < 15:
        clothing.append("Consider a warm removable layer.")
    elif high >= 30:
        clothing.append("Consider lightweight, breathable clothing.")
    else:
        clothing.append("Wear comfortable clothing suited to your activity.")
    clothing.append("Carry drinking water.")
    if peak_rain >= 30:
        clothing.append("Consider a lightweight rain jacket.")
    if peak_uv >= 3:
        clothing.append("Consider sun protection (hat, sunscreen).")
    return clothing


def make_plan(request: PlanRequest, forecast: dict) -> dict:
    rows = forecast["hours"]
    if len(rows) != 24:
        raise ValueError("Tomorrow requires 24 hourly weather rows.")
    candidates = []
    excluded = []
    for start in range(request.earliest_start_hour,
                       request.latest_finish_hour - request.duration_hours + 1):
        segment = rows[start:start + request.duration_hours]
        if len(segment) != request.duration_hours:
            continue
        flags = sorted({note for hour in segment for note in concerns(hour)})
        if request.daylight_only and any(not hour["is_day"] for hour in segment):
            flags.append("Selected time is not entirely daylight")
        if flags:
            excluded.append({"start_hour": start, "reasons": flags})
            continue
        feels = [float(h["apparent_temperature"]) for h in segment]
        rain = max(float(h["precipitation_probability"]) for h in segment)
        wind = max(float(h["wind_speed_10m"]) for h in segment)
        gusts = max(float(h["wind_gusts_10m"]) for h in segment)
        uv = max(float(h["uv_index"]) for h in segment)
        aqi = max((float(h["us_aqi"]) for h in segment if h.get("us_aqi") is not None), default=None)
        temp_excursion = max(max(request.comfort_min_c - min(feels), 0),
                             max(max(feels) - request.comfort_max_c, 0))
        # 5-point rain bands avoid ranking 1% over 2% as a meaningful difference.
        rain_band = int(rain // 5)
        score = 100.0 - min(40.0, 4 * temp_excursion) - rain_band * 1.4
        score -= max(0.0, gusts - 25) * 0.35
        score -= max(0.0, wind - 18) * 0.35
        score -= max(0.0, uv - 5) * 1.5
        if aqi is not None and aqi >= 101:
            score -= 15  # AQI-sensitive caution, even outside 'unhealthy' category.
        score = round(max(0, min(100, score)), 1)
        candidates.append({
            "start_hour": start, "finish_hour": start + request.duration_hours,
            "start": rows[start]["time"], "finish": f"{start + request.duration_hours:02d}:00",
            "score": score, "score_meaning": "Personal preference score only",
            "feels_like_range_c": [round(min(feels), 1), round(max(feels), 1)],
            "peak_rain_probability_pct": rain,
            "hourly_rain": [
                {
                    "start_hour": start + i,
                    "finish_hour": start + i + 1,
                    "chance_pct": round(float(h["precipitation_probability"])),
                    "precipitation_mm": round(float(h["precipitation"]), 1),
                }
                for i, h in enumerate(segment)
            ],
            "peak_wind_kmh": wind,

            "peak_gust_kmh": gusts, "peak_uv": uv, "peak_modeled_us_aqi": aqi,
            "comfort_excursion_c": round(temp_excursion, 1),
            "wear_and_carry": wear_and_carry(segment),
        })
    candidates.sort(key=lambda x: (-x["score"], x["start_hour"]))
    return {
        "location": request.location.model_dump(), "date": forecast["date"],
        "activity": request.activity,
        "best": candidates[0] if candidates else None,
        "backup": candidates[1] if len(candidates) > 1 else None,
        "ranked_windows": candidates,
        "excluded_windows": excluded,
        "air_quality_status": forecast["air_quality_status"],
        "weather_data_fetched_at": forecast["fetched_at"],
        "weather_source": "Open-Meteo modeled forecast (not live station observation)",
        "air_source": "Open-Meteo CAMS model forecast" if forecast["air_quality_status"] == "model_forecast" else None,
        "forecast_based_alert_status": "App-defined indicators, not official warnings",
        "official_warning_status": "Not automatically integrated or verified",
        "official_weather_updates_url": PMD_URL,
        "limitations": [
            "Hourly values are forecasts, not guarantees for every minute.",
            "Heuristic scores and exclusions are not validated safety assessments.",
            "No official warning is inferred from a weather model.",
        ] + (["Modeled air-quality forecast unavailable; ranking excludes AQI."]
             if forecast["air_quality_status"] != "model_forecast" else []),
    }
