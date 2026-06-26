"""Google Fit REST API client for MiSalud.

Reads fitness data: steps, weight, heart rate, sleep, active calories.
Uses the Fitness REST API v1 with OAuth credentials from Hermes.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import GOOGLE_TOKEN_PATH

logger = logging.getLogger(__name__)

NANOS_PER_SECOND = 1_000_000_000

# Google Fit data type identifiers (generic — works with any data source)
DATA_TYPES = {
    "steps": "com.google.step_count.delta",
    "weight": "com.google.weight",
    "heart_rate": "com.google.heart_rate.bpm",
    "sleep": "com.google.sleep.segment",
    "calories": "com.google.calories.expended",
    "activity_minutes": "com.google.active_minutes",
}


class GoogleFitClient:
    """Client for Google Fit REST API v1."""

    def __init__(self):
        if not GOOGLE_TOKEN_PATH.exists():
            raise FileNotFoundError(
                f"Google token not found at {GOOGLE_TOKEN_PATH}. "
                "Run google-workspace skill setup first."
            )
        with open(GOOGLE_TOKEN_PATH) as f:
            token_data = json.load(f)

        self.creds = Credentials.from_authorized_user_info(token_data)
        self.service = build("fitness", "v1", credentials=self.creds)

    def _time_range_ns(self, days_back: int = 7) -> tuple[int, int]:
        """Build (start_ns, end_ns) for the past N days."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)
        end = end.replace(hour=23, minute=59, second=59, microsecond=0)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            int(start.timestamp() * NANOS_PER_SECOND),
            int(end.timestamp() * NANOS_PER_SECOND),
        )

    def _get_aggregate(self, data_type_name: str, days_back: int = 7) -> list[dict]:
        """Get daily aggregated values for a data type."""
        if data_type_name not in DATA_TYPES:
            raise ValueError(f"Unknown data type: {data_type_name}")

        start_ns, end_ns = self._time_range_ns(days_back)

        body = {
            "aggregateBy": [{"dataTypeName": DATA_TYPES[data_type_name]}],
            "bucketByTime": {"durationMillis": 86400000},
            "startTimeMillis": start_ns // 1_000_000,
            "endTimeMillis": end_ns // 1_000_000,
        }

        try:
            result = (
                self.service.users()
                .dataset()
                .aggregate(userId="me", body=body)
                .execute()
            )
        except Exception as e:
            logger.error("Google Fit API error for %s: %s", data_type_name, e)
            return []

        daily_values = []
        for bucket in result.get("bucket", []):
            start_ms = int(bucket["startTimeMillis"])
            date_str = datetime.fromtimestamp(
                start_ms / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")

            value = 0.0
            for ds in bucket.get("dataset", []):
                for point in ds.get("point", []):
                    for val in point.get("value", []):
                        fp = val.get("fpVal")
                        value += fp if fp is not None else val.get("intVal", 0)

            daily_values.append({"date": date_str, "value": round(value, 1)})

        return daily_values

    def get_daily_summary(self, days_back: int = 1) -> dict:
        """Get a summary of all fitness metrics for the most recent day(s).

        Returns:
            dict with keys: steps, weight_kg, heart_rate_bpm,
            sleep_hours, active_calories, active_minutes
        """
        summary = {
            "steps": 0,
            "weight_kg": None,
            "heart_rate_bpm": None,
            "sleep_hours": None,
            "active_calories": 0,
            "active_minutes": 0,
        }

        key_map = {
            "steps": "steps",
            "weight": "weight_kg",
            "heart_rate": "heart_rate_bpm",
            "sleep": "sleep_hours",
            "calories": "active_calories",
            "activity_minutes": "active_minutes",
        }

        for data_type, output_key in key_map.items():
            data = self._get_aggregate(data_type, days_back)
            if not data:
                continue

            val = data[-1]["value"]
            if data_type == "steps":
                summary[output_key] = int(val)
            elif data_type == "sleep":
                summary[output_key] = round(val / 60, 1)
            elif data_type in ("calories", "activity_minutes"):
                summary[output_key] = int(val)
            else:
                summary[output_key] = val

        return summary

    def get_last_7_days(self) -> list[dict]:
        """Get full daily summaries for the last 7 days."""
        result: list[dict] = []

        for data_type in DATA_TYPES:
            daily = self._get_aggregate(data_type, days_back=7)
            for entry in daily:
                date_entry = next(
                    (r for r in result if r["date"] == entry["date"]), None
                )
                if date_entry is None:
                    date_entry = {"date": entry["date"]}
                    result.append(date_entry)

                if data_type == "steps":
                    date_entry["steps"] = int(entry["value"])
                elif data_type == "weight":
                    date_entry["weight_kg"] = entry["value"]
                elif data_type == "heart_rate":
                    date_entry["heart_rate_bpm"] = entry["value"]
                elif data_type == "sleep":
                    date_entry["sleep_hours"] = round(entry["value"] / 60, 1)
                elif data_type == "calories":
                    date_entry["active_calories"] = int(entry["value"])
                elif data_type == "activity_minutes":
                    date_entry["active_minutes"] = int(entry["value"])

        return sorted(result, key=lambda x: x["date"])
