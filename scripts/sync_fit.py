#!/usr/bin/env python3
"""Sync Google Fit data to MiSalud SQLite database.

Fetches last N days from Google Fit REST API and upserts into fit_data table.
Designed to run as a Hermes cron job (daily at 8:00).

Usage:
    python scripts/sync_fit.py          # Last 7 days (default)
    python scripts/sync_fit.py --full   # Last 90 days (full history)
"""
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.google_fit import GoogleFitClient
from src.repository import MiSaludRepo


def main():
    # Parse --full flag
    days = 90 if "--full" in sys.argv else 7

    print(f"🔄 MiSalud — Syncing Google Fit (last {days} days) → SQLite...")

    try:
        fit = GoogleFitClient()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Fetch full range using the client's low-level method
    from datetime import datetime, timedelta, timezone
    NANOS = 1_000_000_000

    data = fit.get_last_7_days() if days == 7 else _fetch_full(fit, days)

    if not data:
        print("⚠️  No Fit data returned. Is Google Fit set up on your phone?")
        print("   Check: https://www.google.com/fit/")
        sys.exit(0)

    print(f"📊 Retrieved {len(data)} days from Google Fit")

    with MiSaludRepo() as repo:
        for day in data:
            repo.upsert_fit_data(
                fit_date=date.fromisoformat(day["date"]),
                steps=day.get("steps", 0),
                resting_heart_rate=day.get("heart_rate_bpm"),
                weight_kg=day.get("weight_kg"),
                sleep_hours=day.get("sleep_hours"),
                active_calories=day.get("active_calories", 0),
                active_minutes=day.get("activity_minutes", 0),
            )

    print(f"✅ Synced {len(data)} days to SQLite")

    # Show latest
    latest = data[-1]
    print(f"\n📋 Latest day ({latest['date']}):")
    print(f"   👣 Steps: {latest.get('steps', 0):,}")
    print(f"   🔥 Active calories: {latest.get('active_calories', 0)}")
    print(f"   😴 Sleep: {latest.get('sleep_hours', '?')} h")


def _fetch_full(fit: GoogleFitClient, days: int = 90) -> list[dict]:
    """Fetch full history from multiple data types, chunked by 30 days."""
    from datetime import datetime, timedelta, timezone

    result: list[dict] = []
    data_types = {
        "steps": "com.google.step_count.delta",
        "weight": "com.google.weight",
        "active_minutes": "com.google.active_minutes",
        "calories": "com.google.calories.expended",
    }

    # Chunk into 30-day windows to avoid "aggregate duration too large"
    chunk_size = 30
    end = datetime.now(timezone.utc)
    for offset in range(0, days, chunk_size):
        chunk_days = min(chunk_size, days - offset)
        chunk_end = end - timedelta(days=offset)
        chunk_start = chunk_end - timedelta(days=chunk_days)

        start_ns = int(chunk_start.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1_000_000_000)
        end_ns = int(chunk_end.replace(hour=23, minute=59, second=59, microsecond=0).timestamp() * 1_000_000_000)

        for key, dt_name in data_types.items():
            body = {
                "aggregateBy": [{"dataTypeName": dt_name}],
                "bucketByTime": {"durationMillis": 86400000},
                "startTimeMillis": start_ns // 1_000_000,
                "endTimeMillis": end_ns // 1_000_000,
            }
            try:
                resp = fit.service.users().dataset().aggregate(userId="me", body=body).execute()
            except Exception as e:
                continue

            for bucket in resp.get("bucket", []):
                start_ms = int(bucket["startTimeMillis"])
                date_str = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

                value = 0.0
                for ds in bucket.get("dataset", []):
                    for point in ds.get("point", []):
                        for val in point.get("value", []):
                            fp = val.get("fpVal")
                            value += fp if fp is not None else val.get("intVal", 0)

                if value > 0:
                    entry = next((r for r in result if r["date"] == date_str), None)
                    if entry is None:
                        entry = {"date": date_str}
                        result.append(entry)

                    if key == "steps":
                        entry["steps"] = int(value)
                    elif key == "weight":
                        entry["weight_kg"] = round(value, 1)
                    elif key == "calories":
                        entry["active_calories"] = int(value)
                    elif key == "active_minutes":
                        entry["activity_minutes"] = int(value)

    return sorted(result, key=lambda x: x["date"])


if __name__ == "__main__":
    main()
