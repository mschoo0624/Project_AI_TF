"""SQLite database configuration for the testing phase."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "project_ai_tf.db"
DB_PATH = Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Import models and create any missing SQLite tables."""
    from user.app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    person_columns = {column["name"] for column in inspect(engine).get_columns("person")}
    postponement_columns = {
        column["name"] for column in inspect(engine).get_columns("postponement")
    }
    education_columns = {column["name"] for column in inspect(engine).get_columns("education")}
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS annual_status (
                    person_id VARCHAR(50) NOT NULL,
                    service_year INTEGER NOT NULL,
                    mobilization_status VARCHAR(20) NOT NULL,
                    PRIMARY KEY (person_id, service_year),
                    FOREIGN KEY (person_id) REFERENCES person(military_number)
                )
                """
            )
        )
        if "branch" not in person_columns:
            connection.execute(
                text("ALTER TABLE person ADD COLUMN branch VARCHAR(50) NOT NULL DEFAULT '육군'")
            )
        if "service_year" not in person_columns:
            connection.execute(
                text("ALTER TABLE person ADD COLUMN service_year INTEGER")
            )
        if "position" not in person_columns:
            connection.execute(
                text("ALTER TABLE person ADD COLUMN position VARCHAR(50)")
            )
        if "origin_type" not in person_columns:
            connection.execute(
                text("ALTER TABLE person ADD COLUMN origin_type VARCHAR(50)")
            )
        if "mobilization_status" not in person_columns:
            connection.execute(
                text("ALTER TABLE person ADD COLUMN mobilization_status VARCHAR(20)")
            )
        if "approved_at" not in postponement_columns:
            connection.execute(
                text("ALTER TABLE postponement ADD COLUMN approved_at DATETIME")
            )
        if "training_year" not in education_columns:
            connection.execute(text("ALTER TABLE education ADD COLUMN training_year INTEGER"))
        if "training_type" not in education_columns:
            connection.execute(
                text(
                    "ALTER TABLE education ADD COLUMN training_type VARCHAR(50) "
                    "NOT NULL DEFAULT '기본훈련'"
                )
            )
        if "training_round" not in education_columns:
            connection.execute(
                text("ALTER TABLE education ADD COLUMN training_round INTEGER NOT NULL DEFAULT 1")
            )
        if "attendance_status" not in education_columns:
            connection.execute(
                text("ALTER TABLE education ADD COLUMN attendance_status VARCHAR(20) NOT NULL DEFAULT 'completed'")
            )
        connection.execute(
            text(
                "UPDATE person SET service_year = 1 WHERE service_year IS NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE person SET position = '보충' WHERE position IS NULL"
            )
        )
        connection.execute(
            text(
                "UPDATE person SET mobilization_status = '미지정' "
                "WHERE mobilization_status IS NULL AND service_year <= 4"
            )
        )
        connection.execute(
            text(
                "UPDATE person SET mobilization_status = '해당없음' "
                "WHERE mobilization_status IS NULL AND service_year > 4"
            )
        )
        connection.execute(
            text(
                """
                INSERT OR IGNORE INTO annual_status (
                    person_id, service_year, mobilization_status
                )
                SELECT military_number, service_year, mobilization_status
                FROM person
                WHERE service_year IS NOT NULL AND mobilization_status IS NOT NULL
                """
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
