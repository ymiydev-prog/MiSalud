"""MiSalud Dashboard — Full nutrition & fitness dashboard.

Fitia-style web dashboard. Run with: streamlit run src/dashboard.py
Opens at http://localhost:8501
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from src.repository import MiSaludRepo
from src.database import SessionLocal
from src import models
from src.config import USER_PROFILE

# ── Config ──────────────────────────────────────
st.set_page_config(page_title="MiSalud", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    .kpi-card { background: #1e1e2e; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid #313244; }
    .kpi-value { font-size: 28px; font-weight: 700; color: #f5f5f5; }
    .kpi-label { font-size: 13px; color: #a6adc8; margin-top: 4px; }
    .kpi-delta { font-size: 12px; margin-top: 2px; }
    .meal-card { background: #1e1e2e; border-radius: 10px; padding: 12px 16px; margin: 8px 0; border-left: 4px solid #f38ba8; }
    .meal-card-protein { border-left-color: #a6e3a1; }
    .goal-bar bg { background: #313244; border-radius: 8px; height: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Data loading ────────────────────────────────
@st.cache_data(ttl=120)
def load_kpi(d):
    with MiSaludRepo() as r: return r.dashboard_kpi(d)

@st.cache_data(ttl=120)
def load_cal_trend(d):
    with MiSaludRepo() as r: return r.daily_calorie_trend(d)

@st.cache_data(ttl=120)
def load_weight(d):
    with MiSaludRepo() as r: return r.get_weight_trend(d)

@st.cache_data(ttl=300)
def load_fit(start, end):
    with MiSaludRepo() as r:
        data = r.get_fit_range(start, end)
        return [{"date": d.date.isoformat(), "steps": d.steps, "sleep": d.sleep_hours,
                 "active_cal": d.active_calories, "active_min": d.active_minutes, "weight": d.weight_kg} for d in data]

@st.cache_data(ttl=300)
def load_plan():
    today = date.today()
    ws = today - timedelta(days=today.weekday())
    with MiSaludRepo() as r:
        plan = r.get_weekly_plan(ws)
        if not plan: plan = r.get_weekly_plan(ws - timedelta(days=7))
        return plan

@st.cache_data(ttl=120)
def load_meals(d):
    with MiSaludRepo() as r: return r.daily_nutrition(d)

# ── Sidebar ─────────────────────────────────────
with st.sidebar:
    st.markdown("## 🥗 MiSalud")
    st.caption(f"{USER_PROFILE['name']} · {USER_PROFILE['age']}a · {USER_PROFILE['height_cm']}cm")
    
    today = date.today()
    date_range = st.date_input("Rango", value=(today - timedelta(days=7), today), max_value=today)
    start_dt, end_dt = date_range if len(date_range) == 2 else (today - timedelta(days=7), today)
    
    st.divider()
    st.caption(f"SQLite · {USER_PROFILE['goal']}")
    if st.button("🔄 Refrescar"):
        st.cache_data.clear()

# ── Tabs ────────────────────────────────────────
tab_overview, tab_meals, tab_weight, tab_fit, tab_plan, tab_goals = st.tabs(
    ["📊 Visión General", "🍽️ Comidas", "⚖️ Peso", "🏃 Fit", "📋 Plan", "🎯 Objetivos"]
)

# ════════════════════════════════════════════════
# TAB 1: OVERVIEW
# ════════════════════════════════════════════════
with tab_overview:
    kpi = load_kpi(today)
    cal_trend = load_cal_trend(30)
    
    st.subheader(f"📊 Hoy — {today.strftime('%d/%m/%Y')}")
    
    cols = st.columns(6)
    goal_cal = kpi.get("goal_calories")
    for i, (label, val, delta, fmt) in enumerate([
        ("Calorías", kpi["calories"], f"{kpi['calories'] - goal_cal:+.0f}" if goal_cal else None, "{:.0f}"),
        ("Proteínas", kpi["protein_g"], None, "{:.0f}g"),
        ("Carbos", kpi["carbs_g"], None, "{:.0f}g"),
        ("Grasas", kpi["fat_g"], None, "{:.0f}g"),
        ("Pasos", kpi.get("steps", 0), None, "{:,.0f}"),
        ("Comidas", kpi["meal_count"], None, "{:.0f}"),
    ]):
        with cols[i]:
            color = "#f5f5f5"
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value" style="color: {color}">{fmt.format(val)}</div>
                <div class="kpi-delta">{('' if delta is None else ('🔺 ' + delta))}</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Calorie chart
    if cal_trend:
        df_cal = pd.DataFrame(cal_trend)
        df_cal["date"] = pd.to_datetime(df_cal["date"])
        fig = px.bar(df_cal, x="date", y="calories", title="Calorías Diarias (30 días)",
                     color="calories", color_continuous_scale="RdYlGn_r")
        if goal_cal:
            fig.add_hline(y=goal_cal, line_dash="dash", line_color="#f38ba8",
                          annotation_text=f"Objetivo {goal_cal} kcal")
        fig.update_layout(height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#cdd6f4", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
    
    # Today's meals detail
    st.subheader("🍽️ Comidas de Hoy")
    meals = load_meals(today)
    if meals["meals"]:
        cols = st.columns(min(len(meals["meals"]), 4))
        for i, m in enumerate(meals["meals"]):
            with cols[i % 4]:
                foods = ", ".join(f["name"] for f in m["foods"])
                color = "#a6e3a1" if m["total_calories"] < 300 else "#f9e2af" if m["total_calories"] < 600 else "#f38ba8"
                st.markdown(f"""
                <div class="meal-card" style="border-left-color: {color};">
                    <strong>{m['type']}</strong> <small>{m['time']}</small><br>
                    <span style="font-size:20px;font-weight:700;">{m['total_calories']:.0f}</span> kcal<br>
                    <small>{foods[:50]}{'…' if len(foods)>50 else ''}</small>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No hay comidas registradas hoy. Envía una foto al bot de Telegram.")

# ════════════════════════════════════════════════
# TAB 2: MEALS TABLE
# ════════════════════════════════════════════════
with tab_meals:
    st.subheader(f"🍽️ Comidas del {start_dt} al {end_dt}")
    
    from src.models import Meal, MealFood, MealType
    db = SessionLocal()
    meals_data = (
        db.query(Meal)
        .filter(Meal.eaten_at >= datetime.combine(start_dt, datetime.min.time()),
                Meal.eaten_at <= datetime.combine(end_dt, datetime.max.time()))
        .order_by(Meal.eaten_at.desc())
        .all()
    )
    db.close()
    
    if meals_data:
        rows = []
        for m in meals_data:
            foods = ", ".join(f"{f.food_name} ({f.calories or 0:.0f}kcal)" for f in m.foods)
            rows.append({
                "Fecha": m.eaten_at.strftime("%d/%m/%Y"),
                "Hora": m.eaten_at.strftime("%H:%M"),
                "Tipo": m.meal_type.name,
                "Alimentos": foods if foods else "(vacio)",
                "Calorías": m.total_calories or 0,
                "Proteína": m.total_protein or 0,
                "Carbos": m.total_carbs or 0,
                "Grasas": m.total_fat or 0,
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={
            "Calorías": st.column_config.NumberColumn(format="%.0f"),
            "Proteína": st.column_config.NumberColumn(format="%.0fg"),
            "Carbos": st.column_config.NumberColumn(format="%.0fg"),
            "Grasas": st.column_config.NumberColumn(format="%.0fg"),
        })
    else:
        st.info("No hay comidas en este rango.")

# ════════════════════════════════════════════════
# TAB 3: WEIGHT
# ════════════════════════════════════════════════
with tab_weight:
    st.subheader("⚖️ Evolución del Peso")
    weight = load_weight(90)
    
    if weight:
        df_w = pd.DataFrame(weight)
        df_w["date"] = pd.to_datetime(df_w["date"])
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_w["date"], y=df_w["weight_kg"], mode="lines+markers",
                                 name="Peso", line=dict(color="#f38ba8", width=3),
                                 marker=dict(size=8, color="#f38ba8")))
        if df_w["bodyfat_pct"].notna().any():
            fig.add_trace(go.Scatter(x=df_w["date"], y=df_w["bodyfat_pct"], mode="lines+markers",
                                     name="% Grasa", yaxis="y2", line=dict(color="#a6e3a1", width=2)))
        fig.update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#cdd6f4",
                          yaxis2=dict(overlaying="y", side="right", title="% Grasa"))
        st.plotly_chart(fig, use_container_width=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Peso actual", f"{weight[-1]['weight_kg']:.1f} kg")
        with col2:
            if len(weight) > 1:
                change = weight[-1]["weight_kg"] - weight[0]["weight_kg"]
                emoji = "🔻" if change < 0 else "🔺" if change > 0 else "➖"
                st.metric("Cambio (90d)", f"{change:+.1f} kg", delta=f"{emoji}")
        with col3:
            st.metric("Registros", len(weight))
    else:
        st.info("Registra tu peso con /peso en Telegram.")

# ════════════════════════════════════════════════
# TAB 4: FIT DATA
# ════════════════════════════════════════════════
with tab_fit:
    st.subheader("🏃 Actividad Diaria")
    fit = load_fit(start_dt, end_dt)
    
    if fit:
        df_f = pd.DataFrame(fit)
        df_f["date"] = pd.to_datetime(df_f["date"])
        
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(df_f, x="date", y="steps", title="Pasos Diarios",
                         color="steps", color_continuous_scale="Viridis")
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#cdd6f4")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            if df_f["sleep"].notna().any():
                fig = px.bar(df_f.dropna(subset=["sleep"]), x="date", y="sleep",
                             title="Horas de Sueño", color="sleep",
                             color_continuous_scale="Blues")
                fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font_color="#cdd6f4")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin datos de sueño")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Media pasos/día", f"{df_f['steps'].mean():.0f}")
        with col2:
            if df_f["active_cal"].notna().any():
                st.metric("Media calorías activas", f"{df_f['active_cal'].mean():.0f}")
    else:
        st.info("Sincroniza Google Fit para ver datos de actividad. El cron sync_fit corre a las 08:00.")

# ════════════════════════════════════════════════
# TAB 5: MEAL PLAN
# ════════════════════════════════════════════════
with tab_plan:
    plan = load_plan()
    
    if plan and plan.get("days"):
        st.subheader(f"📋 Plan de Dieta — Semana del {plan['week_start']}")
        
        day_names = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        all_rows = []
        day_totals = []
        
        for day_idx in sorted(plan["days"].keys()):
            day = plan["days"][day_idx]
            day_cal = sum(m.get("calories", 0) or 0 for m in day["meals"])
            day_prot = sum(m.get("protein_g", 0) or 0 for m in day["meals"])
            day_carbs = sum(m.get("carbs_g", 0) or 0 for m in day["meals"])
            day_fat = sum(m.get("fat_g", 0) or 0 for m in day["meals"])
            day_totals.append({"day": day["day"], "calories": day_cal, "protein": day_prot,
                               "carbs": day_carbs, "fat": day_fat})
            for m in day["meals"]:
                all_rows.append({"Día": day["day"], "Comida": m["meal_type"], "Alimentos": m.get("foods", "")[:80],
                                 "kcal": m.get("calories", 0), "Proteína": m.get("protein_g", 0)})
        
        if day_totals:
            df_days = pd.DataFrame(day_totals)
            fig = go.Figure()
            fig.add_trace(go.Bar(name="Calorías", x=df_days["day"], y=df_days["calories"], marker_color="#f38ba8"))
            fig.add_trace(go.Bar(name="Proteínas", x=df_days["day"], y=df_days["protein"], marker_color="#a6e3a1"))
            fig.add_trace(go.Bar(name="Carbos", x=df_days["day"], y=df_days["carbs"], marker_color="#f9e2af"))
            fig.update_layout(barmode="group", height=350, paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)", font_color="#cdd6f4")
            st.plotly_chart(fig, use_container_width=True)
        
        if all_rows:
            st.dataframe(pd.DataFrame(all_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No hay plan de dieta generado. El cron semanal lo crea los domingos.")

# ════════════════════════════════════════════════
# TAB 6: GOALS
# ════════════════════════════════════════════════
with tab_goals:
    st.subheader("🎯 Objetivos Nutricionales")
    
    with MiSaludRepo() as repo:
        goal = repo.get_active_goal()
        fit_obj = repo.get_today_fit()
    
    if goal:
        kpi = load_kpi(today)
        
        left, right = st.columns([2, 1])
        with left:
            st.markdown(f"**Objetivo:** {USER_PROFILE['goal']}")
            st.markdown(f"🔥 {kpi['calories']:.0f} / {goal.daily_calories} kcal ({kpi['calories']/goal.daily_calories*100:.0f}%)")
            st.progress(min(kpi['calories']/goal.daily_calories, 1.0))
            
            st.markdown(f"💪 {kpi['protein_g']:.0f} / {goal.protein_g}g proteína ({kpi['protein_g']/goal.protein_g*100:.0f}%)")
            st.progress(min(kpi['protein_g']/goal.protein_g, 1.0))
            
            st.markdown(f"🍚 {kpi['carbs_g']:.0f} / {goal.carbs_g}g carbohidratos")
            st.progress(min(kpi['carbs_g']/goal.carbs_g, 1.0))
            
            st.markdown(f"🧈 {kpi['fat_g']:.0f} / {goal.fat_g}g grasas")
            st.progress(min(kpi['fat_g']/goal.fat_g, 1.0))
        
        with right:
            st.metric("Peso objetivo", f"{goal.target_weight_kg} kg" if goal.target_weight_kg else "—")
            if fit_obj:
                st.metric("Pasos hoy", f"{fit_obj.steps:,}")
                if fit_obj.sleep_hours:
                    st.metric("Sueño", f"{fit_obj.sleep_hours}h")
        
        st.caption(f"Para cambiar objetivos, usa /objetivo en Telegram")
    else:
        st.warning("No hay objetivo configurado. Usa /objetivo 2200 en Telegram.")

# ── Footer ──────────────────────────────────────
st.divider()
st.caption(f"MiSalud v2.0 · {USER_PROFILE['name']} · Datos en SQLite · {datetime.now().strftime('%d/%m/%Y %H:%M')}")
