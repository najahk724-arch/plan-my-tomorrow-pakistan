"""Real forecast and modeled air quality data; never fabricate a fallback forecast."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import asyncio
import httpx

PK_TZ = ZoneInfo("Asia/Karachi")
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
GEOCODE_API = "https://geocoding-api.open-meteo.com/v1/search"
AIR_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
HOURLY_WEATHER = [
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "precipitation_probability", "precipitation", "wind_speed_10m",
    "wind_gusts_10m", "uv_index", "weather_code", "is_day",
]


class DataUnavailable(RuntimeError):
    pass


async def get_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    for attempt in range(3):
        try:
            response = await client.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("error"):
                raise DataUnavailable("Weather provider returned invalid data.")
            return data
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt == 2:
                raise DataUnavailable("Weather provider is temporarily unreachable.") from exc
            await asyncio.sleep(0.2 * (attempt + 1))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500 and attempt < 2:
                await asyncio.sleep(0.2 * (attempt + 1))
                continue
            raise DataUnavailable(f"Weather provider HTTP {exc.response.status_code}.") from exc
    raise DataUnavailable("Weather request did not succeed.")


async def search_pakistan(query: str, client: httpx.AsyncClient) -> list[dict]:
    payload = await get_json(client, GEOCODE_API, {
        "name": query, "count": 25, "language": "en", "countryCode": "PK",
    })
    return [{
        "name": place["name"], "latitude": place["latitude"],
        "longitude": place["longitude"], "country_code": "PK",
        "admin1": place.get("admin1"), "admin2": place.get("admin2"),
    } for place in payload.get("results", []) if place.get("country_code") == "PK"]


def _hourly_records(payload: dict, fields: list[str], date: str, *, required: bool) -> list[dict]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if len(times) != 24 or len(set(times)) != 24 or any(not t.startswith(date + "T") for t in times):
        if required:
            raise DataUnavailable("Provider did not return 24 unique hourly timestamps for tomorrow.")
        return []
    if any(len(hourly.get(f, [])) != 24 for f in fields):
        if required:
            raise DataUnavailable("Provider omitted required hourly forecast fields.")
        return []
    records = [{"time": time, **{f: hourly[f][i] for f in fields}}
               for i, time in enumerate(times)]
    if required and any(any(row[f] is None for f in fields) for row in records):
        raise DataUnavailable("Required weather values are missing; unable to rank times.")
    return records


async def fetch_tomorrow(latitude: float, longitude: float, client: httpx.AsyncClient) -> dict:
    date = (datetime.now(PK_TZ).date() + timedelta(days=1)).isoformat()
    common = {
        "latitude": latitude, "longitude": longitude,
        "timezone": "Asia/Karachi", "start_date": date, "end_date": date,
    }
    weather_payload = await get_json(client, FORECAST_API, {
        **common, "hourly": ",".join(HOURLY_WEATHER),
        "current": "temperature_2m,weather_code,wind_speed_10m",
    })
    weather = _hourly_records(weather_payload, HOURLY_WEATHER, date, required=True)
    air = None
    air_status = "unavailable"
    try:
        air_payload = await get_json(client, AIR_API, {
            **common, "hourly": "us_aqi,pm2_5",
        })
        air_records = _hourly_records(air_payload, ["us_aqi", "pm2_5"], date, required=False)
        if air_records and all(row["us_aqi"] is not None for row in air_records):
            air = air_records
            air_status = "model_forecast"
    except DataUnavailable:
        pass  # Explicitly mark AQI unavailable; no fake replacement.
    if air:
        for weather_hour, air_hour in zip(weather, air):
            if weather_hour["time"] != air_hour["time"]:
                raise DataUnavailable("Weather and air-quality timestamps disagree.")
            weather_hour["us_aqi"] = air_hour["us_aqi"]
            weather_hour["pm2_5"] = air_hour["pm2_5"]
    else:
        for row in weather:
            row["us_aqi"] = None
            row["pm2_5"] = None
    return {
        "date": date, "hours": weather,
        "air_quality_status": air_status,
        "current_model_conditions": weather_payload.get("current"),
        "fetched_at": datetime.now(PK_TZ).isoformat(),
    }
