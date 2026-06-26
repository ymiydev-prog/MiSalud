"""MiSalud Dashboard — Streamlit web app.

Visualizes nutrition, fitness, and meal plan data from SQLite.
Run with: streamlit run src/dashboard.py
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta

# Add project root to path (needed when run as streamlit run src/dashboard.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.database import SessionLocal
from src.repository import MiSaludRepo
from src.config import USER_PROFILE

# ── Page Config ──────────────────────────────────
st.set_page_config(
    page_title="MiSalud Dashboard",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🥗 MiSalud Dashboard")
st.caption("Nutrición · Entrenamiento · Bienestar")

# ── Load data (cached for 2 minutes) ────────────
@st.cache_data(ttl=120)
def load_kpi(target_date: date):
    with MiSaludRepo() as repo:
        return repo.dashboard_kpi(target_date)


@st.cache_data(ttl=120)
def load_calorie_trend(days: int = 30):
    with MiSaludRepo() as repo:
        return repo.daily_calorie_trend(days)


@st.cache_data(ttl=120)
def load_weight_trend(days: int = 90):
    with MiSaludRepo() as repo:
        return repo.get_weight_trend(days)


@st.cache_data(ttl=300)
def load_fit_range(start: date, end: date):
    with MiSaludRepo() as repo:
        data = repo.get_fit_range(start, end)
        return [
            {
                "date": d.date.isoformat(),
                "steps": d.steps,
                "sleep_hours": d.sleep_hours,
                "active_calories": d.active_calories,
                "active_minutes": d.active_minutes,
                "weight_kg": d.weight_kg,
            }
            for d in data
        ]


@st.cache_data(ttl=300)
def load_weekly_plan():
    """Load the most recent or current week's meal plan."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    with MiSaludRepo() as repo:
        plan = repo.get_weekly_plan(week_start)
        if not plan:
            # Try previous week
            plan = repo.get_weekly_plan(week_start - timedelta(days=7))
        return plan


@st.cache_data(ttl=300)
def load_workouts(start: date, end: date):
    with MiSaludRepo() as repo:
        workouts = repo.get_workouts_range(start, end)
        return [
            {
                "date": w.started_at.strftime("%Y-%m-%d"),
                "type": w.workout_type.name,
                "duration": w.duration_min,
                "calories": w.calories_burned,
                "notes": w.notes,
            }
            for w in workouts
        ]


# ── Sidebar ──────────────────────────────────────
st.sidebar.header("📅 Filtros")
today = date.today()

date_range = st.sidebar.date_input(
    "Rango de fechas",
    value=(today - timedelta(days=7), today),
    max_value=today,
)

if len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = today - timedelta(days=7)
    end_date = today

# ── Load all data ────────────────────────────────
kpi = load_kpi(today)
cal_trend = load_calorie_trend(30)
weight_trend = load_weight_trend(90)
fit_data = load_fit_range(start_date, end_date)
plan = load_weekly_plan()
workouts = load_workouts(start_date, end_date)

# ── KPI Row ──────────────────────────────────────
st.header(f"📊 Hoy — {today.strftime('%d/%m/%Y')}")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    cals = kpi["calories"]
    goal_cals = kpi.get("goal_calories")
    delta = None
    if goal_cals:
        delta = f"{cals - goal_cals:+.0f} vs objetivo"
    st.metric("🔥 Calorías", f"{cals:.0f} kcal", delta=delta)

with col2:
    st.metric("💪 Proteínas", f"{kpi['protein_g']:.0f} g")

with col3:
    st.metric("🍚 Carbohidratos", f"{kpi['carbs_g']:.0f} g")

with col4:
    st.metric("🧈 Grasas", f"{kpi['fat_g']:.0f} g")

with col5:
    steps = kpi.get("steps", 0)
    st.metric("👣 Pasos", f"{steps:,}" if steps else "—")

# Second KPI row
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("🍽️ Comidas", kpi["meal_count"])

with col2:
    sleep_h = kpi.get("sleep_hours")
    st.metric("😴 Sueño", f"{sleep_h}h" if sleep_h else "—")

with col3:
    active_cal = kpi.get("active_calories", 0)
    st.metric("🔥 Activas", f"{active_cal}" if active_cal else "—")

with col4:
    active_min = kpi.get("active_minutes", 0)
    st.metric("⏱️ Min. activos", f"{active_min}" if active_min else "—")

with col5:
    st.metric("🎯 Objetivo", f"{goal_cals} kcal" if goal_cals else "—")

# ── Today's meals detail ─────────────────────────
if kpi["meals"]:
    with st.expander(f"🍽️ Comidas de hoy ({len(kpi['meals'])})", expanded=False):
        for m in kpi["meals"]:
            st.markdown(f"**{m['type']}** ({m['time']}) — {m['total_calories']:.0f} kcal")
            if m.get("confidence"):
                conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(m["confidence"], "")
                st.caption(f"Confianza IA: {conf_emoji} {m['confidence']}")
            for f in m["foods"]:
                st.text(
                    f"  • {f['name']} ({f.get('portion_g', '?')}g): "
                    f"{f.get('calories', 0):.0f} kcal | "
                    f"P:{f.get('protein_g', 0):.0f}g "
                    f"C:{f.get('carbs_g', 0):.0f}g "
                    f"G:{f.get('fat_g', 0):.0f}g"
                )

# ── Charts ───────────────────────────────────────
st.header("📈 Tendencias")

tab1, tab2, tab3, tab4 = st.tabs(["🍽️ Calorías", "⚖️ Peso", "🏃 Actividad", "📋 Plan"])

with tab1:
    if cal_trend:
        df = pd.DataFrame(cal_trend)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        fig = px.bar(
            df, x="date", y="calories",
            title="Calorías Diarias (últimos 30 días)",
            color="calories",
            color_continuous_scale="RdYlGn_r",
        )
        if goal_cals:
            fig.add_hline(
                y=goal_cals, line_dash="dash", line_color="red",
                annotation_text=f"Objetivo: {goal_cals} kcal",
            )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Registra comidas para ver la tendencia de calorías.")

with tab2:
    if weight_trend:
        df_w = pd.DataFrame(weight_trend)
        df_w["date"] = pd.to_datetime(df_w["date"])
        df_w = df_w.sort_values("date")

        fig = px.line(
            df_w, x="date", y="weight_kg",
            title="Evolución del Peso",
            markers=True,
        )
        fig.update_traces(line=dict(color="#FF6B6B", width=3))
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Registra tu peso con /peso en Telegram.")

with tab3:
    col_a, col_b = st.columns(2)

    with col_a:
        if fit_data:
            df_fit = pd.DataFrame(fit_data)
            if "date" in df_fit.columns and df_fit["steps"].sum() > 0:
                df_fit["date"] = pd.to_datetime(df_fit["date"])
                fig = px.bar(df_fit, x="date", y="steps", title="Pasos Diarios")
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin datos de pasos. Sincroniza Google Fit.")
        else:
            st.info("Sin datos de Google Fit.")

    with col_b:
        if fit_data:
            df_fit = pd.DataFrame(fit_data)
            if "sleep_hours" in df_fit.columns and df_fit["sleep_hours"].notna().any():
                df_fit["date"] = pd.to_datetime(df_fit["date"])
                fig = px.bar(
                    df_fit.dropna(subset=["sleep_hours"]),
                    x="date", y="sleep_hours",
                    title="Horas de Sueño",
                    color="sleep_hours",
                )
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

    # Workouts this week
    if workouts:
        st.subheader("🏋️ Entrenamientos")
        df_wk = pd.DataFrame(workouts)
        st.dataframe(df_wk, use_container_width=True, hide_index=True)

with tab4:
    if plan and plan.get("days"):
        st.subheader(f"📋 Plan de Dieta — Semana del {plan['week_start']}")

        # Build a summary table
        rows = []
        day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        day_cals = []
        for day_idx in sorted(plan["days"].keys()):
            day_data = plan["days"][day_idx]
            day_cal = sum(m.get("calories", 0) or 0 for m in day_data["meals"])
            day_prot = sum(m.get("protein_g", 0) or 0 for m in day_data["meals"])
            day_carbs = sum(m.get("carbs_g", 0) or 0 for m in day_data["meals"])
            day_fat = sum(m.get("fat_g", 0) or 0 for m in day_data["meals"])
            day_cals.append({
                "day": day_data["day"],
                "calories": day_cal,
                "protein": day_prot,
                "carbs": day_carbs,
                "fat": day_fat,
            })

            for m in day_data["meals"]:
                rows.append({
                    "Día": day_data["day"],
                    "Comida": m["meal_type"],
                    "Alimentos": m["foods"][:80] + ("..." if len(m.get("foods", "")) > 80 else ""),
                    "kcal": m.get("calories", 0),
                    "Proteína": m.get("protein_g", 0),
                })

        # Bar chart: calories per day
        df_days = pd.DataFrame(day_cals)
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Calorías", x=df_days["day"], y=df_days["calories"], marker_color="#FF6B6B"))
        fig.add_trace(go.Bar(name="Proteínas", x=df_days["day"], y=df_days["protein"], marker_color="#4ECDC4"))
        fig.add_trace(go.Bar(name="Carbohidratos", x=df_days["day"], y=df_days["carbs"], marker_color="#FFE66D"))
        fig.update_layout(barmode="group", title="Macros por Día (Plan)", height=350)
        st.plotly_chart(fig, use_container_width=True)

        # Full table
        df_plan = pd.DataFrame(rows)
        st.dataframe(df_plan, use_container_width=True, hide_index=True)
    else:
        st.info("Genera un plan de dieta semanal para verlo aquí. El cron job del domingo lo crea automáticamente.")

# ── Footer ───────────────────────────────────────
st.divider()
col1, col2 = st.columns(2)
with col1:
    st.caption(f"MiSalud v1.0 · {USER_PROFILE['name']} · {USER_PROFILE['age']} años · {USER_PROFILE['height_cm']} cm")
with col2:
    st.caption(f"Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
