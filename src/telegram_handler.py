"""Telegram bot handler for MiSalud.

Receives food photos → AI analysis → SQLite storage.
Commands: /start, /ayuda, /resumen, /peso, /entreno
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

from .config import TELEGRAM_BOT_TOKEN, PHOTOS_DIR, USER_PROFILE
from .vision import FoodAnalyzer
from .repository import MiSaludRepo
from .chat_ai import NutritionCoach

logger = logging.getLogger(__name__)


# ── Keyboard ─────────────────────────────────────────

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Resumen"), KeyboardButton("⚖️ Peso")],
        [KeyboardButton("🍽️ Comida"), KeyboardButton("🏋️ Entreno")],
        [KeyboardButton("🧠 Coach"), KeyboardButton("📸 Analizar comida")],
        [KeyboardButton("❓ Ayuda")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Elige una opción o escríbeme...",
)

WELCOME_MSG = (
    "🥗 *MiSalud Bot*\\n\\n"
    "Envíame una foto de tu comida y la analizaré con IA para estimar "
    "calorías, proteínas, carbohidratos y grasas.\\n\\n"
    "🧠 *Háblame!* Soy tu coach nutricional con IA. "
    "Pregúntame lo que quieras sobre alimentación, recetas, entrenamiento...\\n\\n"
    "📸 *Comandos:*\\n"
    "/resumen — Resumen nutricional del día\\n"
    "/peso <kg> — Registra tu peso (ej: /peso 85.5)\\n"
    "/entreno <tipo> <minutos> — Registra entrenamiento\\n"
    "/coach <pregunta> — Habla con el nutricionista IA\\n"
    "/reset — Reinicia la memoria del coach\\n"
    "/menu — Mostrar/ocultar teclado\\n"
    "/ayuda — Esta ayuda"
)


def _format_nutrition_result(result: dict) -> str:
    """Build a Telegram message from food analysis results."""
    foods_text = "\n".join(
        f"• *{f['name']}*: {f.get('calories', 0):.0f} kcal "
        f"(P:{f.get('protein_g', 0):.0f}g C:{f.get('carbs_g', 0):.0f}g G:{f.get('fat_g', 0):.0f}g)"
        for f in result.get("foods", [])
    )

    confidence_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(
        result.get("confidence", "medium"), "🟡"
    )

    totals = result.get("totals", {})
    msg = (
        f"{confidence_emoji} *Análisis Nutricional — {result.get('meal_type', 'Comida')}*\n\n"
        f"*Alimentos detectados:*\n{foods_text}\n\n"
        f"📊 *Totales:*\n"
        f"🔥 Calorías: *{totals.get('calories', 0):.0f} kcal*\n"
        f"💪 Proteínas: *{totals.get('protein_g', 0):.0f} g*\n"
        f"🍚 Carbohidratos: *{totals.get('carbs_g', 0):.0f} g*\n"
        f"🧈 Grasas: *{totals.get('fat_g', 0):.0f} g*"
    )

    if totals.get("fiber_g"):
        msg += f"\n🌿 Fibra: *{totals['fiber_g']:.0f} g*"

    if result.get("notes"):
        msg += f"\n\n💡 {result['notes']}"

    return msg


# ── Bot class ────────────────────────────────────────


class MiSaludBot:
    """Telegram bot for MiSalud food & fitness tracking."""

    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.app: Optional[Application] = None
        self.analyzer = FoodAnalyzer()
        self.coach = NutritionCoach()

    # ── /start, /ayuda ────────────────────────────

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            WELCOME_MSG, parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_KEYBOARD,
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            WELCOME_MSG, parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_KEYBOARD,
        )

    # ── /menu ──────────────────────────────────────

    async def menu_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle keyboard on/off."""
        await update.message.reply_text(
            "📱 *Menú de MiSalud*\n\n"
            "Usa los botones de abajo para navegar rápidamente.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_KEYBOARD,
        )

    # ── Button helpers ────────────────────────────

    async def _peso_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "⚖️ *Registrar peso*\n\n"
            "Escribe tu peso en kg. Ejemplo: `85.5`\n"
            "O usa el comando: `/peso 85.5`",
            parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KEYBOARD,
        )

    async def _entreno_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🏋️ *Registrar entrenamiento*\n\n"
            "Escribe tipo y duración. Ejemplo: `running 45`\n"
            "O usa: `/entreno running 45`",
            parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KEYBOARD,
        )

    async def _coach_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🧠 *YhasSalud Coach*\n\n"
            "Pregúntame sobre nutrición, recetas, entrenamiento...\n"
            "• ¿Qué puedo cenar hoy?\n"
            "• Dame una receta alta en proteínas\n"
            "• ¿Estoy comiendo bien esta semana?",
            parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KEYBOARD,
        )

    async def _photo_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📸 *Analizar comida*\n\n"
            "Haz una foto a tu plato y envíamela. "
            "La IA identificará los alimentos, calorías y macros.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KEYBOARD,
        )

    async def _comida_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🍽️ *Registrar comida por texto*\n\n"
            "Describe lo que comiste. Ejemplo:\n"
            "`pollo con arroz y ensalada`\n\n"
            "O usa el comando: `/comida 2 huevos, pan, cafe`",
            parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KEYBOARD,
        )

    # ── /resumen ───────────────────────────────────

    async def resumen_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show today's nutritional summary from SQLite."""
        today = datetime.now().date()

        with MiSaludRepo() as repo:
            nutrition = repo.daily_nutrition(today)
            goal = repo.get_active_goal()

        if not nutrition["meals"]:
            await update.message.reply_text("📭 No hay comidas registradas hoy.\nEnvía una foto de tu plato.")
            return

        total_cal = nutrition["calories"]
        msg = (
            "📊 *Resumen Nutricional de Hoy*\n\n"
            f"🔥 Calorías: *{total_cal:.0f} kcal*"
        )
        if goal and goal.daily_calories:
            remaining = goal.daily_calories - total_cal
            sign = "+" if remaining >= 0 else ""
            msg += f"  (objetivo: {goal.daily_calories} → {sign}{remaining:.0f})"

        msg += (
            f"\n💪 Proteínas: *{nutrition['protein_g']:.0f} g*"
            f"\n🍚 Carbohidratos: *{nutrition['carbs_g']:.0f} g*"
            f"\n🧈 Grasas: *{nutrition['fat_g']:.0f} g*"
            f"\n🌿 Fibra: *{nutrition['fiber_g']:.0f} g*"
            f"\n\n🍽️ Comidas registradas: *{len(nutrition['meals'])}*"
        )

        # List meals
        for m in nutrition["meals"]:
            foods_short = ", ".join(f["name"] for f in m["foods"][:3])
            if len(m["foods"]) > 3:
                foods_short += f" +{len(m['foods']) - 3} más"
            msg += f"\n  • {m['type']}: {foods_short} ({m['total_calories']:.0f} kcal)"

        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    # ── /peso ──────────────────────────────────────

    async def peso_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Record weight: /peso 85.5 [nota opcional]"""
        if not context.args:
            await update.message.reply_text(
                "⚖️ Registra tu peso así: `/peso 85.5`\n"
                "Opcional: `/peso 85.5 en ayunas`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        try:
            peso = float(context.args[0].replace(",", "."))
        except ValueError:
            await update.message.reply_text(
                "❌ Peso inválido. Ejemplo: `/peso 85.5`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        nota = " ".join(context.args[1:]) if len(context.args) > 1 else ""

        with MiSaludRepo() as repo:
            repo.log_weight(peso, notes=nota if nota else None)

        await update.message.reply_text(
            f"✅ Peso registrado: *{peso} kg*\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /entreno ───────────────────────────────────

    async def entreno_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Record workout: /entreno <tipo> <minutos> [nota]"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "🏋️ Registra un entreno: `/entreno <tipo> <minutos> [nota]`\n"
                "Ejemplo: `/entreno running 45 5km ritmo suave`\n"
                "Ejemplo: `/entreno gimnasio 60 pecho y tríceps`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        tipo = context.args[0]
        try:
            duracion = int(context.args[1])
        except ValueError:
            await update.message.reply_text(
                "❌ Duración inválida. Ejemplo: `/entreno gym 60`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        nota = " ".join(context.args[2:]) if len(context.args) > 2 else ""

        with MiSaludRepo() as repo:
            repo.add_workout(
                type_name=tipo.capitalize(),
                duration_min=duracion,
                notes=nota if nota else None,
            )

        await update.message.reply_text(
            f"✅ Entreno registrado: *{tipo}* — *{duracion} min*\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /comida ──────────────────────────────────────

    async def comida_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Register a meal by text description. Uses DeepSeek to parse foods."""
        if not context.args:
            await update.message.reply_text(
                "🍽️ *Registrar comida por texto*\n\n"
                "Describe lo que comiste y la IA lo analizará. Ejemplos:\n"
                "`/comida 2 huevos fritos, pan integral, café con leche`\n"
                "`/comida ensalada de pollo con aguacate y nueces`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        user_text = " ".join(context.args)
        await update.message.reply_chat_action("typing")

        # Parse food via DeepSeek
        try:
            result = self.coach._parse_meal_text(user_text)
        except Exception as e:
            await update.message.reply_text(f"❌ Error al analizar: {e}")
            return

        if not result or not result.get("foods"):
            await update.message.reply_text(
                "❌ No pude identificar los alimentos. Intenta con más detalle."
            )
            return

        # Save to database
        try:
            with MiSaludRepo() as repo:
                meal = repo.add_meal(
                    meal_type_name=result.get("meal_type", "Comida"),
                    eaten_at=datetime.now(),
                    confidence="medium",
                )
                for food in result.get("foods", []):
                    repo.add_food_to_meal(meal.id, food)
        except Exception as e:
            logger.exception("Failed to save meal")
            await update.message.reply_text(f"⚠️ Error al guardar: {e}")
            return

        # Build response
        foods_text = "\n".join(
            f"• *{f['name']}*: {f.get('calories', 0):.0f} kcal"
            for f in result["foods"]
        )
        totals = result.get("totals", {})
        msg = (
            f"✅ *{result.get('meal_type', 'Comida')} guardada*\n\n"
            f"{foods_text}\n\n"
            f"📊 *Totales:*\n"
            f"🔥 Calorías: *{totals.get('calories', 0):.0f} kcal*\n"
            f"💪 Proteínas: *{totals.get('protein_g', 0):.0f} g*\n"
            f"🍚 Carbohidratos: *{totals.get('carbs_g', 0):.0f} g*\n"
            f"🧈 Grasas: *{totals.get('fat_g', 0):.0f} g*"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    # ── Photo handler ──────────────────────────────

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive food photo, analyze with AI, store in SQLite."""
        user = update.message.from_user

        # Download photo
        photo_file = await update.message.photo[-1].get_file()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        photo_path = PHOTOS_DIR / f"{timestamp}_{user.id}.jpg"
        await photo_file.download_to_drive(photo_path)

        await update.message.reply_text("🔍 *Analizando tu comida con IA...*", parse_mode=ParseMode.MARKDOWN)

        # Analyze
        result = self.analyzer.analyze(photo_path)

        if "error" in result:
            await update.message.reply_text(
                f"❌ Error al analizar la foto: {result['error']}\n\n"
                "La foto se ha guardado. Intenta de nuevo más tarde."
            )
            return

        # Save to SQLite
        try:
            with MiSaludRepo() as repo:
                meal = repo.add_meal(
                    meal_type_name=result.get("meal_type", "Comida"),
                    eaten_at=datetime.now(),
                    photo_path=str(photo_path),
                    confidence=result.get("confidence"),
                    notes=result.get("notes"),
                )
                for food in result.get("foods", []):
                    repo.add_food_to_meal(meal.id, food)
        except Exception as e:
            logger.exception("Failed to save meal to database")
            await update.message.reply_text(
                f"⚠️ Análisis completado pero error al guardar: {e}"
            )
            return

        # Send nutrition summary
        msg = _format_nutrition_result(result)
        msg += f"\n\n📸 _Foto guardada: {photo_path.name}_"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    # ── /editar ──────────────────────────────────────

    async def editar_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Edit the most recent meal: /editar pollo → atun"""
        if not context.args:
            await update.message.reply_text(
                "✏️ *Editar última comida*\n\n"
                "Corrige la última comida registrada. Ejemplo:\n"
                "`/editar pollo → atun, mayonesa → yogur`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        correction = " ".join(context.args)
        with MiSaludRepo() as repo:
            from src.database import SessionLocal
            db = SessionLocal()
            last_meal = db.query(db.__class__).get(1)  # placeholder
            from src.models import Meal
            last_meal = db.query(Meal).order_by(Meal.id.desc()).first()
            if not last_meal:
                await update.message.reply_text("❌ No hay comidas para editar.")
                db.close()
                return

            # Use DeepSeek to parse the correction and update foods
            try:
                prompt = f"""El usuario quiere corregir la comida. Descripcion original: {last_meal.foods_list}. Correccion: {correction}. Devuelve SOLO un JSON con los alimentos corregidos usando este esquema: {{"foods":[{{"name":"...","portion_g":100,"calories":200,"protein_g":10,"carbs_g":20,"fat_g":5,"fiber_g":2}}]}}"""
                resp = __import__('requests').post(
                    f"{self.coach.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.coach.api_key}", "Content-Type": "application/json"},
                    json={"model": self.coach.model, "messages": [{"role":"user","content":prompt}], "temperature":0.1, "max_tokens":600},
                    timeout=30,
                )
                data = resp.json()["choices"][0]["message"]["content"].strip()
                import re, json
                m = re.search(r'\{[\s\S]*\}', data)
                if m:
                    new_foods = json.loads(m.group(0)).get("foods", [])
                    if new_foods:
                        # Delete old foods
                        from src.models import MealFood
                        db.query(MealFood).filter_by(meal_id=last_meal.id).delete()
                        # Add new foods
                        for f in new_foods:
                            mf = MealFood(meal_id=last_meal.id, **{k: v for k, v in f.items() if hasattr(MealFood, k)})
                            db.add(mf)
                        db.commit()
                        total = sum(f.get("calories", 0) for f in new_foods)
                        db.close()
                        await update.message.reply_text(
                            f"✅ Comida actualizada: {', '.join(f['name'] for f in new_foods)}\n"
                            f"🔥 Nuevo total: {total:.0f} kcal"
                        )
                        return
            except Exception as e:
                pass
            finally:
                db.close()

        await update.message.reply_text("❌ No pude procesar la corrección. Intenta: `/editar pollo → atun`")

    # ── /coach ─────────────────────────────────────

    async def coach_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Talk to the AI nutrition coach."""
        if not context.args:
            await update.message.reply_text(
                "🧠 *YhasSalud Coach* — tu nutricionista IA\n\n"
                "Puedes preguntarme lo que quieras:\n"
                "• ¿Cuántas calorías tiene una manzana?\n"
                "• Dame una receta rica en proteínas\n"
                "• ¿Qué puedo cenar hoy?\n"
                "• ¿Estoy comiendo bien esta semana?\n\n"
                "O simplemente háblame sin el comando /coach.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        user_msg = " ".join(context.args)
        await update.message.reply_chat_action("typing")
        reply = self.coach.chat(user_msg)
        await update.message.reply_text(reply)

    async def reset_coach_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reset conversation history."""
        self.coach.conversation_history = []
        await update.message.reply_text("🧠 Memoria del coach reiniciada. ¡Empezamos de cero!")

    # ── Text handler (AI chat) ─────────────────────

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command text — keyboard buttons or AI chat."""
        text = update.message.text.strip()

        # ── Keyboard button routing ──────────────────
        button_handlers = {
            "📊 Resumen": self.resumen_cmd,
            "⚖️ Peso": self._peso_button,
            "🍽️ Comida": self._comida_button,
            "🏋️ Entreno": self._entreno_button,
            "🧠 Coach": self._coach_button,
            "📸 Analizar comida": self._photo_button,
            "❓ Ayuda": self.help_cmd,
        }

        if text in button_handlers:
            await button_handlers[text](update, context)
            return

        # Quick greetings bypass AI
        if text.lower() in ["hola", "buenas", "hey", "hi", "buenos dias", "buenas tardes"]:
            await update.message.reply_text(
                "👋 ¡Hola Youssef! Soy tu coach de MiSalud. "
                "Pregúntame lo que quieras sobre nutrición, entrenamiento, "
                "o envíame una foto de tu plato para analizarla."
            )
            return

        # Everything else → AI coach
        await update.message.reply_chat_action("typing")
        reply = self.coach.chat(text)
        await update.message.reply_text(reply)

    # ── Lifecycle ──────────────────────────────────

    def build_app(self) -> Application:
        """Build and configure the bot application."""
        if not self.token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is not set. "
                "Create a bot with @BotFather and set MISALUD_TELEGRAM_TOKEN in .env"
            )

        app = Application.builder().token(self.token).build()

        # Commands
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("ayuda", self.help_cmd))
        app.add_handler(CommandHandler("help", self.help_cmd))
        app.add_handler(CommandHandler("resumen", self.resumen_cmd))
        app.add_handler(CommandHandler("peso", self.peso_cmd))
        app.add_handler(CommandHandler("entreno", self.entreno_cmd))
        app.add_handler(CommandHandler("comida", self.comida_cmd))
        app.add_handler(CommandHandler("editar", self.editar_cmd))
        app.add_handler(CommandHandler("coach", self.coach_cmd))
        app.add_handler(CommandHandler("reset", self.reset_coach_cmd))
        app.add_handler(CommandHandler("menu", self.menu_cmd))

        # Photo handler
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

        # Text fallback (must be last)
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        return app

    async def run(self):
        """Start the bot (blocking polling loop)."""
        self.app = self.build_app()
        logger.info("Starting MiSalud Telegram bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info("Bot is running. Press Ctrl+C to stop.")

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Shutting down bot...")
        finally:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()

    def run_sync(self):
        """Synchronous entry point."""
        asyncio.run(self.run())
