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
    user_columns = {column["name"] for column in inspect(engine).get_columns("app_user")}
    education_columns = {column["name"] for column in inspect(engine).get_columns("education")}
    annual_status_columns = {column["name"] for column in inspect(engine).get_columns("annual_status")}
    audit_log_columns = {column["name"] for column in inspect(engine).get_columns("audit_log")}
    postponement_columns = {
        column["name"] for column in inspect(engine).get_columns("postponement")
    }
    audit_columns = {column["name"] for column in inspect(engine).get_columns("audit_log")}
    copilot_message_columns = {column["name"] for column in inspect(engine).get_columns("copilot_message")}
    transfer_intake_columns = {
        column["name"] for column in inspect(engine).get_columns("transfer_intake")
    }
    training_schedule_columns = {
        column["name"] for column in inspect(engine).get_columns("training_schedule")
    }
    training_batch_columns = {
        column["name"]: column for column in inspect(engine).get_columns("training_result_batch")
    }
    with engine.begin() as connection:
        if "is_active" not in user_columns:
            connection.execute(text("ALTER TABLE app_user ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        if "version" not in training_schedule_columns:
            connection.execute(text("ALTER TABLE training_schedule ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
        if "demo_early_save_enabled" not in training_schedule_columns:
            connection.execute(text(
                "ALTER TABLE training_schedule ADD COLUMN demo_early_save_enabled BOOLEAN NOT NULL DEFAULT 0"
            ))
        if "demo_early_save_used" not in training_schedule_columns:
            connection.execute(text(
                "ALTER TABLE training_schedule ADD COLUMN demo_early_save_used BOOLEAN NOT NULL DEFAULT 0"
            ))
        if training_batch_columns and not training_batch_columns["user_id"]["nullable"]:
            connection.execute(text("""
                CREATE TABLE training_result_batch_rebuild (
                    idempotency_key VARCHAR(128) NOT NULL PRIMARY KEY,
                    user_id INTEGER NULL,
                    request_hash VARCHAR(64) NOT NULL,
                    response_data TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES app_user(id)
                )
            """))
            connection.execute(text("""
                INSERT INTO training_result_batch_rebuild
                    (idempotency_key, user_id, request_hash, response_data, created_at)
                SELECT idempotency_key, user_id, request_hash, response_data, created_at
                FROM training_result_batch
            """))
            connection.execute(text("DROP TABLE training_result_batch"))
            connection.execute(text(
                "ALTER TABLE training_result_batch_rebuild RENAME TO training_result_batch"
            ))
        for status_key in ("이수", "completed", "참석", "attended"):
            connection.execute(text("""
                INSERT OR IGNORE INTO training_status_policy (
                    status_key, counts_hours, credits_hours, advances_round,
                    confirmed_absence, enabled, prosecution_kind
                ) VALUES (:status_key, 1, 0, 0, 0, 1, NULL)
            """), {"status_key": status_key})
        for status_key in ("무단불참", "무단_불참", "unexcused_absence"):
            connection.execute(text("""
                INSERT OR IGNORE INTO training_status_policy (
                    status_key, counts_hours, credits_hours, advances_round,
                    confirmed_absence, enabled, prosecution_kind
                ) VALUES (:status_key, 0, 0, 1, 1, 1, 'type_i_or_round_3')
            """), {"status_key": status_key})
        for status_key in ("연기", "postponed", "보류", "round_hold", "훈련 예정", "scheduled", "overdue"):
            connection.execute(text("""
                INSERT OR IGNORE INTO training_status_policy (
                    status_key, counts_hours, credits_hours, advances_round,
                    confirmed_absence, enabled, prosecution_kind
                ) VALUES (:status_key, 0, 0, 0, 0, 1, NULL)
            """), {"status_key": status_key})
        early_dismissal_counts_hours = os.getenv(
            "EARLY_DISMISSAL_COUNTS_HOURS", "true"
        ).lower() in {"1", "true", "yes"}
        connection.execute(text("""
            INSERT OR IGNORE INTO training_status_policy (
                status_key, counts_hours, credits_hours, advances_round,
                confirmed_absence, enabled, prosecution_kind
            ) VALUES ('조기퇴소', :counts_hours, 0, 0, 0, 1, NULL)
        """), {"counts_hours": int(early_dismissal_counts_hours)})
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
        if "discharge_date" not in person_columns:
            connection.execute(text("ALTER TABLE person ADD COLUMN discharge_date DATE"))
        if "callup_release_date" not in person_columns:
            connection.execute(text("ALTER TABLE person ADD COLUMN callup_release_date DATE"))
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
        if "scheduled_date" not in education_columns:
            connection.execute(text("ALTER TABLE education ADD COLUMN scheduled_date DATE"))
        if "schedule_id" not in education_columns:
            connection.execute(
                text(
                    "ALTER TABLE education ADD COLUMN schedule_id INTEGER "
                    "REFERENCES training_schedule(id)"
                )
            )
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_education_schedule_person "
            "ON education(schedule_id, person_id) WHERE schedule_id IS NOT NULL"
        ))
        if "version" not in education_columns:
            connection.execute(text("ALTER TABLE education ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
        if "source_kind" not in education_columns:
            connection.execute(text("ALTER TABLE education ADD COLUMN source_kind VARCHAR(20) NOT NULL DEFAULT 'attendance'"))
        if "confirmed_by" not in education_columns:
            connection.execute(text("ALTER TABLE education ADD COLUMN confirmed_by VARCHAR(100)"))
        if "confirmed_at" not in education_columns:
            connection.execute(text("ALTER TABLE education ADD COLUMN confirmed_at DATETIME"))
        if "semester_completed" not in annual_status_columns:
            connection.execute(text("ALTER TABLE annual_status ADD COLUMN semester_completed BOOLEAN"))
        if "actor_label" not in audit_log_columns:
            connection.execute(text("ALTER TABLE audit_log ADD COLUMN actor_label VARCHAR(100) NOT NULL DEFAULT '미인증 요청'"))
        if "entity_key" not in audit_log_columns:
            connection.execute(text("ALTER TABLE audit_log ADD COLUMN entity_key VARCHAR(100)"))
        if "before_data" not in audit_log_columns:
            connection.execute(text("ALTER TABLE audit_log ADD COLUMN before_data TEXT"))
        if "after_data" not in audit_log_columns:
            connection.execute(text("ALTER TABLE audit_log ADD COLUMN after_data TEXT"))
        if "created_at" not in audit_log_columns:
            connection.execute(text("ALTER TABLE audit_log ADD COLUMN created_at DATETIME"))
        connection.execute(text("UPDATE audit_log SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
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
        if "category" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN category VARCHAR(50)"))
        if "training_year" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN training_year INTEGER"))
        if "source_file" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN source_file VARCHAR(255)"))
        if "classifier_submission_id" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN classifier_submission_id VARCHAR(64)"))
        if "approved_at" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN approved_at DATETIME"))
        for column, column_type in (("source", "VARCHAR(50)"),
                                    ("trace_id", "VARCHAR(32)"), ("summary", "TEXT"), ("detail", "TEXT")):
            if column not in audit_columns:
                connection.execute(text(f"ALTER TABLE audit_log ADD COLUMN {column} {column_type}"))
        for column, column_type in (("undone_at", "DATETIME"), ("undone_summary", "TEXT")):
            if column not in copilot_message_columns:
                connection.execute(text(f"ALTER TABLE copilot_message ADD COLUMN {column} {column_type}"))
        if "education_record_id" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN education_record_id INTEGER"))
        if "start_date" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN start_date DATE"))
        if "end_date" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN end_date DATE"))
        if "credited_hours" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN credited_hours INTEGER"))
        if "resolution_reported_at" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN resolution_reported_at DATETIME"))
        if "hold_ended_recalculated_at" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN hold_ended_recalculated_at DATETIME"))
        if "decided_by" not in postponement_columns:
            connection.execute(text("ALTER TABLE postponement ADD COLUMN decided_by VARCHAR(100)"))
        if "carryovers" not in transfer_intake_columns:
            connection.execute(text("ALTER TABLE transfer_intake ADD COLUMN carryovers JSON NOT NULL DEFAULT '[]'"))
        carryover_columns = {
            column["name"] for column in inspect(engine).get_columns("training_carryover")
        }
        if "imported_hours" not in carryover_columns:
            connection.execute(text("ALTER TABLE training_carryover ADD COLUMN imported_hours INTEGER NOT NULL DEFAULT 0"))
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
