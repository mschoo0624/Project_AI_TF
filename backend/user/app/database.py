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
        mixed_squad_count = connection.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                    SELECT squad_id
                    FROM person
                    WHERE squad_id IS NOT NULL
                    GROUP BY squad_id
                    HAVING COUNT(DISTINCT branch || ':' || CASE
                        WHEN rank IN ('이병', '일병', '상병', '병장') THEN '병사'
                        WHEN rank IN ('하사', '중사', '상사', '원사') THEN '부사관'
                        WHEN rank IN ('소위', '중위', '대위', '소령', '중령', '대령') THEN '장교'
                        ELSE '기타'
                    END) > 1
                )
                """
            )
        ).scalar_one()
        if mixed_squad_count:
            connection.execute(
                text(
                    """
                    WITH categorized AS (
                        SELECT military_number, branch,
                            CASE
                                WHEN rank IN ('이병', '일병', '상병', '병장') THEN '병사'
                                WHEN rank IN ('하사', '중사', '상사', '원사') THEN '부사관'
                                WHEN rank IN ('소위', '중위', '대위', '소령', '중령', '대령') THEN '장교'
                                ELSE '기타'
                            END AS category
                        FROM person
                        WHERE squad_id IS NOT NULL
                    ), group_squads AS (
                        SELECT branch, category,
                            DENSE_RANK() OVER (ORDER BY branch, category) AS squad_id
                        FROM categorized
                        GROUP BY branch, category
                    )
                    UPDATE person
                    SET squad_id = (
                        SELECT group_squads.squad_id
                        FROM categorized
                        JOIN group_squads
                          ON group_squads.branch = categorized.branch
                         AND group_squads.category = categorized.category
                        WHERE categorized.military_number = person.military_number
                    )
                    WHERE squad_id IS NOT NULL
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE assignment
                    SET squad_id = (
                        SELECT person.squad_id
                        FROM person
                        WHERE person.military_number = assignment.person_id
                    )
                    WHERE person_id IN (SELECT military_number FROM person WHERE squad_id IS NOT NULL)
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
        if "registration_type" not in person_columns:
            connection.execute(
                text("ALTER TABLE person ADD COLUMN registration_type VARCHAR(50)")
            )
        if "mobilization_status" not in person_columns:
            connection.execute(
                text("ALTER TABLE person ADD COLUMN mobilization_status VARCHAR(20)")
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
                "UPDATE person SET mobilization_status = '동원미지정' "
                "WHERE service_year BETWEEN 1 AND 4 "
                "AND mobilization_status NOT IN ("
                "'지정', '동원지정', '미지정', '동원미지정', '학생', '학생예비군', "
                "'보류', '일부보류', '훈련일부보류', 'designated', 'non_designated', "
                "'student', 'partial_hold'"
                ")"
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
        connection.execute(
            text(
                """
                INSERT OR IGNORE INTO squad (id, name, description)
                SELECT id, printf('%d분대', id), printf('제%d분대', id)
                FROM (
                    SELECT 10 AS id UNION ALL SELECT 11 UNION ALL SELECT 12 UNION ALL
                    SELECT 13 UNION ALL SELECT 14 UNION ALL SELECT 15 UNION ALL
                    SELECT 16 UNION ALL SELECT 17 UNION ALL SELECT 18 UNION ALL
                    SELECT 19 UNION ALL SELECT 20
                )
                """
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
