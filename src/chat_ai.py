"""Conversational AI layer for MiSalud Telegram bot.

Uses DeepSeek API (OpenAI-compatible) for nutrition coaching chat.
Injects user context: today's meals, goals, weight, Fit data.
"""
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# Load .env from project root AND Hermes home
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path.home() / ".hermes" / ".env")

from .repository import MiSaludRepo
from .config import USER_PROFILE

logger = logging.getLogger(__name__)

# DeepSeek API key — check MISALUD_DEEPSEEK_KEY first, then DEEPSEEK_API_KEY
DEEPSEEK_API_KEY = os.getenv("MISALUD_DEEPSEEK_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

SYSTEM_PROMPT = """Eres YhasSalud Coach, un nutricionista y entrenador personal profesional. Tu trabajo es ayudar a Youssef con su alimentacion y entrenamiento.

## Sobre Youssef
- {age} anos, {height_cm} cm, sexo {sex}
- Objetivo: {goal}
- Dieta: {diet_type}
- Calorias objetivo diarias: {target_calories} kcal
- Proteina: {target_protein}g, Carbos: {target_carbs}g, Grasas: {target_fat}g

## Datos de hoy ({today})
- Calorias consumidas: {calories_today:.0f} kcal
- Proteinas: {protein_today:.0f}g
- Comidas registradas: {meal_count}
- Pasos: {steps_today}
- Peso actual: {current_weight} kg
{meals_detail}

## Reglas
1. Responde en espanol, siempre
2. Se motivador pero honesto — si se paso de calorias, diselo con tacto
3. Da consejos practicos y accionables, no teoria generica
4. Si te preguntan por un alimento, estima sus calorias
5. Si te preguntan recetas, dalas con ingredientes y cantidades
6. Respuestas concisas (2-4 frases), a menos que pidan detalles
7. Usa emojis con moderacion
8. Recuerda datos de la conversacion actual"""


class NutritionCoach:
    """AI nutrition coach backed by DeepSeek LLM."""

    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_BASE_URL
        self.model = DEEPSEEK_MODEL
        self.conversation_history: list[dict] = []

    def _build_context(self) -> str:
        """Fetch real user data and build the system prompt."""
        today = date.today()
        profile = USER_PROFILE

        with MiSaludRepo() as repo:
            nutrition = repo.daily_nutrition(today)
            fit = repo.get_today_fit()
            goal = repo.get_active_goal()
            weight_trend = repo.get_weight_trend(7)

        current_weight = weight_trend[-1]["weight_kg"] if weight_trend else "?"

        target_calories = goal.daily_calories if goal else 2200
        target_protein = goal.protein_g if goal else 150
        target_carbs = goal.carbs_g if goal else 220
        target_fat = goal.fat_g if goal else 73

        steps = fit.steps if fit else 0

        # Build meals detail
        meals_lines = []
        for m in nutrition.get("meals", []):
            foods = ", ".join(f["name"] for f in m["foods"])
            meals_lines.append(f"  {m['type']} ({m['time']}): {foods} — {m['total_calories']:.0f} kcal")

        meals_detail = "\n".join(meals_lines) if meals_lines else "  Sin comidas registradas aun"

        goal_map = {
            "maintain": "mantener peso",
            "lose": "perder peso",
            "gain": "ganar musculo",
        }

        return SYSTEM_PROMPT.format(
            age=profile["age"],
            height_cm=profile["height_cm"],
            sex="hombre" if profile["sex"] == "male" else "mujer",
            goal=goal_map.get(profile["goal"], profile["goal"]),
            diet_type=profile["diet_type"],
            target_calories=target_calories,
            target_protein=target_protein,
            target_carbs=target_carbs,
            target_fat=target_fat,
            today=today.strftime("%d/%m/%Y"),
            calories_today=nutrition["calories"],
            protein_today=nutrition["protein_g"],
            meal_count=len(nutrition["meals"]),
            steps_today=f"{steps:,}" if steps else "sin datos",
            current_weight=current_weight,
            meals_detail=meals_detail,
        )

    def chat(self, user_message: str) -> str:
        """Send a message to the AI coach and get a response."""
        if not self.api_key:
            return (
                "No tengo acceso a la IA en este momento (API key no configurada). "
                "Pero puedo ayudarte con los comandos: /resumen, /peso, /entreno"
            )

        system_prompt = self._build_context()

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history[-12:])
        messages.append({"role": "user", "content": user_message})

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 800,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"].strip()

            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": reply})

            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

            return reply

        except requests.exceptions.Timeout:
            return "El coach esta tardando en responder. Puedes repetir la pregunta?"
        except requests.exceptions.ConnectionError:
            return "No puedo conectar con el servidor de IA ahora mismo."
        except Exception as e:
            logger.exception("AI chat error")
            return f"Error al contactar con la IA. Intenta de nuevo en un momento."
