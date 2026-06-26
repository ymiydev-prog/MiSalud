"""SQLAlchemy ORM models for MiSalud.

Relational model:
  meal ──< meal_foods   (one meal has many foods)
  workout ──< workout_type
  meal_plan ──< plan_meals
  fit_data.date is unique (upsert on sync)
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date,
    ForeignKey, Boolean, Text,
)
from sqlalchemy.orm import relationship
from .database import Base


class MealType(Base):
    """Types: Desayuno, Almuerzo, Cena, Merienda, Snack."""
    __tablename__ = "meal_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    sort_order = Column(Integer, default=0)

    meals = relationship("Meal", back_populates="meal_type")
    plan_meals = relationship("PlanMeal", back_populates="meal_type")


class Meal(Base):
    """A recorded meal (e.g., lunch on June 24)."""
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True)
    meal_type_id = Column(Integer, ForeignKey("meal_types.id"), nullable=False)
    eaten_at = Column(DateTime, nullable=False, default=datetime.now)
    photo_path = Column(String(500), nullable=True)
    confidence = Column(String(20), nullable=True)  # high, medium, low
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    meal_type = relationship("MealType", back_populates="meals")
    foods = relationship(
        "MealFood", back_populates="meal",
        cascade="all, delete-orphan",
        order_by="MealFood.food_order",
    )

    @property
    def total_calories(self) -> float:
        return sum(f.calories or 0 for f in self.foods)

    @property
    def total_protein(self) -> float:
        return sum(f.protein_g or 0 for f in self.foods)

    @property
    def total_carbs(self) -> float:
        return sum(f.carbs_g or 0 for f in self.foods)

    @property
    def total_fat(self) -> float:
        return sum(f.fat_g or 0 for f in self.foods)

    @property
    def total_fiber(self) -> float:
        return sum(f.fiber_g or 0 for f in self.foods)

    @property
    def foods_list(self) -> str:
        return ", ".join(
            f"{f.food_name} ({f.portion_g or '?'}g)"
            for f in self.foods
        )


class MealFood(Base):
    """Individual food item within a meal."""
    __tablename__ = "meal_foods"

    id = Column(Integer, primary_key=True)
    meal_id = Column(Integer, ForeignKey("meals.id", ondelete="CASCADE"), nullable=False)
    food_name = Column(String(200), nullable=False)
    portion_g = Column(Float, nullable=True)
    calories = Column(Float, nullable=True)
    protein_g = Column(Float, nullable=True)
    carbs_g = Column(Float, nullable=True)
    fat_g = Column(Float, nullable=True)
    fiber_g = Column(Float, nullable=True)
    food_order = Column(Integer, default=0)

    meal = relationship("Meal", back_populates="foods")


class WorkoutType(Base):
    """Types: Running, Gym, Cycling, etc. with MET values."""
    __tablename__ = "workout_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    met_value = Column(Float, nullable=True)

    workouts = relationship("Workout", back_populates="workout_type")


class Workout(Base):
    """A recorded workout session."""
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True)
    workout_type_id = Column(Integer, ForeignKey("workout_types.id"), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.now)
    ended_at = Column(DateTime, nullable=True)
    duration_min = Column(Integer, nullable=True)
    calories_burned = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    avg_heart_rate = Column(Integer, nullable=True)
    sets_count = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)

    workout_type = relationship("WorkoutType", back_populates="workouts")


class WeightLog(Base):
    """Body weight measurements over time."""
    __tablename__ = "weight_logs"

    id = Column(Integer, primary_key=True)
    measured_at = Column(DateTime, nullable=False, default=datetime.now)
    weight_kg = Column(Float, nullable=False)
    bodyfat_pct = Column(Float, nullable=True)
    muscle_kg = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)


class FitData(Base):
    """Daily data synced from Google Fit. One row per date."""
    __tablename__ = "fit_data"

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False)
    steps = Column(Integer, default=0)
    resting_heart_rate = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    sleep_hours = Column(Float, nullable=True)
    active_calories = Column(Integer, default=0)
    active_minutes = Column(Integer, default=0)


class Goal(Base):
    """Active and historical nutrition/fitness goals."""
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True)
    start_date = Column(Date, nullable=False)
    goal_type = Column(String(50), nullable=False)  # lose, maintain, gain
    daily_calories = Column(Integer, nullable=False)
    protein_g = Column(Integer, nullable=False)
    carbs_g = Column(Integer, nullable=False)
    fat_g = Column(Integer, nullable=False)
    target_weight_kg = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)


class MealPlan(Base):
    """A weekly meal plan."""
    __tablename__ = "meal_plans"

    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.now)

    meals = relationship(
        "PlanMeal", back_populates="plan",
        cascade="all, delete-orphan",
    )


class PlanMeal(Base):
    """A single meal within a weekly plan."""
    __tablename__ = "plan_meals"

    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    meal_type_id = Column(Integer, ForeignKey("meal_types.id"), nullable=False)
    foods_text = Column(Text, nullable=False)
    calories = Column(Float, nullable=True)
    protein_g = Column(Float, nullable=True)
    carbs_g = Column(Float, nullable=True)
    fat_g = Column(Float, nullable=True)
    recipe_text = Column(Text, nullable=True)

    plan = relationship("MealPlan", back_populates="meals")
    meal_type = relationship("MealType", back_populates="plan_meals")


class WeeklySummary(Base):
    """Pre-computed weekly summary for fast dashboard rendering."""
    __tablename__ = "weekly_summaries"

    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False, unique=True)
    avg_weight = Column(Float, nullable=True)
    avg_calories = Column(Float, nullable=True)
    avg_protein = Column(Float, nullable=True)
    avg_carbs = Column(Float, nullable=True)
    avg_fat = Column(Float, nullable=True)
    avg_steps = Column(Integer, nullable=True)
    compliance_pct = Column(Float, nullable=True)
