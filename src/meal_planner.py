"""AI-powered meal plan generator for MiSalud.

Builds a prompt for the LLM to generate personalized weekly meal plans
based on user profile, goals, preferences, and recent meal history.
"""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from .config import USER_PROFILE

logger = logging.getLogger(__name__)

MEAL_PLAN_PROMPT_TEMPLATE = """Eres un nutricionista profesional. Crea un plan de comidas semanal personalizado.

## Perfil del Usuario
- Nombre: {name}
- Sexo: {sex}
- Edad: {age} años
- Altura: {height_cm} cm
- Nivel de actividad: {activity_level}
- Objetivo: {goal} (lose=perder peso, maintain=mantener, gain=ganar músculo)
- Tipo de dieta: {diet_type}
- Alergias: {allergies}
- Alimentos que no le gustan: {dislikes}
- Comidas al día: {meals_per_day}

## Objetivos Nutricionales
- Peso actual: {current_weight} kg
- Peso objetivo: {target_weight} kg
- Calorías diarias objetivo: {target_calories} kcal
- Proteína diaria objetivo: {target_protein} g
- Carbohidratos diarios objetivo: {target_carbs} g
- Grasas diarias objetivo: {target_fat} g

## Historial de comidas (última semana)
{recent_meals}

## Instrucciones
1. Crea un plan para 7 días ({start_date} a {end_date})
2. {meals_per_day} comidas por día: {meal_names}
3. Cada comida debe incluir alimentos concretos, cantidades en gramos, y macros
4. Prioriza comida real, mediterránea, fácil de preparar
5. Varía los alimentos a lo largo de la semana
6. Incluye recetas breves (1-2 líneas) para las comidas principales
7. Asegúrate de que el total diario esté cerca de las calorías objetivo (±10%)
8. Nombra las comidas en español: Desayuno, Almuerzo, Cena, Merienda

Devuelve SOLO un JSON array con este formato exacto (sin markdown, sin texto adicional):
[
  {{
    "day_index": 0,
    "day": "Lunes",
    "date": "YYYY-MM-DD",
    "meals": [
      {{
        "name": "Desayuno",
        "foods": "descripción detallada de alimentos con cantidades en gramos",
        "calories": 500,
        "protein_g": 30,
        "carbs_g": 50,
        "fat_g": 15,
        "recipe": "instrucciones breves de preparación"
      }}
    ],
    "daily_totals": {{
      "calories": 2200,
      "protein_g": 150,
      "carbs_g": 220,
      "fat_g": 70
    }}
  }}
]"""


class MealPlanner:
    """Build meal plan prompts and parse LLM responses."""

    def __init__(self, profile: dict = None):
        self.profile = profile or USER_PROFILE

    def build_prompt(
        self,
        start_date: str = None,
        recent_meals_text: str = "",
        current_weight: float = None,
        target_weight: float = None,
        target_calories: int = None,
    ) -> tuple[str, str]:
        """Build the prompt for meal plan generation.

        Returns (prompt, week_start_date_str).
        """
        if start_date is None:
            today = datetime.now()
            days_until_monday = (7 - today.weekday()) % 7 or 7
            start = today + timedelta(days=days_until_monday)
            start_date = start.strftime("%Y-%m-%d")

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = start + timedelta(days=6)

        # Calculate targets
        if target_calories is None:
            weight = current_weight or 80
            age = self.profile["age"]
            height = self.profile["height_cm"]
            sex_factor = 5 if self.profile["sex"] == "male" else -161
            bmr = (10 * weight) + (6.25 * height) - (5 * age) + sex_factor

            activity_mult = {
                "sedentary": 1.2, "light": 1.375,
                "moderate": 1.55, "active": 1.725, "very_active": 1.9,
            }
            tdee = bmr * activity_mult.get(self.profile["activity_level"], 1.55)

            goal_adj = {"lose": -500, "maintain": 0, "gain": 500}
            target_calories = int(tdee + goal_adj.get(self.profile["goal"], 0))

        weight_for_macros = current_weight or 80
        target_protein = int(weight_for_macros * 2.0)
        target_fat = int(target_calories * 0.25 / 9)
        target_carbs = int(
            (target_calories - target_protein * 4 - target_fat * 9) / 4
        )

        meal_names_map = {
            3: "Desayuno, Almuerzo, Cena",
            4: "Desayuno, Almuerzo, Merienda, Cena",
            5: "Desayuno, Media Mañana, Almuerzo, Merienda, Cena",
        }
        meal_names = meal_names_map.get(
            self.profile["meals_per_day"], "Desayuno, Almuerzo, Cena"
        )

        prompt = MEAL_PLAN_PROMPT_TEMPLATE.format(
            name=self.profile["name"],
            sex="Hombre" if self.profile["sex"] == "male" else "Mujer",
            age=self.profile["age"],
            height_cm=self.profile["height_cm"],
            activity_level=self.profile["activity_level"],
            goal=self.profile["goal"],
            diet_type=self.profile["diet_type"],
            allergies=", ".join(self.profile["allergies"]) if self.profile["allergies"] else "Ninguna",
            dislikes=", ".join(self.profile["dislikes"]) if self.profile["dislikes"] else "Ninguno",
            meals_per_day=self.profile["meals_per_day"],
            current_weight=current_weight or "?",
            target_weight=target_weight or "?",
            target_calories=target_calories,
            target_protein=target_protein,
            target_carbs=target_carbs,
            target_fat=target_fat,
            recent_meals=recent_meals_text or "No hay datos recientes de comidas.",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            meal_names=meal_names,
        )

        return prompt, start_date

    @staticmethod
    def parse_plan(response_text: str) -> list[dict]:
        """Extract JSON meal plan from LLM response text."""
        # Direct parse
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Markdown code block
        json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', response_text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # JSON array anywhere
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse meal plan JSON from response")
        return []
