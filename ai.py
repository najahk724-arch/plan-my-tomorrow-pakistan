"""Optional pretrained LLM: translate the user's words into checked input fields.

Gemini never supplies weather values, official alerts or risk thresholds.
"""
import os
from app.schemas import ParsedPreferences


def parse_preferences(text: str) -> ParsedPreferences:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not configured; use structured preferences instead.")
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("Optional google-genai package is not installed.") from exc

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=(
            "Extract only the activity, start/finish hours, whole-hour duration, "
            "rain avoidance, and daylight preference explicitly mentioned by the user. "
            "Use 24-hour local Pakistan hours. Return null for unspecified information. "
            "Do not generate weather forecasts or safety advice.\n\nUser: " + text
        ),
        config={"response_mime_type": "application/json",
                "response_schema": ParsedPreferences},
    )
    if response.parsed is None:
        raise RuntimeError("AI returned no structured preferences.")
    return ParsedPreferences.model_validate(response.parsed)
