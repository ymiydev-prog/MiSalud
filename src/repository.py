"""Repository layer — high-level data operations for MiSalud.

All business logic for meals, workouts, weight, fit data, goals,
meal plans, and weekly summaries lives here.  Thin wrappers over
SQLAlchemy that keep the rest of the app ignorant of ORM details.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from .database import SessionLocal
from . import models


class MiSaludRepo:
    """High-level data access.  Use as context manager or pass a session."""

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
        self._own_session = db is None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._own_session:
            self.db.close()

    # ── Meals ────────────────────────────────────────

    def add_meal(
        self,
        meal_type_name: str,
        eaten_at: datetime = None,
        photo_path: str = None,
        confidence: str = None,
        notes: str = None,
    ) -> models.Meal:
        """Create a new meal record (without foods).  Use add_food_to_meal next."""
        # Normalize: case-insensitive lookup, capitalize first letter
        meal_type = (
            self.db.query(models.MealType)
            .filter(models.MealType.name.ilike(meal_type_name))
            .first()
        )
        if not meal_type:
            # Try creating it as a new type
            meal_type = models.MealType(name=meal_type_name.capitalize())
            self.db.add(meal_type)
            self.db.commit()

        meal = models.Meal(
            meal_type_id=meal_type.id,
            eaten_at=eaten_at or datetime.now(),
            photo_path=photo_path,
            confidence=confidence,
            notes=notes,
        )
        self.db.add(meal)
        self.db.commit()
        return meal

    def add_food_to_meal(self, meal_id: int, food: dict) -> models.MealFood:
        """Add a food item to an existing meal.

        food dict keys: name (required), portion_g, calories, protein_g,
                        carbs_g, fat_g, fiber_g
        """
        max_order = (
            self.db.query(func.max(models.MealFood.food_order))
            .filter_by(meal_id=meal_id)
            .scalar()
        ) or 0

        mf = models.MealFood(
            meal_id=meal_id,
            food_name=food["name"],
            portion_g=food.get("portion_g"),
            calories=food.get("calories"),
            protein_g=food.get("protein_g"),
            carbs_g=food.get("carbs_g"),
            fat_g=food.get("fat_g"),
            fiber_g=food.get("fiber_g"),
            food_order=max_order + 1,
        )
        self.db.add(mf)
        self.db.commit()
        return mf

    def get_meals_for_date(self, target_date: date) -> list[models.Meal]:
        """All meals for a specific date, with foods eagerly loaded."""
        return (
            self.db.query(models.Meal)
            .filter(func.date(models.Meal.eaten_at) == target_date)
            .order_by(models.Meal.eaten_at)
            .all()
        )

    def get_meals_range(self, start: date, end: date) -> list[models.Meal]:
        """All meals in a date range (inclusive)."""
        return (
            self.db.query(models.Meal)
            .filter(
                and_(
                    func.date(models.Meal.eaten_at) >= start,
                    func.date(models.Meal.eaten_at) <= end,
                )
            )
            .order_by(models.Meal.eaten_at)
            .all()
        )

    def daily_nutrition(self, target_date: date) -> dict:
        """Full nutrition breakdown for one day."""
        meals = self.get_meals_for_date(target_date)
        totals = {
            "date": target_date.isoformat(),
            "calories": 0, "protein_g": 0, "carbs_g": 0,
            "fat_g": 0, "fiber_g": 0,
            "meals": [],
        }
        for meal in meals:
            meal_dict = {
                "id": meal.id,
                "type": meal.meal_type.name,
                "time": meal.eaten_at.strftime("%H:%M"),
                "confidence": meal.confidence,
                "photo_path": meal.photo_path,
                "foods": [
                    {
                        "name": f.food_name,
                        "portion_g": f.portion_g,
                        "calories": f.calories,
                        "protein_g": f.protein_g,
                        "carbs_g": f.carbs_g,
                        "fat_g": f.fat_g,
                    }
                    for f in meal.foods
                ],
                "total_calories": meal.total_calories,
            }
            totals["meals"].append(meal_dict)
            totals["calories"] += meal.total_calories or 0
            totals["protein_g"] += meal.total_protein or 0
            totals["carbs_g"] += meal.total_carbs or 0
            totals["fat_g"] += meal.total_fat or 0
            totals["fiber_g"] += meal.total_fiber or 0

        return totals

    def daily_calorie_trend(self, days: int = 30) -> list[dict]:
        """Calories per day for the last N days (for dashboard charts)."""
        cutoff = datetime.now().date() - timedelta(days=days)
        rows = (
            self.db.query(
                func.date(models.Meal.eaten_at).label("day"),
                func.sum(models.MealFood.calories).label("total_cal"),
            )
            .join(models.MealFood)
            .filter(func.date(models.Meal.eaten_at) >= cutoff)
            .group_by(func.date(models.Meal.eaten_at))
            .order_by("day")
            .all()
        )
        return [{"date": str(r.day), "calories": float(r.total_cal or 0)} for r in rows]

    # ── Workouts ─────────────────────────────────────

    def get_last_meal(self) -> Optional[models.Meal]:
        """Get the most recent meal."""
        return (
            self.db.query(models.Meal)
            .order_by(models.Meal.id.desc())
            .first()
        )

    def delete_meal(self, meal_id: int) -> bool:
        """Delete a meal and all its foods (cascade)."""
        meal = self.db.query(models.Meal).get(meal_id)
        if meal:
            self.db.delete(meal)
            self.db.commit()
            return True
        return False

    def replace_meal_foods(self, meal_id: int, foods: list[dict]) -> bool:
        """Replace all foods in a meal with a new list."""
        from .database import SessionLocal
        db = SessionLocal()
        try:
            db.query(models.MealFood).filter_by(meal_id=meal_id).delete()
            for i, f in enumerate(foods):
                mf = models.MealFood(
                    meal_id=meal_id,
                    food_name=f["name"],
                    portion_g=f.get("portion_g"),
                    calories=f.get("calories"),
                    protein_g=f.get("protein_g"),
                    carbs_g=f.get("carbs_g"),
                    fat_g=f.get("fat_g"),
                    fiber_g=f.get("fiber_g"),
                    food_order=i + 1,
                )
                db.add(mf)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def add_workout(
        self,
        type_name: str,
        started_at: datetime = None,
        duration_min: int = None,
        calories_burned: float = None,
        distance_km: float = None,
        avg_heart_rate: int = None,
        sets_count: int = None,
        weight_kg: float = None,
        notes: str = None,
    ) -> models.Workout:
        """Record a workout. Creates workout type if it doesn't exist."""
        wtype = self.db.query(models.WorkoutType).filter_by(name=type_name).first()
        if not wtype:
            wtype = models.WorkoutType(name=type_name)
            self.db.add(wtype)
            self.db.commit()

        workout = models.Workout(
            workout_type_id=wtype.id,
            started_at=started_at or datetime.now(),
            duration_min=duration_min,
            calories_burned=calories_burned,
            distance_km=distance_km,
            avg_heart_rate=avg_heart_rate,
            sets_count=sets_count,
            weight_kg=weight_kg,
            notes=notes,
        )
        self.db.add(workout)
        self.db.commit()
        return workout

    def get_workouts_range(self, start: date, end: date) -> list[models.Workout]:
        """Workouts in a date range."""
        return (
            self.db.query(models.Workout)
            .filter(
                and_(
                    func.date(models.Workout.started_at) >= start,
                    func.date(models.Workout.started_at) <= end,
                )
            )
            .order_by(models.Workout.started_at)
            .all()
        )

    # ── Weight ───────────────────────────────────────

    def log_weight(
        self, weight_kg: float,
        measured_at: datetime = None,
        bodyfat_pct: float = None,
        muscle_kg: float = None,
        notes: str = None,
    ) -> models.WeightLog:
        """Record a weight measurement."""
        wl = models.WeightLog(
            weight_kg=weight_kg,
            measured_at=measured_at or datetime.now(),
            bodyfat_pct=bodyfat_pct,
            muscle_kg=muscle_kg,
            notes=notes,
        )
        self.db.add(wl)
        self.db.commit()
        return wl

    def get_weight_trend(self, days: int = 90) -> list[dict]:
        """Weight entries for the last N days, ordered by date ascending."""
        cutoff = datetime.now() - timedelta(days=days)
        logs = (
            self.db.query(models.WeightLog)
            .filter(models.WeightLog.measured_at >= cutoff)
            .order_by(models.WeightLog.measured_at)
            .all()
        )
        return [
            {
                "date": l.measured_at.strftime("%Y-%m-%d"),
                "weight_kg": l.weight_kg,
                "bodyfat_pct": l.bodyfat_pct,
            }
            for l in logs
        ]

    # ── Fit Data ─────────────────────────────────────

    def upsert_fit_data(self, fit_date: date, **kwargs) -> models.FitData:
        """Insert or update Fit data for a given date."""
        existing = self.db.query(models.FitData).filter_by(date=fit_date).first()
        if existing:
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            self.db.commit()
            return existing

        fd = models.FitData(date=fit_date, **kwargs)
        self.db.add(fd)
        self.db.commit()
        return fd

    def get_fit_range(self, start: date, end: date) -> list[models.FitData]:
        """Fit data for a date range."""
        return (
            self.db.query(models.FitData)
            .filter(and_(models.FitData.date >= start, models.FitData.date <= end))
            .order_by(models.FitData.date)
            .all()
        )

    def get_today_fit(self) -> Optional[models.FitData]:
        """Most recent Fit data record (usually today's)."""
        today = date.today()
        return self.db.query(models.FitData).filter_by(date=today).first()

    # ── Goals ────────────────────────────────────────

    def get_active_goal(self) -> Optional[models.Goal]:
        """Currently active nutrition/fitness goal."""
        return self.db.query(models.Goal).filter_by(is_active=True).first()

    def set_goal(self, **kwargs) -> models.Goal:
        """Set a new active goal (deactivates all previous ones)."""
        self.db.query(models.Goal).filter_by(is_active=True).update({"is_active": False})
        goal = models.Goal(
            **kwargs,
            is_active=True,
            start_date=kwargs.get("start_date", date.today()),
        )
        self.db.add(goal)
        self.db.commit()
        return goal

    # ── Meal Plans ──────────────────────────────────

    def save_meal_plan(self, week_start: date, plan_data: list[dict]) -> models.MealPlan:
        """Save a full weekly meal plan (replaces existing for that week).

        plan_data: list of day dicts:
          [{"day_index": 0, "meals": [{"name": "Desayuno", "foods": "...", ...}]}, ...]
        """
        existing = self.db.query(models.MealPlan).filter_by(week_start=week_start).first()
        if existing:
            self.db.delete(existing)
            self.db.commit()

        mp = models.MealPlan(week_start=week_start)
        self.db.add(mp)
        self.db.flush()

        for day in plan_data:
            for meal in day.get("meals", []):
                mt = self.db.query(models.MealType).filter_by(name=meal["name"]).first()
                if not mt:
                    mt = models.MealType(name=meal["name"])
                    self.db.add(mt)
                    self.db.flush()

                pm = models.PlanMeal(
                    plan_id=mp.id,
                    day_of_week=day.get("day_index", 0),
                    meal_type_id=mt.id,
                    foods_text=meal.get("foods", ""),
                    calories=meal.get("calories"),
                    protein_g=meal.get("protein_g"),
                    carbs_g=meal.get("carbs_g"),
                    fat_g=meal.get("fat_g"),
                    recipe_text=meal.get("recipe", ""),
                )
                self.db.add(pm)

        self.db.commit()
        return mp

    def get_weekly_plan(self, week_start: date) -> Optional[dict]:
        """Retrieve a meal plan for a specific week."""
        plan = self.db.query(models.MealPlan).filter_by(week_start=week_start).first()
        if not plan:
            return None

        day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        days = {}
        for pm in plan.meals:
            day_key = pm.day_of_week
            if day_key not in days:
                days[day_key] = {"day": day_names[day_key], "meals": []}
            days[day_key]["meals"].append({
                "meal_type": pm.meal_type.name,
                "foods": pm.foods_text,
                "calories": pm.calories,
                "protein_g": pm.protein_g,
                "carbs_g": pm.carbs_g,
                "fat_g": pm.fat_g,
                "recipe": pm.recipe_text,
            })

        return {"week_start": plan.week_start.isoformat(), "days": days}

    # ── Weekly Summary ──────────────────────────────

    def compute_weekly_summary(self, week_start: date) -> dict:
        """Compute and persist a weekly summary for the dashboard."""
        week_end = week_start + timedelta(days=6)

        # Average weight
        avg_weight = (
            self.db.query(func.avg(models.WeightLog.weight_kg))
            .filter(
                and_(
                    func.date(models.WeightLog.measured_at) >= week_start,
                    func.date(models.WeightLog.measured_at) <= week_end,
                )
            )
            .scalar()
        )

        # Nutrition averages
        meals = self.get_meals_range(week_start, week_end)
        days_with_meals = set()
        total_cal = total_prot = total_carbs = total_fat = 0.0
        for meal in meals:
            days_with_meals.add(meal.eaten_at.date())
            total_cal += meal.total_calories or 0
            total_prot += meal.total_protein or 0
            total_carbs += meal.total_carbs or 0
            total_fat += meal.total_fat or 0

        n_days = max(len(days_with_meals), 1)
        avg_cal = total_cal / n_days
        avg_prot = total_prot / n_days
        avg_carbs = total_carbs / n_days
        avg_fat = total_fat / n_days

        # Average steps
        avg_steps = (
            self.db.query(func.avg(models.FitData.steps))
            .filter(
                and_(
                    models.FitData.date >= week_start,
                    models.FitData.date <= week_end,
                )
            )
            .scalar()
        )

        # Compliance vs active goal
        compliance = None
        goal = self.get_active_goal()
        if goal and goal.daily_calories and avg_cal:
            compliance = min(100.0, round((avg_cal / goal.daily_calories) * 100, 1))

        # Upsert
        existing = self.db.query(models.WeeklySummary).filter_by(week_start=week_start).first()
        if existing:
            existing.avg_weight = round(avg_weight, 1) if avg_weight else None
            existing.avg_calories = round(avg_cal, 0)
            existing.avg_protein = round(avg_prot, 0)
            existing.avg_carbs = round(avg_carbs, 0)
            existing.avg_fat = round(avg_fat, 0)
            existing.avg_steps = int(avg_steps) if avg_steps else None
            existing.compliance_pct = compliance
        else:
            ws = models.WeeklySummary(
                week_start=week_start,
                avg_weight=round(avg_weight, 1) if avg_weight else None,
                avg_calories=round(avg_cal, 0),
                avg_protein=round(avg_prot, 0),
                avg_carbs=round(avg_carbs, 0),
                avg_fat=round(avg_fat, 0),
                avg_steps=int(avg_steps) if avg_steps else None,
                compliance_pct=compliance,
            )
            self.db.add(ws)

        self.db.commit()

        return {
            "week_start": week_start.isoformat(),
            "avg_weight": round(avg_weight, 1) if avg_weight else None,
            "avg_calories": round(avg_cal, 0),
            "avg_protein": round(avg_prot, 0),
            "avg_carbs": round(avg_carbs, 0),
            "avg_fat": round(avg_fat, 0),
            "avg_steps": int(avg_steps) if avg_steps else 0,
            "compliance_pct": compliance,
        }

    # ── Dashboard helpers ───────────────────────────

    def dashboard_kpi(self, target_date: date = None) -> dict:
        """Single call returning everything the dashboard needs for today."""
        if target_date is None:
            target_date = date.today()

        nutrition = self.daily_nutrition(target_date)
        fit = self.get_today_fit()
        active_goal = self.get_active_goal()

        return {
            "date": target_date.isoformat(),
            "calories": nutrition["calories"],
            "protein_g": nutrition["protein_g"],
            "carbs_g": nutrition["carbs_g"],
            "fat_g": nutrition["fat_g"],
            "fiber_g": nutrition["fiber_g"],
            "meal_count": len(nutrition["meals"]),
            "steps": fit.steps if fit else 0,
            "sleep_hours": fit.sleep_hours if fit else None,
            "active_calories": fit.active_calories if fit else 0,
            "active_minutes": fit.active_minutes if fit else 0,
            "goal_calories": active_goal.daily_calories if active_goal else None,
            "goal_protein": active_goal.protein_g if active_goal else None,
            "meals": nutrition["meals"],
        }
