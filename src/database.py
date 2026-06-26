"""Database engine, session, and initialization for MiSalud."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

# Enable WAL mode + foreign keys on every connection
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    """Dependency-style DB session generator."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and seed default meal_types / workout_types."""
    from . import models  # noqa — ensure all models are registered
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Seed meal types
        default_meal_types = [
            ("Desayuno", 1),
            ("Almuerzo", 2),
            ("Cena", 3),
            ("Merienda", 4),
            ("Snack", 5),
        ]
        for name, order in default_meal_types:
            if not db.query(models.MealType).filter_by(name=name).first():
                db.add(models.MealType(name=name, sort_order=order))

        # Seed workout types with MET values
        default_workout_types = [
            ("Running", 9.8),
            ("Ciclismo", 7.5),
            ("Natación", 8.0),
            ("Gimnasio", 5.0),
            ("Yoga", 3.0),
            ("Caminata", 3.8),
            ("HIIT", 8.0),
            ("CrossFit", 8.0),
            ("Fútbol", 7.0),
            ("Pádel", 6.0),
            ("Otro", 5.0),
        ]
        for name, met in default_workout_types:
            if not db.query(models.WorkoutType).filter_by(name=name).first():
                db.add(models.WorkoutType(name=name, met_value=met))

        db.commit()
    finally:
        db.close()
