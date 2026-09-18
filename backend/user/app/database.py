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
        # The original regrouping was a one-time legacy normalization. Running
        # it again after an editable hierarchy exists can assign people to
        # obsolete numeric squad IDs, so never run it against the new tree.
        if mixed_squad_count and connection.execute(
            text("SELECT COUNT(*) FROM organization_node")
        ).scalar_one() == 0:
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
        # Repair only the known example/legacy hierarchy. Existing user-created
        # units elsewhere in the tree must not be silently deleted or moved.
        _ensure_squad_based_hierarchy(connection)


def _ensure_squad_based_hierarchy(connection) -> None:
    """One-time correction: 11 per squad; remove the old parked starter squads.

    This runs in init_db's transaction. People remain in the database; anyone
    assigned to the obsolete starter squads becomes unassigned. Assignment
    rows referring to deleted squads are removed to keep foreign keys valid.
    """
    roots = connection.execute(text("""
        SELECT id, name FROM organization_node WHERE kind = 'root' ORDER BY id
    """)).mappings().all()
    created_root = not roots
    if not roots:
        root_id = connection.execute(text("""
            INSERT INTO organization_node (parent_id, kind, name, squad_id, planned_strength)
            VALUES (NULL, 'root', '삼각동대', NULL, NULL) RETURNING id
        """)).scalar_one()
    else:
        root_id = roots[0]['id']

    nodes = connection.execute(text("""
        SELECT id, parent_id, kind, name, squad_id
        FROM organization_node ORDER BY id
    """)).mappings().all()
    parked = [n for n in nodes if n['kind'] == 'company'
              and n['name'] == '기존 분대 (미배치)' and n['parent_id'] == root_id]
    obsolete_ids: set[int] = set()
    obsolete_node_ids: set[int] = set()
    parked_ids: list[int] = []
    if parked:
        for group in parked:
            children = [n for n in nodes if n['parent_id'] == group['id']]
            if any(n['kind'] != 'squad' or n['squad_id'] is None for n in children):
                raise RuntimeError('기존 분대 아래에 사용자 정의 하위 단위가 있습니다. 자동 삭제를 중단합니다.')
            parked_ids.append(group['id'])
            obsolete_ids.update(n['squad_id'] for n in children)
            obsolete_node_ids.update(n['id'] for n in children)
    else:
        # Also repair the older, untouched 20-squad root, but never classify an
        # edited hierarchy as legacy merely because it contains a numbered squad.
        nonroot = [n for n in nodes if n['kind'] != 'root']
        untouched = (
            len(roots) == 1 and roots[0]['name'] == '편제'
            and len(nonroot) == 20
            and {n['squad_id'] for n in nonroot} == set(range(1, 21))
            and all(n['kind'] == 'squad' and n['parent_id'] == root_id for n in nonroot)
        )
        if untouched:
            obsolete_ids = set(range(1, 21))
            obsolete_node_ids = {n['id'] for n in nonroot}

    # The original DB can have the starter 20 squads without *any* organization
    # nodes yet. Identify this case by all 20 original IDs and their exact names.
    # Never delete a customized squad merely because its ID is low.
    if not parked and not obsolete_ids and all(n['kind'] == 'root' for n in nodes):
        standalone_squads = connection.execute(text("""
            SELECT id, name FROM squad ORDER BY id
        """)).mappings().all()
        if len(standalone_squads) == 20 and all(
            unit['id'] == number and unit['name'] == f'{number}분대'
            for number, unit in enumerate(standalone_squads, start=1)
        ):
            obsolete_ids = set(range(1, 21))

    for squad_id in sorted(obsolete_ids):
        connection.execute(text('UPDATE person SET squad_id = NULL WHERE squad_id = :sid'), {'sid': squad_id})
        connection.execute(text('DELETE FROM assignment WHERE squad_id = :sid'), {'sid': squad_id})
    for node_id in sorted(obsolete_node_ids):
        connection.execute(text('DELETE FROM organization_node WHERE id = :nid'), {'nid': node_id})
    for group_id in parked_ids:
        connection.execute(text('DELETE FROM organization_node WHERE id = :gid'), {'gid': group_id})
    for squad_id in sorted(obsolete_ids):
        connection.execute(text('DELETE FROM squad WHERE id = :sid'), {'sid': squad_id})

    remaining = connection.execute(text("""
        SELECT id FROM organization_node WHERE kind != 'root' LIMIT 1
    """)).first()
    # The initial demonstration layout is created only for an empty hierarchy;
    # adding or removing units later must never be undone on restart.
    if not remaining and (created_root or bool(obsolete_ids)
                          or (len(roots) == 1 and roots[0]['name'] == '편제')):
        if len(roots) == 1 and roots[0]['name'] == '편제':
            connection.execute(text("""
                UPDATE organization_node SET name = '삼각동대' WHERE id = :rid
            """), {'rid': root_id})
        for platoon_number in range(1, 4):
            platoon_id = connection.execute(text("""
                INSERT INTO organization_node (parent_id, kind, name, squad_id, planned_strength)
                VALUES (:parent, 'platoon', :name, NULL, NULL) RETURNING id
            """), {'parent': root_id, 'name': f'{platoon_number}소대'}).scalar_one()
            for squad_number in range(1, 5):
                squad_id = connection.execute(text("""
                    INSERT INTO squad (name, description)
                    VALUES (:name, :description) RETURNING id
                """), {'name': f'{platoon_number}소대 {squad_number}분대',
                       'description': '기본 편제'}).scalar_one()
                connection.execute(text("""
                    INSERT INTO organization_node
                        (parent_id, kind, name, squad_id, planned_strength)
                    VALUES (:parent, 'squad', :name, :squad, 11)
                """), {'parent': platoon_id, 'name': f'{squad_number}분대', 'squad': squad_id})
    # Quota belongs to a squad. Platoon/root quotas are derived, not stored
    # independently, so a newly added or removed squad changes the total.
    connection.execute(text("UPDATE organization_node SET planned_strength = 11 WHERE kind = 'squad'"))
    connection.execute(text("UPDATE organization_node SET planned_strength = NULL WHERE kind != 'squad'"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
