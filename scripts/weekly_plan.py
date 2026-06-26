#!/usr/bin/env python3
"""Weekly meal plan generator for MiSalud.

Generates a meal plan prompt and saves it for the LLM to process.
Designed to run as a Hermes cron job (Sundays at 10:00).
The cron job prompt will call the LLM and save the result.
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.repository import MiSaludRepo
from src.meal_planner import MealPlanner


def main():
    print("🍽️ MiSalud — Generating weekly meal plan prompt...\n")

    with MiSaludRepo() as repo:
        # Recent meals context
        today = date.today()
        week_ago = today - timedelta(days=7)
        meals = repo.get_meals_range(week_ago, today)

        recent_text = ""
        if meals:
            lines = []
            for m in meals[-15:]:  # Last 15 meals
                foods = ", ".join(f.food_name for f in m.foods)
                lines.append(
                    f"{m.eaten_at.strftime('%d/%m')} {m.meal_type.name}: "
                    f"{foods} ({m.total_calories:.0f} kcal)"
                )
            recent_text = "\n".join(lines)
        else:
            recent_text = "No hay comidas registradas esta semana"

        # Current weight
        weight_trend = repo.get_weight_trend(7)
        current_weight = weight_trend[-1]["weight_kg"] if weight_trend else None

        # Target weight from active goal
        goal = repo.get_active_goal()
        target_weight = goal.target_weight_kg if goal else None
        target_calories = goal.daily_calories if goal else None

    # Build prompt
    planner = MealPlanner()
    prompt, week_start = planner.build_prompt(
        recent_meals_text=recent_text,
        current_weight=current_weight,
        target_weight=target_weight,
        target_calories=target_calories,
    )

    # Save prompt for the cron job agent to process
    prompt_dir = Path(__file__).resolve().parent.parent / "data"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / "last_plan_prompt.txt"
    prompt_file.write_text(prompt)

    print(f"✅ Meal plan prompt generated ({len(prompt)} chars)")
    print(f"   Week: {week_start}")
    print(f"   Weight: {current_weight or '?'} kg")
    print(f"   Target: {target_calories or '?'} kcal/day")
    print(f"   Goal: {planner.profile['goal']}")
    print(f"\n📝 Prompt saved to: {prompt_file}")
    print("\nThe cron agent will now send this prompt to the LLM.")
    print("After receiving the response, run:")
    print("  python3 scripts/save_plan.py '<llm_response_json>'")


if __name__ == "__main__":
    main()
