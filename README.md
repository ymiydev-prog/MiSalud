# MiSalud — Dashboard de Nutrición y Entrenamiento con IA

Sistema completo de tracking de comidas y entrenamiento con análisis por IA.

## Funcionalidades

- 📸 **Fotos de comida por Telegram** → IA analiza calorías y macros
- 🏃 **Google Fit sync** → pasos, sueño, peso, actividad
- 📊 **Dashboard Streamlit** → tendencias, KPIs, gráficos
- 🍽️ **Plan de dieta semanal** → generado por IA cada domingo
- 📱 **Export a Google Sheets** → vista móvil opcional

## Arquitectura

```
Telegram Bot → AI Vision → SQLite ← Google Fit API
                              ↓
                         Streamlit Dashboard
                              ↓ (opcional)
                         Google Sheets (móvil)
```

## Requisitos

- Python 3.12+
- Ollama con qwen2.5vl (para análisis de comida)
- Google OAuth configurado (para Google Fit)
- Bot de Telegram (crear con @BotFather)

## Instalación

```bash
cd MiSalud
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "from src.database import init_db; init_db()"
```

O usa el script de setup:

```bash
python scripts/setup.py
```

## Configuración

Copia `.env.example` a `.env` y configura:

```bash
MISALUD_TELEGRAM_TOKEN=tu_token_del_bot
```

El token de Google se lee de `~/.hermes/google_token.json` (configurado vía google-workspace skill).

Para Google Fit necesitas añadir estos scopes al token:
- `https://www.googleapis.com/auth/fitness.activity.read`
- `https://www.googleapis.com/auth/fitness.body.read`
- `https://www.googleapis.com/auth/fitness.heart_rate.read`
- `https://www.googleapis.com/auth/fitness.sleep.read`

## Uso

### Dashboard

```bash
streamlit run src/dashboard.py
```

Abre http://localhost:8501

### Bot de Telegram

```bash
python -c "from src.telegram_handler import MiSaludBot; MiSaludBot().run_sync()"
```

### Comandos del Bot

| Comando | Descripción |
|---------|-------------|
| 📸 Enviar foto | Analiza la comida con IA (qwen3-vl + DeepSeek) |
| `/comida <texto>` | Registra comida por descripción de texto |
| `/resumen` | Resumen nutricional del día |
| `/peso 85.5` | Registra tu peso |
| `/entreno running 45` | Registra un entrenamiento |
| `/coach <pregunta>` | Habla con el nutricionista IA |
| `/menu` | Muestra el teclado de botones |
| `/ayuda` | Muestra la ayuda |

## Cron Jobs

Configura estos cron jobs en Hermes:

| Job | Schedule | Descripción |
|-----|----------|-------------|
| `misalud-sync-fit` | Diario 08:00 | Sincroniza Google Fit → SQLite |
| `misalud-daily-summary` | Diario 21:00 | Resumen diario de nutrición |
| `misalud-weekly-plan` | Domingo 10:00 | Genera plan de dieta semanal |

```bash
hermes cronjob create \
  --schedule "0 8 * * *" \
  --prompt "Ejecuta python scripts/sync_fit.py" \
  --name "misalud-sync-fit"
```

## Modelo de Datos

SQLite con 11 tablas relacionales:

- `meals` → `meal_foods` (una comida tiene N alimentos)
- `workouts` → `workout_types`
- `weight_logs` — registro de peso
- `fit_data` — datos de Google Fit (una fila por día)
- `goals` — objetivos activos
- `meal_plans` → `plan_meals` — planes de dieta semanales
- `weekly_summaries` — resúmenes precalculados

## Estructura del Proyecto

```
MiSalud/
├── src/
│   ├── config.py          # Configuración
│   ├── database.py        # Engine + init_db
│   ├── models.py          # SQLAlchemy models (11 tablas)
│   ├── repository.py      # Capa de acceso a datos
│   ├── vision.py          # Análisis de comida (qwen2.5vl)
│   ├── google_fit.py      # Google Fit REST API
│   ├── meal_planner.py    # Generador de dietas con IA
│   ├── telegram_handler.py # Bot de Telegram
│   ├── dashboard.py       # Streamlit dashboard
│   └── sheets_export.py   # Export a Google Sheets
├── scripts/
│   ├── setup.py           # Instalación rápida
│   ├── sync_fit.py        # Cron: Google Fit → SQLite
│   ├── daily_summary.py   # Cron: resumen diario
│   ├── weekly_plan.py     # Cron: plan semanal
│   └── export_to_sheets.py # Export a Sheets (móvil)
├── data/                  # SQLite DB + fotos (gitignored)
├── requirements.txt
├── .env.example
└── README.md
```
