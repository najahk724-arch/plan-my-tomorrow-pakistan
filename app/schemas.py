from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Location(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    latitude: float = Field(ge=23.0, le=38.0)
    longitude: float = Field(ge=60.0, le=79.0)
    country_code: Literal["PK"] = "PK"
    admin1: str | None = None


class PlanRequest(BaseModel):
    location: Location
    activity: Literal["run", "cycling", "picnic", "driving", "hiking", "sports", "camping"]
    earliest_start_hour: int = Field(default=6, ge=0, le=23)
    latest_finish_hour: int = Field(default=21, ge=1, le=24)
    duration_hours: int = Field(default=1, ge=1, le=24)
    comfort_min_c: float = Field(default=18, ge=-30, le=60)
    comfort_max_c: float = Field(default=26, ge=-30, le=60)
    avoid_rain: bool = True
    daylight_only: bool = False

    @model_validator(mode="after")
    def validate_window(self):
        if self.latest_finish_hour - self.earliest_start_hour < self.duration_hours:
            raise ValueError("Available time window must fit your activity duration.")
        if self.comfort_max_c <= self.comfort_min_c:
            raise ValueError("Highest preferred temperature must exceed lowest.")
        return self


class PreferencesText(BaseModel):
    text: str = Field(min_length=4, max_length=1000)


class ParsedPreferences(BaseModel):
    activity: Literal["run", "cycling", "picnic", "driving", "hiking", "sports", "camping"] | None = None
    earliest_start_hour: int | None = Field(default=None, ge=0, le=23)
    latest_finish_hour: int | None = Field(default=None, ge=1, le=24)
    duration_hours: int | None = Field(default=None, ge=1, le=24)
    avoid_rain: bool | None = None
    daylight_only: bool | None = None
