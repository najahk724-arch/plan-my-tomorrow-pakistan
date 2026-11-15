from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
import httpx
from app.schemas import Location, PlanRequest
from app.planner import make_plan
from app.forecast import search_pakistan, fetch_tomorrow, DataUnavailable


def request(**kwargs):
    kwargs.setdefault("activity", "run")
    return PlanRequest(location=Location(name="Lahore", latitude=31.558,
                                         longitude=74.351), **kwargs)


def fixture(aqi=55, gust=8, code=0, rain_prob=2, rainfall=0.0, feels=24):
    date = (datetime.now(ZoneInfo("Asia/Karachi")).date() + timedelta(days=1)).isoformat()
    rows = []
    for hour in range(24):
        rows.append({"time": f"{date}T{hour:02d}:00", "apparent_temperature": feels,
                     "temperature_2m": 25, "relative_humidity_2m": 50,
                     "precipitation_probability": rain_prob, "precipitation": rainfall,
                     "wind_speed_10m": 6.0, "wind_gusts_10m": gust,
                     "uv_index": 2.0, "weather_code": code,
                     "is_day": int(6 <= hour < 18), "us_aqi": aqi, "pm2_5": 14})
    return {"date": date, "hours": rows, "air_quality_status": "model_forecast" if aqi is not None else "unavailable",
            "fetched_at": f"{date}T00:00:00+05:00"}


def test_valid_run_returns_time_and_backup():
    result = make_plan(request(earliest_start_hour=16, latest_finish_hour=20), fixture())
    assert result["best"]["start_hour"] == 16
    assert result["backup"]["start_hour"] == 17
    assert result["best"]["peak_rain_probability_pct"] == 2
    assert result["official_warning_status"] == "Not automatically integrated or verified"


def test_no_suitable_windows_for_thunderstorm():
    result = make_plan(request(earliest_start_hour=16, latest_finish_hour=19), fixture(code=95))
    assert result["best"] is None
    assert all("thunderstorm" in x["reasons"][0].lower() for x in result["excluded_windows"])


def test_no_suitable_windows_for_unhealthy_aqi():
    result = make_plan(request(earliest_start_hour=16, latest_finish_hour=20), fixture(aqi=174))
    assert result["best"] is None
    assert any("unhealthy" in x["reasons"][0] for x in result["excluded_windows"])


def test_no_fabricated_air_quality():
    result = make_plan(request(earliest_start_hour=16, latest_finish_hour=20), fixture(aqi=None))
    assert result["best"]["peak_modeled_us_aqi"] is None
    assert "Modelled air-quality" not in result["official_warning_status"]
    assert any("air-quality" in message.lower() for message in result["limitations"])


def test_daylight_only_rejects_night():
    result = make_plan(request(earliest_start_hour=18, latest_finish_hour=20, daylight_only=True), fixture())
    assert result["best"] is None


def test_invalid_activity_window():
    with pytest.raises(ValueError):
        request(earliest_start_hour=20, latest_finish_hour=21, duration_hours=2)


@pytest.mark.asyncio
async def test_mocked_weather_and_pakistan_search():
    date = (datetime.now(ZoneInfo("Asia/Karachi")).date() + timedelta(days=1)).isoformat()
    hourly = [f"{date}T{x:02d}:00" for x in range(24)]
    weather = {"hourly": {"time": hourly,
        "temperature_2m": [24.0]*24, "apparent_temperature": [26.0]*24,
        "relative_humidity_2m": [55]*24, "precipitation_probability": [4]*24,
        "precipitation": [0.0]*24, "wind_speed_10m": [8.0]*24,
        "wind_gusts_10m": [12.0]*24, "uv_index": [0.0]*24,
        "weather_code": [0]*24, "is_day": [0]*24},
        "current": {"temperature_2m": 26}}
    aq = {"hourly": {"time": hourly, "us_aqi": [75]*24, "pm2_5": [17.0]*24}}
    places = {"results": [{"name": "Lahore", "country_code": "PK", "latitude": 31.558,
                             "longitude": 74.351, "admin1": "Punjab"},
                            {"name": "Lahore", "country_code": "IN", "latitude": 1, "longitude": 2}]}
    def callback(req):
        if "geocoding-api" in str(req.url):
            return httpx.Response(200, json=places)
        if "air-quality" in str(req.url):
            return httpx.Response(200, json=aq)
        return httpx.Response(200, json=weather)
    async with httpx.AsyncClient(transport=httpx.MockTransport(callback)) as client:
        assert len(await search_pakistan("Lahore", client)) == 1
        result = await fetch_tomorrow(31.558, 74.351, client)
    assert len(result["hours"]) == 24
    assert result["hours"][0]["us_aqi"] == 75
    assert result["air_quality_status"] == "model_forecast"


@pytest.mark.asyncio
async def test_missing_weather_values_do_not_fake_plan():
    date = (datetime.now(ZoneInfo("Asia/Karachi")).date() + timedelta(days=1)).isoformat()
    def callback(req):
        return httpx.Response(200, json={"hourly": {"time": [f"{date}T00:00"]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(callback)) as client:
        with pytest.raises(DataUnavailable):
            await fetch_tomorrow(31.558, 74.351, client)


def test_api_health_and_openapi():
    from fastapi.testclient import TestClient
    from app.main import app
    test_client = TestClient(app)
    assert test_client.get("/health").json()["status"] == "ok"
    assert test_client.get("/openapi.json").status_code == 200


def test_api_plan_mocked_forecast(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as routes
    async def fake_fetch(latitude, longitude, client):
        return fixture()
    monkeypatch.setattr(routes, "fetch_tomorrow", fake_fetch)
    async def fake_multi_city_ai(client, latitude, longitude):
        return {"status": "unavailable"}
    monkeypatch.setattr(routes, "predict_pakistan_pm25", fake_multi_city_ai)
    test_client = TestClient(routes.app)
    response = test_client.post("/plan", json={
        "location": {"name": "Lahore", "latitude": 31.558, "longitude": 74.351},
        "activity": "run", "earliest_start_hour": 16,
        "latest_finish_hour": 20, "duration_hours": 1,
    })
    assert response.status_code == 200
    output = response.json()
    assert output["best"]["start_hour"] == 16
    assert output["official_weather_updates_url"] == "https://weather.gov.pk/"
