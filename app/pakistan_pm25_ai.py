
"""Experimental Pakistan multi-city PM2.5 predictor."""

from datetime import datetime, timedelta
from functools import lru_cache
from math import pi, sin, cos, isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from joblib import load


MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "pakistan_ai_candidate.joblib"
)


@lru_cache(maxsize=1)
def get_model_package():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "pakistan_ai_candidate.joblib was not found."
        )
    return load(MODEL_PATH)


async def predict_pakistan_pm25(
    client,
    latitude: float,
    longitude: float,
):
    package = get_model_package()
    model = package["model"]
    features = package["features"]

    # Use Pakistan's date, regardless of server timezone.
    today = datetime.now(
        ZoneInfo("Asia/Karachi")
    ).date()

    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    start = yesterday - timedelta(days=13)

    response = await client.get(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "pm2_5",
            "timezone": "Asia/Karachi",
            "start_date": start.isoformat(),
            "end_date": yesterday.isoformat(),
        },
    )
    response.raise_for_status()

    hourly = response.json().get("hourly", {})
    times = hourly.get("time", [])
    values = hourly.get("pm2_5", [])

    if not times or len(times) != len(values):
        raise ValueError("Historical PM2.5 data is missing.")

    df = pd.DataFrame({
        "time": pd.to_datetime(times),
        "pm25": pd.to_numeric(values, errors="coerce"),
    })
    df["date"] = df["time"].dt.date

    # Only count days with 24 valid hourly observations.
    daily = df.groupby("date")["pm25"].agg(
        ["mean", "count", "size"]
    )

    daily = daily[
        (daily["count"] == 24)
        & (daily["size"] == 24)
    ]

    # Match the training setup exactly:
    # seven completed days, ending yesterday.
    needed_dates = [
        yesterday - timedelta(days=i)
        for i in range(6, -1, -1)
    ]

    if not all(day in daily.index for day in needed_dates):
        raise ValueError(
            "Seven complete recent days of PM2.5 "
            "data are not available."
        )

    history = daily.loc[needed_dates, "mean"]

    pm25 = float(history.iloc[-1])
    lag_1 = float(history.iloc[-2])
    lag_2 = float(history.iloc[-3])
    lag_3 = float(history.iloc[-4])

    day_number = tomorrow.timetuple().tm_yday

    inputs = {
        "pm25": pm25,
        "lag_1": lag_1,
        "lag_2": lag_2,
        "lag_3": lag_3,
        "avg_3": float(history.iloc[-3:].mean()),
        "avg_7": float(history.mean()),
        "change": pm25 - lag_1,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "season_sin": sin(
            2 * pi * day_number / 365.25
        ),
        "season_cos": cos(
            2 * pi * day_number / 365.25
        ),
    }

    # Exact feature order saved during training.
    model_input = pd.DataFrame([inputs])[features]

    prediction = float(
        model.predict(model_input)[0]
    )

    if not isfinite(prediction):
        raise ValueError("AI returned an invalid prediction.")

    return {
        "status": "available",
        "model": "Pakistan Multi-city Random Forest",
        "prediction_date": tomorrow.isoformat(),
        "predicted_daily_pm25_ug_m3": round(
            max(0.0, prediction), 2
        ),
        "baseline_daily_pm25_ug_m3": round(
            pm25, 2
        ),
        "experimental": True,
        "message": (
            "Experimental next-day pollution estimate. "
            "Trained on nine Pakistani cities and tested "
            "on additional cities. Accuracy varies by "
            "location; this is not a safety rating."
        ),
    }
