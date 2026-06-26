#!/usr/bin/env python3
"""Export SQLite data to Google Sheets (read-only mobile view).

Exports the last 30 days of meals, weight, and fit data to a Google Sheet.
This is NOT the source of truth — SQLite is. Sheets is a convenience view.
"""
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.repository import MiSaludRepo
from src.sheets_export import SheetsExporter


def main():
    print("📤 MiSalud — Exporting to Google Sheets...")

    today = date.today()
    start = today - timedelta(days=30)

    with MiSaludRepo() as repo:
        # Build flat tables
        meals_data = []
        meal_rows = repo.get_meals_range(start, today)
        for m in meal_rows:
            for f in m.foods:
                meals_data.append([
                    m.eaten_at.strftime("%Y-%m-%d"),
                    m.eaten_at.strftime("%H:%M"),
                    m.meal_type.name,
                    f.food_name,
                    f.portion_g or "",
                    f.calories or "",
                    f.protein_g or "",
                    f.carbs_g or "",
                    f.fat_g or "",
                    m.confidence or "",
                    m.notes or "",
                ])

        weight_data = [
            [w["date"], w["weight_kg"], w.get("bodyfat_pct", "")]
            for w in repo.get_weight_trend(30)
        ]

        fit_rows = repo.get_fit_range(start, today)
        fit_data = [
            [
                str(r.date), r.steps,
                r.sleep_hours or "",
                r.active_calories,
                r.active_minutes,
                r.weight_kg or "",
            ]
            for r in fit_rows
        ]

    # Export to Sheets
    exporter = SheetsExporter()
    exporter.export_meals(meals_data)
    exporter.export_weight(weight_data)
    exporter.export_fit(fit_data)

    print(f"✅ Exported: {len(meals_data)} foods, {len(weight_data)} weights, {len(fit_data)} fit rows")
    print(f"📎 {exporter.url}")


if __name__ == "__main__":
    main()
