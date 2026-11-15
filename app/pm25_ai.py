
"""Experimental Lahore next-day PM2.5 ML prediction."""

from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import httpx
from joblib import load

from app.forecast import AIR_API, get_json

PK_TZ = ZoneInfo("Asia/Karachi")
MODEL_FILE = (
    Path(__file__).resolve().parent.parent
    / "lahore_pm25_model.joblib"
)


@lru_cache(maxsize=1)
def load_ai_model():
    # Only load our own trusted model file.
    return load(MODEL_FILE)


async def predict_lahore_pm25(client: httpx.AsyncClient):
    today = datetime.now(PK_TZ).date()
    start = today - timedelta(days=8)

    payload = await get_json(
        client,
        AIR_API,
        {
            "latitude": 31.55,
            "longitude": 74.35,
            "hourly": "pm2_5",
            "timezone": "Asia/Karachi",
            "start_date": start.isoformat(),
            "end_date": today.isoformat(),
        },
    )

    hourly = payload["hourly"]

    df = pd.DataFrame({
        "date": [t[:10] for t in hourly["time"]],
        "pm25": hourly["pm2_5"],
    })

    daily = df.groupby("date").agg(
        pm25=("pm25", "mean"),
        hours=("pm25", "count"),
    )

    # Seven consecutive complete days, ending today.
    dates = [
        (today - timedelta(days=n)).isoformat()
        for n in range(6, -1, -1)
    ]

    recent = daily.reindex(dates)

    if recent.isna().any().any() or not (
        recent["hours"] == 24
    ).all():
        raise ValueError("Seven complete daily estimates unavailable.")

    values = recent["pm25"].tolist()

    features = {
        "pm25": values[-1],
        "pm_yesterday": values[-2],
        "pm_3day_avg": sum(values[-3:]) / 3,
        "pm_7day_avg": sum(values) / 7,
        "pm_change": values[-1] - values[-2],
    }

    package = load_ai_model()

    X = pd.DataFrame([features])[package["features"]]
    prediction = float(package["model"].predict(X)[0])

    return {
        "status": "available",
        "city": "Lahore",
        "prediction_date": (
            today + timedelta(days=1)
        ).isoformat(),
        "model": package["model_name"],
        "predicted_daily_pm25_ug_m3": round(
            max(0.0, prediction), 2
        ),
        "baseline_daily_pm25_ug_m3": round(
            values[-1], 2
        ),
        "note": (
            "Experimental daily-average ML estimate. "
            "Input includes today's modeled pollution values, "
            "including forecasts for remaining hours. "
            "Not a station reading or hourly safety rating."
        ),
    }
