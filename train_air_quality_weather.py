
import httpx
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

print("MODULE 8: Weather-powered pollution AI")

# 1. Download historical pollution data
print("Downloading Lahore PM2.5 data...")

air_response = httpx.get(
    "https://air-quality-api.open-meteo.com/v1/air-quality",
    params={
        "latitude": 31.55,
        "longitude": 74.35,
        "hourly": "pm2_5",
        "timezone": "Asia/Karachi",
        "start_date": "2025-11-01",
        "end_date": "2026-11-13"
    },
    timeout=75
)

air_response.raise_for_status()
air = air_response.json()["hourly"]

air_df = pd.DataFrame({
    "date": pd.to_datetime(air["time"]).normalize(),
    "pm25": air["pm2_5"]
})

daily_air = air_df.groupby("date").agg(
    pm25=("pm25", "mean"),
    hours=("pm25", "count")
)

daily_air = daily_air[daily_air["hours"] == 24].copy()

# 2. Download historical weather
print("Downloading Lahore weather history...")

weather_response = httpx.get(
    "https://archive-api.open-meteo.com/v1/archive",
    params={
        "latitude": 31.55,
        "longitude": 74.35,
        "daily": (
            "temperature_2m_mean,"
            "relative_humidity_2m_mean,"
            "precipitation_sum,"
            "wind_speed_10m_max"
        ),
        "timezone": "Asia/Karachi",
        "start_date": "2025-11-01",
        "end_date": "2026-11-08"
    },
    timeout=75
)

weather_response.raise_for_status()
weather = weather_response.json()["daily"]

weather_df = pd.DataFrame({
    "date": pd.to_datetime(weather["time"]),
    "temperature": weather["temperature_2m_mean"],
    "humidity": weather["relative_humidity_2m_mean"],
    "rainfall": weather["precipitation_sum"],
    "wind": weather["wind_speed_10m_max"]
}).set_index("date")

# 3. Create features
daily_air["pm_yesterday"] = daily_air["pm25"].shift(1)
daily_air["pm_3day_avg"] = daily_air["pm25"].rolling(3).mean()
daily_air["pm_7day_avg"] = daily_air["pm25"].rolling(7).mean()
daily_air["pm_change"] = (
    daily_air["pm25"] - daily_air["pm_yesterday"]
)

# Predict the NEXT day's pollution
daily_air["tomorrow_pm25"] = daily_air["pm25"].shift(-1)

# Combine pollution and weather on the same date
data = daily_air.join(weather_df, how="inner")
data = data.dropna().copy()

pollution_features = [
    "pm25",
    "pm_yesterday",
    "pm_3day_avg",
    "pm_7day_avg",
    "pm_change"
]

weather_features = pollution_features + [
    "temperature",
    "humidity",
    "rainfall",
    "wind"
]

if len(data) < 100:
    raise ValueError("Not enough matching weather and pollution days.")

# 4. Split chronologically
# Earlier dates: train
# Middle dates: validation
# Latest dates: final test
n = len(data)
train_end = int(n * 0.70)
validation_end = int(n * 0.85)

# Leave a one-day gap at each boundary
train = data.iloc[:train_end - 1]
validation = data.iloc[train_end:validation_end - 1]
test = data.iloc[validation_end:]

print("\nTraining days:", len(train))
print("Validation days:", len(validation))
print("Final test days:", len(test))

# 5. Train two AI models
def create_model():
    return RandomForestRegressor(
        n_estimators=250,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1
    )

print("\nTraining pollution-only AI...")
pollution_model = create_model()
pollution_model.fit(
    train[pollution_features],
    train["tomorrow_pm25"]
)

print("Training weather-powered AI...")
weather_model = create_model()
weather_model.fit(
    train[weather_features],
    train["tomorrow_pm25"]
)

# 6. Compare on validation dates
actual_val = validation["tomorrow_pm25"]

validation_scores = {
    "Baseline": mean_absolute_error(
        actual_val, validation["pm25"]
    ),
    "Pollution AI": mean_absolute_error(
        actual_val,
        pollution_model.predict(validation[pollution_features])
    ),
    "Weather AI": mean_absolute_error(
        actual_val,
        weather_model.predict(validation[weather_features])
    )
}

print("\n===== VALIDATION RESULTS =====")
for name, error in validation_scores.items():
    print(f"{name} MAE: {error:.2f}")

winner = min(validation_scores, key=validation_scores.get)
print("Validation winner:", winner)

# 7. Final test: same unseen dates for every method
actual_test = test["tomorrow_pm25"]

predictions = {
    "Baseline": test["pm25"].to_numpy(),
    "Pollution AI": pollution_model.predict(
        test[pollution_features]
    ),
    "Weather AI": weather_model.predict(
        test[weather_features]
    )
}

print("\n===== FINAL UNSEEN TEST =====")
for name, values in predictions.items():
    error = mean_absolute_error(actual_test, values)
    print(f"{name} MAE: {error:.2f}")

print("\nSelected using validation:", winner)

# 8. Save results
results = pd.DataFrame({
    "date": test.index + pd.Timedelta(days=1),
    "actual_pm25": actual_test.to_numpy(),
    "baseline": predictions["Baseline"],
    "pollution_ai": predictions["Pollution AI"],
    "weather_ai": predictions["Weather AI"]
})

results.to_csv(
    "air_quality_weather_test_results.csv",
    index=False
)

print("\nLast 5 predictions:")
print(results.tail().to_string(index=False))

print("\nSaved: air_quality_weather_test_results.csv")
print("MODULE 8 COMPLETE")

# MODULE 9: Save the selected model for deployment

from joblib import dump

print("\nMODULE 9: Preparing deployment model...")

if winner == "Baseline":
    print("Baseline selected; no AI model saved.")
else:
    selected_features = (
        pollution_features
        if winner == "Pollution AI"
        else weather_features
    )

    # Refit after evaluation using available historical data.
    # Keep the earlier final-test scores unchanged.
    if winner == "Pollution AI":
        deployment_data = daily_air.dropna(
            subset=selected_features + ["tomorrow_pm25"]
        ).copy()
    else:
        deployment_data = data.copy()

    final_model = create_model()
    final_model.fit(
        deployment_data[selected_features],
        deployment_data["tomorrow_pm25"]
    )

    model_package = {
        "model": final_model,
        "features": selected_features,
        "model_name": winner,
        "city": "Lahore",
        "prediction_target": "next-day mean PM2.5",
        "training_data": "Open-Meteo modeled pollution data",
    }

    dump(model_package, "lahore_pm25_model.joblib")

    print("Selected model:", winner)
    print("Deployment training samples:", len(deployment_data))
    print("Model saved: lahore_pm25_model.joblib")

print("MODULE 9 COMPLETE")

