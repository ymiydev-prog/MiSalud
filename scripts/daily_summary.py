#!/usr/bin/env python3
"""Daily nutrition and fitness summary for MiSalud.

Generates an end-of-day summary. Designed to run as a Hermes cron job
(daily at 21:00). The final agent response will be delivered to the user.
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.repository import MiSaludRepo


def main():
    today = date.today()
    print(f"📊 *Resumen Diario MiSalud — {today.strftime('%d/%m/%Y')}*\n")

    with MiSaludRepo() as repo:
        nutrition = repo.daily_nutrition(today)
        fit = repo.get_today_fit()
        goal = repo.get_active_goal()

    # ── Nutrition ──────────────────────────────────
    print("🍽️ *Nutrición*")
    if nutrition["meals"]:
        print(f"• Calorías: {nutrition['calories']:.0f} kcal")
        print(f"• Proteínas: {nutrition['protein_g']:.0f} g")
        print(f"• Carbohidratos: {nutrition['carbs_g']:.0f} g")
        print(f"• Grasas: {nutrition['fat_g']:.0f} g")
        print(f"• Fibra: {nutrition['fiber_g']:.0f} g")
        print(f"• Comidas registradas: {len(nutrition['meals'])}")

        if goal and goal.daily_calories:
            remaining = goal.daily_calories - nutrition["calories"]
            sign = "+" if remaining >= 0 else ""
            emoji = "✅" if -100 <= remaining <= 100 else ("⚠️" if remaining < -100 else "📉")
            print(f"• {emoji} vs Objetivo ({goal.daily_calories} kcal): {sign}{remaining:.0f}")

        for m in nutrition["meals"]:
            foods = ", ".join(f["name"] for f in m["foods"])
            print(f"  • {m['type']} ({m['time']}): {foods} — {m['total_calories']:.0f} kcal")
    else:
        print("• Sin comidas registradas hoy")

    print()

    # ── Activity ───────────────────────────────────
    print("🏃 *Actividad*")
    if fit and fit.steps:
        print(f"• Pasos: {fit.steps:,}")
    else:
        print("• Pasos: sin datos")

    with MiSaludRepo() as repo:
        workouts = repo.get_workouts_range(today, today)
    if workouts:
        print("• Entrenos:")
        for w in workouts:
            print(f"  • {w.workout_type.name}: {w.duration_min} min" +
                  (f" — {w.notes}" if w.notes else ""))
    else:
        print("• Sin entrenamiento registrado")

    print()

    # ── Sleep ──────────────────────────────────────
    print("😴 *Sueño*")
    if fit and fit.sleep_hours:
        print(f"• {fit.sleep_hours} horas")
    else:
        print("• Sin datos de sueño")

    # ── Weekly summary (auto-compute) ──────────────
    # Compute for the current week
    week_start = today - timedelta(days=today.weekday())
    with MiSaludRepo() as repo:
        summary = repo.compute_weekly_summary(week_start)
    print(f"\n📈 *Media semanal* ({week_start} → {today}):")
    print(f"• Calorías: {summary['avg_calories']:.0f} kcal/día")
    if summary.get("compliance_pct"):
        print(f"• Cumplimiento: {summary['compliance_pct']}%")


if __name__ == "__main__":
    main()
