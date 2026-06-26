"""MiSalud — Configuración central."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PHOTOS_DIR = DATA_DIR / "photos"
DB_PATH = DATA_DIR / "misalud.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

# ── Database ────────────────────────────────────────
DATABASE_URL = os.getenv("MISALUD_DATABASE_URL", f"sqlite:///{DB_PATH}")

DATABASE_URL = DATABASE_URL.replace("sqlite:///data/", f"sqlite:///{DATA_DIR}/")

# ── Google APIs ─────────────────────────────────────
GOOGLE_TOKEN_PATH = Path.home() / ".hermes" / "google_token.json"

# Google Fit scopes
GOOGLE_FIT_SCOPES = [
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
]

# ── Telegram ────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("MISALUD_TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("MISALUD_TELEGRAM_CHAT_ID", "")

# ── IA / Visión ─────────────────────────────────────
VISION_MODEL = "qwen3-vl:latest"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── Perfil del usuario ──────────────────────────────
USER_PROFILE = {
    "name": "Youssef",
    "sex": "male",
    "age": 42,
    "height_cm": 178,
    "activity_level": "moderate",
    "goal": "maintenance",
    "diet_type": "mediterranean",
    "allergies": [],
    "dislikes": [],
    "meals_per_day": 4,
}
