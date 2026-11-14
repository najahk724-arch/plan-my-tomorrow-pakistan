
import httpx
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

# MODULE 6: Lahore next-day PM2.5 prediction

print("Fetching Lahore pollution history...")

response = httpx.get(
    "https://air-quality-api.open-meteo.com/v1/air-quality",
    params={
        "latitude": 31.55,
        "longitude": 74.35,
        "hourly": "pm2_5",
        "timezone": "Asia/Karachi",

"start_date": "2025-11-01",
"end_date": "2026-11-13",

    },
    timeout=45,
)
response.raise_for_status()

hourly = response.json()["hourly"]

df = pd.DataFrame({
    "time": pd.to_datetime(hourly["time"]),
    "pm25": hourly["pm2_5"]
})

df["date"] = df["time"].dt.normalize()

# Calculate daily average pollution
daily = df.groupby("date").agg(
    pm25=("pm25", "mean"),
    hours=("pm25", "count")
).sort_index()

# Keep only complete days
daily = daily[daily["hours"] == 24].copy()

if len(daily) < 40:
    raise ValueError("Not enough complete days for training.")

if not (daily.index.to_series().diff().dropna()
        == pd.Timedelta(days=1)).all():
    raise ValueError("Missing dates in pollution history.")

# Features available before predicting tomorrow
daily["today"] = daily["pm25"]
daily["yesterday"] = daily["pm25"].shift(1)
daily["two_days_ago"] = daily["pm25"].shift(2)
daily["three_day_average"] = daily["pm25"].rolling(3).mean()
daily["recent_change"] = daily["today"] - daily["yesterday"]

# Tomorrow is the prediction target
daily["tomorrow"] = daily["pm25"].shift(-1)

data = daily.dropna().copy()

features = [
    "today",
    "yesterday",
    "two_days_ago",
    "three_day_average",
    "recent_change"
]

# Chronological split, with a one-day gap
split = int(len(data) * 0.75)
train = data.iloc[:split]
test = data.iloc[split + 1:]

if len(test) < 10:
    raise ValueError("Not enough test days.")

model = RandomForestRegressor(
    n_estimators=200,
    min_samples_leaf=3,
    random_state=42
)

print("Training AI model...")
model.fit(train[features], train["tomorrow"])

ai_predictions = model.predict(test[features])

# Baseline: tomorrow's pollution equals today's
baseline_predictions = test["today"].to_numpy()

ai_error = mean_absolute_error(
    test["tomorrow"], ai_predictions
)

baseline_error = mean_absolute_error(
    test["tomorrow"], baseline_predictions
)

print("\n===== PLAN MY TOMORROW: AI TEST =====")
print("Training samples:", len(train))
print("Unseen test samples:", len(test))
print("Baseline MAE:", round(baseline_error, 2))
print("AI model MAE:", round(ai_error, 2))

if ai_error < baseline_error:
    print("RESULT: AI beat the baseline!")
else:
    print("RESULT: Baseline performed better or tied.")

results = pd.DataFrame({
    "date_predicted": test.index + pd.Timedelta(days=1),
    "actual_pm25": test["tomorrow"].to_numpy(),
    "baseline_pm25": baseline_predictions,
    "ai_pm25": ai_predictions
})

results.to_csv("air_quality_test_results.csv", index=False)

print("\nLast 5 test predictions:")
print(results.tail().round(2).to_string(index=False))
print("\nResults saved to air_quality_test_results.csv")
