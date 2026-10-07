"""Coverage for the rank/mobilization-status-aware training rules."""

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import pytest
from datetime import date, timedelta

from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.api.reservists import list_prosecution_targets
from user.app.models.annual_status import AnnualStatus
from user.app.models.audit_log import AuditLog
from user.app.services.training import (
	all_training_progress,
    apply_mobilization_status_change,
    mobilization_status_for_year,
    reconcile_due_training_absences,
    reconcile_all_due_training_absences,
    target_training_hours,
    training_plan,
    training_round_sequence_error,
    training_round_satisfied,
    all_training_progress,
    training_progress,
)
from user.app.models.education import Education
from user.app.models.squad import Squad
from user.app.models.training_schedule import TrainingSchedule, TrainingSession
from user.app.models.training_recalculation import TrainingCarryover, TrainingYearResult
from user.app.services.training_recalculation import (
    DEFAULT_STATUS_POLICIES,
    _rounds_for_person,
    _derived_snapshot,
    overlay_progress_with_recalculation,
    recalculate_person,
)


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from user.app import models  # noqa: F401

    models.Person.metadata.create_all(engine)
    return Session(engine)


def test_officer_training_type_tracks_mobilization_designation() -> None:
    for service_year in range(1, 7):
        for rank in ("하사", "중사", "소위", "대위"):
            assert target_training_hours(service_year, "동원미지정", "육군", rank) == 28
            assert target_training_hours(service_year, None, "육군", rank) == 28
            assert training_plan(service_year, "동원미지정", "육군", rank) == [
                {"name": "동원훈련Ⅱ형", "hours": 28}
            ]
            assert training_plan(service_year, "동원지정", "육군", rank) == [
                {"name": "동원훈련Ⅰ형", "hours": 28}
            ]


def test_officer_cadre_has_no_alternative_training_choice() -> None:
    assert target_training_hours(3, "학생예비군", "육군", "중사") == 8
    assert target_training_hours(3, "일부보류", "육군", "중사") == 28
    assert target_training_hours(6, "해당없음", "육군", "소위") == 28


def test_officer_years_seven_eight_are_exempt() -> None:
    assert target_training_hours(7, "동원지정", "육군", "대위") == 0
    assert target_training_hours(8, "동원미지정", "육군", "소령") == 0


def test_missing_designation_stays_needs_review_even_with_squad_assignment() -> None:
    db = make_session()
    squad = Squad(name="배속 여부는 지정 상태의 근거가 아님")
    db.add(squad)
    db.flush()
    person = Person(
        military_number="26-NEEDS-REVIEW-001", name="지정 상태 미상", branch="육군", rank="병장",
        discharge_date=date(2025, 1, 1), service_year=1, mobilization_status=None,
        squad_id=squad.id, status="active",
    )
    db.add(person)
    db.flush()

    recalculate_person(
        db, person.military_number, reason="engine_regression", actor="approver:1",
        today=date(2026, 10, 6),
    )
    db.flush()
    first_snapshot = _derived_snapshot(db, person.military_number)
    year_results = db.scalars(select(TrainingYearResult).where(
        TrainingYearResult.person_id == person.military_number,
        TrainingYearResult.service_year == 1,
    )).all()

    assert len(year_results) == 1
    assert year_results[0].training_type == "NEEDS_REVIEW"
    assert year_results[0].needs_review_reason == "missing_designated_status"
    assert year_results[0].required_hours == 0
    assert year_results[0].unmet_hours == 0
    progress = training_progress(db, person, 1)
    assert progress["training_status"] == "NEEDS_REVIEW"
    assert progress["needs_review_reason"] == "missing_designated_status"
    assert progress["required_hours"] == 0
    recalculate_person(
        db, person.military_number, reason="engine_regression", actor="approver:1",
        today=date(2026, 10, 6),
    )
    db.flush()
    second_snapshot = _derived_snapshot(db, person.military_number)
    audit_rows = db.scalars(select(AuditLog).where(
        AuditLog.entity_key == person.military_number,
        AuditLog.action == "training.recalculate.engine_regression",
    ).order_by(AuditLog.id)).all()

    assert second_snapshot == first_snapshot
    assert len(audit_rows) == 2
    assert audit_rows[1].actor_label == "approver:1"
    assert json.loads(audit_rows[1].before_data) == first_snapshot
    assert json.loads(audit_rows[1].after_data) == second_snapshot
    db.close()


def test_incomplete_student_status_does_not_infer_designation_from_squad() -> None:
    db = make_session()
    squad = Squad(name="학생 지정 상태 미확인")
    db.add(squad)
    db.flush()
    person = Person(
        military_number="26-NEEDS-REVIEW-002", name="학기 미이수", branch="육군", rank="병장",
        discharge_date=date(2024, 1, 1), service_year=2, mobilization_status=None,
        squad_id=squad.id, status="active",
    )
    db.add_all([
        person,
        AnnualStatus(
            person_id=person.military_number, service_year=2,
            mobilization_status="학생예비군", semester_completed=False,
        ),
    ])
    db.flush()

    recalculate_person(db, person.military_number, today=date(2026, 10, 6))
    db.flush()
    year_results = db.scalars(select(TrainingYearResult).where(
        TrainingYearResult.person_id == person.military_number,
        TrainingYearResult.service_year == 2,
    )).all()

    assert len(year_results) == 1
    assert year_results[0].training_type == "NEEDS_REVIEW"
    assert year_results[0].needs_review_reason == "missing_designated_status"
    progress = training_progress(db, person, 2)
    assert progress["training_status"] == "NEEDS_REVIEW"
    assert progress["required_hours"] == 0
    db.close()


def test_enlisted_year_five_six_uses_basic_operations_except_partial_hold() -> None:
    assert target_training_hours(5, "동원미지정", "육군", "병장") == 20
    assert target_training_hours(5, "일부보류", "육군", "이병") == 32
    assert target_training_hours(5, "일부보류", "해군", "병장") == 32
    assert target_training_hours(5, "일부보류", "공군", "병장") == 28
    assert training_plan(5, "동원미지정", "육군", "병장") == [
        {"name": "기본훈련", "hours": 8},
        {"name": "작계훈련(전·후반기)", "hours": 12},
    ]


def test_year_one_to_four_type_two_hours_follow_branch_and_rank() -> None:
    assert target_training_hours(3, "동원미지정", "육군", "병장") == 32
    assert target_training_hours(3, "동원미지정", "해군", "병장") == 32
    assert target_training_hours(3, "동원미지정", "해병대", "병장") == 32
    assert target_training_hours(3, "동원미지정", "공군", "병장") == 28
    assert target_training_hours(3, "동원미지정", "육군", "하사") == 28


def test_student_reservist_always_gets_flat_eight_hours() -> None:
    for service_year in range(1, 7):
        assert target_training_hours(service_year, "학생예비군", "육군", "상병") == 8
        assert training_plan(service_year, "학생예비군", "육군", "상병") == [
            {"name": "학생예비군", "hours": 8}
        ]


def test_enlisted_mobilization_status_selects_training_type() -> None:
    assert training_plan(3, "동원지정", "육군", "병장") == [
        {"name": "동원훈련Ⅰ형", "hours": 28}
    ]
    assert training_plan(3, "동원미지정", "육군", "병장") == [
        {"name": "동원훈련Ⅱ형", "hours": 32}
    ]


def test_enlisted_year_five_six_defaults_to_basic_and_operations_training() -> None:
    assert target_training_hours(5, None, "육군", "병장") == 20
    assert training_plan(6, None, "육군", "상병") == [
        {"name": "기본훈련", "hours": 8},
        {"name": "작계훈련(전·후반기)", "hours": 12},
    ]


def test_training_progress_reports_personnel_category_for_nco() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099000",
        name="테스터",
        branch="육군",
        rank="하사",
        service_year=3,
        position="분대장",
        mobilization_status="동원미지정",
        status="active",
    )
    db.add(person)
    db.commit()

    progress = training_progress(db, person, 3)
    assert progress["personnel_category"] == "부사관"
    assert progress["target_hours"] == 28
    assert progress["training_plan"] == [{"name": "동원훈련Ⅱ형", "hours": 28}]

    db.close()


def test_officer_type_ii_target_stays_at_28_after_deferral() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099002",
        name="간부 시험",
        branch="육군",
        rank="하사",
        service_year=3,
        position="분대장",
        mobilization_status="동원미지정",
        status="active",
    )
    db.add(person)
    postponed_record = Education(
        person_id=person.military_number,
        education_year=3,
        training_year=2026,
        training_type="동원훈련Ⅱ형",
        training_round=1,
        attendance_status="연기",
        training_hours=0,
    )
    db.add(postponed_record)
    db.flush()
    from user.app.models.postpoment import Postponement

    db.add(Postponement(
        person_id=person.military_number,
        type="delay",
        reason="approved deferral",
        status="approved",
        training_year=2026,
        education_record_id=postponed_record.id,
    ))
    db.commit()

    progress = training_progress(db, person, 3)
    assert progress["officer_type_ii_makeup"] is False
    assert progress["target_hours"] == 28
    assert progress["required_hours"] == 28
    assert progress["training_plan"] == [{"name": "동원훈련Ⅱ형", "hours": 28}]
    assert progress["round_escalated"] is True

    db.close()


def test_officer_type_ii_makeup_target_uses_32_hours_with_carryover() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099003",
        name="간부 이월 시험",
        branch="육군",
        rank="하사",
        service_year=3,
        position="분대장",
        mobilization_status="동원미지정",
        status="active",
    )
    db.add(person)
    db.commit()

    progress = training_progress(db, person, 3, carryover_hours=8)
    assert progress["officer_type_ii_makeup"] is True
    assert progress["target_hours"] == 32
    assert progress["required_hours"] == 40
    assert progress["training_plan"] == [{"name": "동원훈련Ⅱ형", "hours": 32}]

    db.close()


def test_officer_type_ii_makeup_target_uses_32_after_repeated_absence_and_deferral() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099004",
        name="간부 보충훈련 시험",
        branch="육군",
        rank="하사",
        service_year=3,
        position="분대장",
        mobilization_status="동원미지정",
        status="active",
    )
    absence = Education(
        person_id=person.military_number,
        education_year=3,
        training_year=2026,
        training_type="동원훈련Ⅱ형",
        training_round=1,
        attendance_status="무단불참",
        training_hours=0,
        confirmed_by="approver",
    )
    deferral = Education(
        person_id=person.military_number,
        education_year=3,
        training_year=2026,
        training_type="동원훈련Ⅱ형",
        training_round=2,
        attendance_status="연기",
        training_hours=0,
    )
    db.add_all([person, absence, deferral])
    db.flush()
    db.add(Postponement(
        person_id=person.military_number,
        type="delay",
        reason="approved deferral",
        status="approved",
        training_year=2026,
        education_record_id=deferral.id,
    ))
    db.flush()

    progress = training_progress(db, person, 3)

    assert progress["officer_type_ii_makeup"] is True
    assert progress["target_hours"] == 32
    assert progress["required_hours"] == 32
    assert progress["training_plan"] == [{"name": "동원훈련Ⅱ형", "hours": 32}]
    db.close()


def test_training_progress_counts_attended_hours_immediately() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099001",
        name="테스터",
        branch="육군",
        rank="병장",
        service_year=3,
        position="소총수",
        mobilization_status="동원미지정",
        status="active",
    )
    db.add(person)
    db.add(Education(
        person_id=person.military_number,
        education_year=3,
        training_year=2026,
        training_type="동원훈련Ⅱ형",
        training_round=1,
        attendance_status="참석",
        training_hours=8,
    ))
    db.commit()

    progress = training_progress(db, person, 3)
    assert progress["completed_hours"] == 8
    assert progress["remaining_hours"] == 24
    assert progress["current_zero_training_hours"] is False

    db.close()


def test_overdue_scheduled_type_i_remains_unconfirmed_and_not_prosecutable() -> None:
    db = make_session()
    person = Person(
        military_number="26-70200002", name="예정 훈련", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원지정", status="active",
    )
    record = Education(
        person_id=person.military_number,
        education_year=1,
        training_year=2026,
        scheduled_date=date(2026, 9, 1),
        training_type="동원훈련Ⅰ형",
        training_round=1,
        attendance_status="scheduled",
        training_hours=0,
    )
    db.add_all([person, record])
    db.commit()

    progress = all_training_progress(db, person)[1]

    assert record.attendance_status == "scheduled"
    assert progress["prosecution_reason"] is None
    assert any("훈련 결과 미입력" in hint for hint in progress["review_hints"])
    assert db.scalars(select(AuditLog).where(AuditLog.record_id == record.id)).all() == []
    db.close()


def test_prosecution_page_only_includes_confirmed_type_i_or_round_three_absence() -> None:
    db = make_session()
    people = {
        key: Person(
            military_number=f"26-PROSECUTION-{key}", name=key, branch="육군", rank="병장",
            service_year=1, position="소총수", mobilization_status=status, status="active",
        )
        for key, status in (
            ("type-i-confirmed", "동원지정"),
            ("type-i-unconfirmed", "동원지정"),
            ("round-three-confirmed", "동원미지정"),
            ("round-three-unconfirmed", "동원미지정"),
            ("round-three-satisfied", "동원미지정"),
            ("outstanding-hours", "동원지정"),
            ("overdue", "동원지정"),
            ("no-record", "동원지정"),
        )
    }
    db.add_all(people.values())
    db.flush()
    records = [
        Education(
            person_id=people["type-i-confirmed"].military_number, education_year=1,
            training_year=2026, training_type="동원훈련Ⅰ형", training_round=1,
            attendance_status="무단불참", training_hours=0, confirmed_by="approver",
        ),
        Education(
            person_id=people["type-i-unconfirmed"].military_number, education_year=1,
            training_year=2026, training_type="동원훈련Ⅰ형", training_round=1,
            attendance_status="무단불참", training_hours=0,
        ),
        Education(
            person_id=people["round-three-confirmed"].military_number, education_year=1,
            training_year=2026, training_type="동원훈련Ⅱ형", training_round=3,
            attendance_status="무단불참", training_hours=0, confirmed_by="approver",
        ),
        Education(
            person_id=people["round-three-unconfirmed"].military_number, education_year=1,
            training_year=2026, training_type="동원훈련Ⅱ형", training_round=3,
            attendance_status="무단불참", training_hours=0,
        ),
        Education(
            person_id=people["round-three-satisfied"].military_number, education_year=1,
            training_year=2026, training_type="동원훈련Ⅱ형", training_round=3,
            attendance_status="이수", training_hours=32,
        ),
        Education(
            person_id=people["round-three-satisfied"].military_number, education_year=1,
            training_year=2026, training_type="동원훈련Ⅱ형", training_round=3,
            attendance_status="무단불참", training_hours=0, confirmed_by="approver",
        ),
        Education(
            person_id=people["overdue"].military_number, education_year=1,
            training_year=2026, scheduled_date=date.today() - timedelta(days=30),
            training_type="동원훈련Ⅰ형", training_round=1,
            attendance_status="scheduled", training_hours=0,
        ),
        Education(
            person_id=people["outstanding-hours"].military_number, education_year=1,
            training_year=2026, training_type="동원훈련Ⅰ형", training_round=1,
            attendance_status="참석", training_hours=8,
        ),
    ]
    db.add_all(records)
    db.commit()

    targets = list_prosecution_targets(db)

    assert {item["military_number"] for item in targets} == {
        people["type-i-confirmed"].military_number,
        people["round-three-confirmed"].military_number,
    }
    assert all(item["service_year"] == 1 for item in targets)
    db.close()


def test_scheduled_training_is_not_absent_before_its_date() -> None:
    db = make_session()
    person = Person(
        military_number="26-70200003", name="예정 훈련", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원지정", status="active",
    )
    record = Education(
        person_id=person.military_number,
        education_year=1,
        training_year=2026,
        scheduled_date=date.today() + timedelta(days=1),
        training_type="동원훈련Ⅰ형",
        training_round=1,
        attendance_status="scheduled",
        training_hours=0,
    )
    db.add_all([person, record])
    db.commit()

    progress = all_training_progress(db, person)[1]

    assert record.attendance_status == "scheduled"
    assert progress["prosecution_status"] is None
    assert progress["training_status"] == "훈련 예정"
    assert progress["round_escalated"] is False
    db.close()


def test_batch_reconciliation_reports_overdue_without_changing_attendance() -> None:
    db = make_session()
    overdue_person = Person(
        military_number="26-70200005", name="기한 경과", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원지정", status="active",
    )
    future_person = Person(
        military_number="26-70200006", name="훈련 예정", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원지정", status="active",
    )
    overdue_record = Education(
        person_id=overdue_person.military_number, education_year=1, training_year=2026,
        scheduled_date=date(2026, 10, 1), training_type="동원훈련Ⅰ형",
        attendance_status="scheduled", training_hours=0,
    )
    future_record = Education(
        person_id=future_person.military_number, education_year=1, training_year=2026,
        scheduled_date=date(2026, 10, 20), training_type="동원훈련Ⅰ형",
        attendance_status="scheduled", training_hours=0,
    )
    db.add_all([overdue_person, future_person, overdue_record, future_record])
    db.commit()

    changed = reconcile_all_due_training_absences(db, date(2026, 10, 10))

    assert changed == 1
    assert overdue_record.attendance_status == "scheduled"
    assert future_record.attendance_status == "scheduled"
    db.close()


def test_overdue_grace_starts_after_the_final_schedule_session() -> None:
    db = make_session()
    person = Person(
        military_number="26-OVERDUE-MULTIDAY", name="다일 훈련", branch="육군", rank="병장",
        service_year=1, mobilization_status="동원지정", status="active",
    )
    schedule = TrainingSchedule(
        title="다일 훈련", training_type="동원훈련Ⅰ형", training_round=1,
        service_year=1, status="scheduled",
    )
    db.add_all([person, schedule])
    db.flush()
    db.add_all([
        TrainingSession(schedule_id=schedule.id, day_number=1, session_date=date(2026, 6, 1)),
        TrainingSession(schedule_id=schedule.id, day_number=2, session_date=date(2026, 6, 10)),
    ])
    record = Education(
        person_id=person.military_number, education_year=1, training_year=2026,
        scheduled_date=date(2026, 6, 1), schedule_id=schedule.id,
        training_type="동원훈련Ⅰ형", training_round=1,
        attendance_status="scheduled", training_hours=0,
    )
    db.add(record)
    db.flush()

    assert reconcile_due_training_absences(db, person, date(2026, 6, 17)) == 0
    assert reconcile_due_training_absences(db, person, date(2026, 6, 18)) == 1
    assert record.attendance_status == "scheduled"
    db.close()


def test_multiday_schedule_crossing_kst_new_year_uses_last_session_for_grace() -> None:
    db = make_session()
    person = Person(
        military_number="26-OVERDUE-KST-NEW-YEAR", name="연말 다일 훈련", branch="육군",
        rank="병장", service_year=1, mobilization_status="동원지정", status="active",
    )
    schedule = TrainingSchedule(
        title="연말 다일 훈련", training_type="동원훈련Ⅰ형", training_round=1,
        service_year=1, status="scheduled",
    )
    db.add_all([person, schedule])
    db.flush()
    db.add_all([
        TrainingSession(schedule_id=schedule.id, day_number=1, session_date=date(2026, 12, 31)),
        TrainingSession(schedule_id=schedule.id, day_number=2, session_date=date(2027, 1, 1)),
    ])
    record = Education(
        person_id=person.military_number, education_year=1, training_year=2026,
        scheduled_date=date(2026, 12, 31), schedule_id=schedule.id,
        training_type="동원훈련Ⅰ형", training_round=1,
        attendance_status="scheduled", training_hours=0,
    )
    db.add(record)
    db.flush()

    assert reconcile_due_training_absences(db, person, date(2027, 1, 8)) == 0
    assert reconcile_due_training_absences(db, person, date(2027, 1, 9)) == 1
    db.close()


def test_postponed_rounds_and_next_year_no_show_only_advance_that_year() -> None:
    db = make_session()
    person = Person(
        military_number="26-POSTPONED-ROUNDS-NEXT-YEAR", name="연기 후 무단불참",
        branch="육군", rank="병장", service_year=2,
        mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    prior_rounds = [
        Education(
            person_id=person.military_number, education_year=1, training_year=2025,
            training_type="기본훈련", training_round=round_number,
            attendance_status="연기", training_hours=0,
        )
        for round_number in (1, 2)
    ]
    attended_round = Education(
        person_id=person.military_number, education_year=1, training_year=2025,
        training_type="기본훈련", training_round=3,
        attendance_status="참석", training_hours=8,
    )
    next_year_absence = Education(
        person_id=person.military_number, education_year=2, training_year=2026,
        training_type="기본훈련", training_round=1,
        attendance_status="무단불참", training_hours=0, confirmed_by="확인자",
    )
    db.add_all([*prior_rounds, attended_round, next_year_absence])
    db.flush()
    db.add_all([
        Postponement(
            person_id=person.military_number, type="delay", reason="approved postponement",
            status="approved", training_year=2025, education_record_id=record.id,
        )
        for record in prior_rounds
    ])
    db.flush()

    recalculated_rounds = _rounds_for_person(
        person.military_number,
        [*prior_rounds, attended_round, next_year_absence],
        db.scalars(select(Postponement).where(
            Postponement.person_id == person.military_number,
        )).all(),
        DEFAULT_STATUS_POLICIES,
    )
    progress = training_progress(db, person, 2)

    assert recalculated_rounds[(1, "기본훈련")] == 3
    assert recalculated_rounds[(2, "기본훈련")] == 2
    assert progress["round_escalated"] is True
    assert progress["prosecution_status"] is None
    assert person.military_number not in {
        item["military_number"] for item in list_prosecution_targets(db)
    }
    db.close()


@pytest.mark.parametrize(
    ("postponement_type", "expected_status"),
    [("delay", "postponed"), ("hold", "보류")],
)
def test_approved_postponement_or_hold_converts_overdue_schedule_without_prosecution(
    postponement_type: str, expected_status: str,
) -> None:
    db = make_session()
    person = Person(
        military_number="26-70200004", name="연기 훈련", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원지정", status="active",
    )
    from user.app.models.postpoment import Postponement

    record = Education(
        person_id=person.military_number,
        education_year=1,
        training_year=2026,
        scheduled_date=date(2026, 10, 1),
        training_type="동원훈련Ⅰ형",
        training_round=1,
        attendance_status="scheduled",
        training_hours=0,
    )
    postponement = Postponement(
        person_id=person.military_number,
        type=postponement_type,
        reason="승인된 연기 또는 보류",
        status="approved",
        training_year=2026,
    )
    db.add_all([person, record, postponement])
    db.commit()

    progress = all_training_progress(db, person)[1]

    assert record.attendance_status == "scheduled"
    assert progress["prosecution_status"] is None
    db.close()


def test_local_reserve_command_officer_has_basic_and_operations_plan() -> None:
    position = "지역예비군 부중대장"
    assert target_training_hours(3, "동원미지정", "육군", "대위", position) == 20
    assert training_plan(3, "동원미지정", "육군", "대위", position) == [
        {"name": "기본훈련", "hours": 8},
        {"name": "작계훈련(전·후반기)", "hours": 12},
    ]


def test_round_sequence_requires_unique_rounds_and_missed_predecessor() -> None:
    first_round = Education(
        id=1, person_id="sequence-test", education_year=2, training_type="기본훈련",
        training_round=1, attendance_status="무단불참", training_hours=0,
    )
    records = [first_round]

    assert training_round_sequence_error(
        records, "기본훈련", 1, "무단불참", 0, 8
    ) == "기본훈련 1차 기록이 이미 있습니다. 기존 기록을 수정하세요."
    assert training_round_sequence_error(
        records, "기본훈련", 3, "무단불참", 0, 8
    ) == "3차 전에 2차 기록이 필요합니다."
    assert training_round_sequence_error(
        [Education(id=2, person_id="sequence-test", education_year=2,
                   training_type="기본훈련", training_round=1,
                   attendance_status="completed", training_hours=8)],
        "기본훈련", 2, "scheduled", 0, 8,
    ) == "1차 훈련이 이미 충족되어 2차 기록은 등록할 수 없습니다."


def test_round_advancement_requires_confirmed_absence_or_approved_deferral() -> None:
    unconfirmed = Education(
        id=10, person_id="sequence-test", education_year=2, training_type="기본훈련",
        training_round=1, attendance_status="무단불참", training_hours=0,
    )
    confirmed = Education(
        id=11, person_id="sequence-test", education_year=2, training_type="기본훈련",
        training_round=1, attendance_status="무단불참", training_hours=0,
        confirmed_by="확인자",
    )
    scheduled = Education(
        id=12, person_id="sequence-test", education_year=2, training_type="기본훈련",
        training_round=1, attendance_status="scheduled", training_hours=0,
    )

    assert training_round_sequence_error(
        [unconfirmed], "기본훈련", 2, "scheduled", 0, 8,
    ) is not None
    assert training_round_sequence_error(
        [confirmed], "기본훈련", 2, "scheduled", 0, 8,
    ) is None
    assert training_round_sequence_error(
        [scheduled], "기본훈련", 2, "scheduled", 0, 8,
        approved_deferral_record_ids={12},
    ) is None


def test_round_ladder_resets_for_each_obligation_year() -> None:
    previous_year_attempt = Education(
        id=20, person_id="round-reset", education_year=1, training_type="기본훈련",
        training_round=1, attendance_status="무단불참", training_hours=0, confirmed_by="확인자",
    )
    current_year_attempt = Education(
        id=21, person_id="round-reset", education_year=2, training_type="기본훈련",
        training_round=1, attendance_status="이수", training_hours=8,
    )

    rounds = _rounds_for_person(
        "round-reset", [previous_year_attempt, current_year_attempt], [], DEFAULT_STATUS_POLICIES
    )

    assert rounds == {(1, "기본훈련"): 2, (2, "기본훈련"): 1}


def test_current_year_hours_count_before_resolving_prior_carryover() -> None:
    db = make_session()
    person = Person(
        military_number="26-CARRYOVER-001", name="이월 시간 산정", branch="육군", rank="병장",
        discharge_date=date(2024, 1, 1), service_year=2, mobilization_status="동원미지정",
        status="active",
    )
    db.add_all([
        person,
        Education(
            person_id=person.military_number, education_year=1, training_year=2025,
            training_type="동원훈련Ⅱ형", training_round=1, attendance_status="무단불참",
            training_hours=0, confirmed_by="확인자",
        ),
        Education(
            person_id=person.military_number, education_year=1, training_year=2025,
            training_type="동원훈련Ⅱ형", training_round=2, attendance_status="무단불참",
            training_hours=0, confirmed_by="확인자",
        ),
        Education(
            person_id=person.military_number, education_year=2, training_year=2026,
            training_type="동원훈련Ⅱ형", training_round=1, attendance_status="참석",
            training_hours=8,
        ),
    ])
    db.flush()

    recalculate_person(db, person.military_number, today=date(2026, 10, 6))
    db.flush()
    current_result = db.scalars(select(TrainingYearResult).where(
        TrainingYearResult.person_id == person.military_number,
        TrainingYearResult.service_year == 2,
        TrainingYearResult.training_type == "동원훈련Ⅱ형",
    )).one()
    prior_carryover = db.scalars(select(TrainingCarryover).where(
        TrainingCarryover.person_id == person.military_number,
        TrainingCarryover.origin_year == 1,
    )).one()

    assert current_result.required_hours == 32
    assert current_result.counted_hours == 8
    assert current_result.unmet_hours == 24
    assert prior_carryover.remaining_hours == 24
    projected = overlay_progress_with_recalculation(
        db, person, all_training_progress(db, person)
    )[2]
    assert projected["required_hours"] == 32
    assert projected["carryover_hours"] == 24
    assert projected["remaining_hours"] == 48
    db.close()


def test_closed_year_shortfall_is_recorded_without_advancing_next_year_ladder() -> None:
    db = make_session()
    person = Person(
        military_number="26-CARRYOVER-002", name="차수 미도달", branch="육군", rank="병장",
        discharge_date=date(2024, 1, 1), service_year=2, mobilization_status="동원미지정",
        status="active",
    )
    db.add_all([
        person,
        Education(
            person_id=person.military_number, education_year=1, training_year=2025,
            training_type="동원훈련Ⅱ형", training_round=1, attendance_status="참석",
            training_hours=8,
        ),
    ])
    db.flush()

    recalculate_person(db, person.military_number, today=date(2026, 10, 6))
    db.flush()
    result = db.scalars(select(TrainingYearResult).where(
        TrainingYearResult.person_id == person.military_number,
        TrainingYearResult.service_year == 1,
        TrainingYearResult.training_type == "동원훈련Ⅱ형",
    )).one()
    carryovers = db.scalars(select(TrainingCarryover).where(
        TrainingCarryover.person_id == person.military_number,
        TrainingCarryover.origin_year == 1,
    )).all()

    assert result.unmet_hours == 24
    assert result.carryover_status == "open"
    assert len(carryovers) == 1
    assert carryovers[0].current_round == 1
    db.close()


def test_round_satisfaction_requires_counted_hours_and_hold_does_not_advance() -> None:
    assert training_round_satisfied("보류", 0, 8) is False
    assert training_round_satisfied("참석", 4, 8) is False
    assert training_round_satisfied("참석", 8, 8) is True


def test_status_change_only_applies_from_the_current_year_onward() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099500",
        name="테스터",
        branch="육군",
        rank="병장",
        service_year=3,
        position="소총수",
        mobilization_status="동원미지정",
        status="active",
    )
    db.add(person)
    db.commit()

    # Completed years 1-2 as 동원미지정 (동원훈련Ⅱ형), now switches to 학생예비군 from year 3.
    apply_mobilization_status_change(db, person, "학생예비군")
    db.get(AnnualStatus, (person.military_number, 3)).semester_completed = True
    db.commit()

    assert mobilization_status_for_year(db, person, 1) == "동원미지정"
    assert mobilization_status_for_year(db, person, 2) == "동원미지정"
    assert mobilization_status_for_year(db, person, 3) == "학생예비군"
    assert mobilization_status_for_year(db, person, 4) == "학생예비군"
    assert person.mobilization_status == "학생예비군"

    progress = training_progress(db, person, 2)
    assert progress["target_hours"] == 32
    progress_current = training_progress(db, person, 3)
    assert progress_current["target_hours"] == 8

    db.close()


def test_absence_streak_is_a_review_hint_not_a_prosecution_trigger() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099600", name="테스터", branch="육군", rank="병장",
        service_year=3, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add_all([
        Education(person_id=person.military_number, education_year=1, training_year=2024,
                  training_type="기본훈련", training_round=3, attendance_status="무단불참", confirmed_by="unit-test"),
        Education(person_id=person.military_number, education_year=2, training_year=2025,
                  training_type="기본훈련", training_round=1, attendance_status="무단불참", confirmed_by="unit-test"),
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_type="기본훈련", training_round=1, attendance_status="무단불참", confirmed_by="unit-test"),
    ])

    progress = training_progress(db, person, 3)

    assert progress["consecutive_unexcused_absences"] == 3
    assert progress["absence_recorded"] is True
    assert progress["round_escalated"] is True
    assert progress["prosecution_status"] is None
    assert progress["prosecution_risk"] is False
    assert "연속 무단불참 3회" in progress["review_hints"]
    db.close()


def test_postponement_breaks_absence_streak_and_hold_is_not_prosecuted() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099700", name="테스터", branch="육군", rank="병장",
        service_year=4, mobilization_status="일부보류", status="active",
    )
    db.add(person)
    db.flush()
    db.add_all([
        Education(person_id=person.military_number, education_year=1, training_year=2024,
                  training_round=1, attendance_status="무단불참", confirmed_by="unit-test"),
        Education(person_id=person.military_number, education_year=2, training_year=2025,
                  training_round=1, attendance_status="연기"),
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_round=1, attendance_status="무단불참", confirmed_by="unit-test"),
        Education(person_id=person.military_number, education_year=4, training_year=2026,
                  training_round=2, attendance_status="무단불참", confirmed_by="unit-test"),
    ])
    db.commit()

    progress = training_progress(db, person, 4)

    assert progress["consecutive_unexcused_absences"] == 2
    assert progress["prosecution_status"] is None
    assert progress["prosecution_risk"] is False
    db.close()


def test_third_round_unexcused_basic_training_is_a_prosecution_trigger() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099800", name="테스터", branch="육군", rank="병장",
        service_year=5, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add(Education(
        person_id=person.military_number, education_year=5, training_year=2026,
        training_type="기본훈련", training_round=3,
        attendance_status="무단불참", training_hours=0, confirmed_by="unit-test",
    ))
    db.commit()

    progress = training_progress(db, person, 5)

    assert progress["current_zero_training_hours"] is True
    assert progress["prosecution_status"] == "고발대상자"
    assert progress["prosecution_reason"] == "기본훈련 3차 무단불참"
    db.close()


def test_future_year_training_gaps_are_not_prosecution_targets() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099900", name="테스터", branch="육군", rank="병장",
        service_year=4, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.commit()

    progress = training_progress(db, person, 5)

    assert progress["training_status"] == "훈련 예정"
    assert progress["prosecution_status"] is None
    assert progress["prosecution_risk"] is False
    db.close()


def test_third_round_unexcused_absence_prosecutes_before_service_year_three() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099950", name="테스터", branch="육군", rank="병장",
        service_year=2, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add(Education(
        person_id=person.military_number, education_year=2, training_year=2026,
        training_type="기본훈련", training_round=3,
        attendance_status="무단불참", confirmed_by="unit-test",
    ))
    db.commit()

    progress = training_progress(db, person, 2)

    assert progress["prosecution_status"] == "고발대상자"
    assert progress["prosecution_risk"] is True
    db.close()


def test_type_i_absence_prosecutes_immediately_in_service_year_one() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100000", name="간부", branch="육군", rank="하사",
        service_year=1, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add(Education(person_id=person.military_number, education_year=1, training_year=2026,
                     training_type="동원훈련Ⅰ형", training_round=1,
                     attendance_status="무단불참", confirmed_by="unit-test"))
    db.commit()

    progress = training_progress(db, person, 1)

    assert progress["prosecution_status"] == "고발대상자"
    assert progress["prosecution_reason"] == "동원훈련Ⅰ형 무단불참"
    db.close()


def test_approved_hold_excludes_linked_type_i_absence_from_prosecution() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100001", name="보류 대상", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원지정", status="active",
    )
    record = Education(
        person_id=person.military_number,
        education_year=1,
        training_year=2026,
        scheduled_date=date(2026, 6, 1),
        training_type="동원훈련Ⅰ형",
        training_round=1,
        attendance_status="무단불참",
        training_hours=0,
        confirmed_by="확인자",
    )
    db.add_all([person, record])
    db.flush()
    from user.app.models.postpoment import Postponement

    db.add(Postponement(
        person_id=person.military_number,
        type="hold",
        reason="법규보류",
        status="approved",
        training_year=2026,
        education_record_id=record.id,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 30),
    ))
    db.commit()

    progress = training_progress(db, person, 1)

    assert progress["absence_recorded"] is False
    assert progress["consecutive_unexcused_absences"] == 0
    assert progress["prosecution_status"] is None
    db.close()


def test_first_round_general_training_absence_only_escalates_round() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100100", name="병사", branch="육군", rank="병장",
        service_year=5, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add(Education(person_id=person.military_number, education_year=5, training_year=2026,
                     training_type="기본훈련", training_round=1,
                     attendance_status="무단불참", confirmed_by="unit-test"))
    db.commit()

    progress = training_progress(db, person, 5)

    assert progress["absence_recorded"] is True
    assert progress["round_escalated"] is True
    assert progress["prosecution_status"] is None
    assert progress["prosecution_risk"] is False
    db.close()


def test_postponed_type_ii_third_round_is_not_a_prosecution_trigger() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100200", name="병사", branch="육군", rank="병장",
        service_year=3, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add_all([
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_type="동원훈련Ⅱ형", training_round=1, attendance_status="연기"),
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_type="동원훈련Ⅱ형", training_round=2, attendance_status="연기"),
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_type="동원훈련Ⅱ형", training_round=3, attendance_status="연기"),
    ])
    db.commit()

    progress = training_progress(db, person, 3)

    assert progress["prosecution_status"] is None
    assert progress["prosecution_risk"] is False
    db.close()


def test_type_ii_training_completed_by_third_round_is_not_prosecuted() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100300", name="병사", branch="육군", rank="병장",
        service_year=3, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add_all([
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_type="동원훈련Ⅱ형", training_round=1, attendance_status="연기"),
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_type="동원훈련Ⅱ형", training_round=2, attendance_status="연기"),
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_type="동원훈련Ⅱ형", training_round=3, attendance_status="참석", training_hours=32),
    ])
    db.commit()

    progress = training_progress(db, person, 3)

    assert progress["prosecution_status"] is None
    db.close()


def test_type_ii_three_consecutive_round_absences_trigger_prosecution() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100310", name="병사", branch="육군", rank="병장",
        service_year=3, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add_all([
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_type="동원훈련Ⅱ형", training_round=round_number,
                  attendance_status="무단불참", confirmed_by="unit-test")
        for round_number in (1, 2, 3)
    ])
    db.commit()

    progress = training_progress(db, person, 3)

    assert progress["prosecution_status"] == "고발대상자"
    assert progress["prosecution_reason"] == "동원훈련Ⅱ형 3차 무단불참"
    db.close()


def test_type_ii_new_year_first_round_absence_is_not_prosecuted_after_prior_completion() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100311", name="병사", branch="육군", rank="병장",
        service_year=2, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add_all([
        Education(person_id=person.military_number, education_year=1, training_year=2025,
                  training_type="동원훈련Ⅱ형", training_round=1, attendance_status="연기"),
        Education(person_id=person.military_number, education_year=1, training_year=2025,
                  training_type="동원훈련Ⅱ형", training_round=2, attendance_status="연기"),
        Education(person_id=person.military_number, education_year=1, training_year=2025,
                  training_type="동원훈련Ⅱ형", training_round=3, attendance_status="참석",
                  training_hours=32),
        Education(person_id=person.military_number, education_year=2, training_year=2026,
                  training_type="동원훈련Ⅱ형", training_round=1,
                  attendance_status="무단불참", confirmed_by="unit-test"),
    ])
    db.commit()

    progress = training_progress(db, person, 2)

    assert progress["prosecution_status"] is None
    assert progress["prosecution_risk"] is False
    db.close()


def test_absences_in_earlier_years_do_not_create_a_later_year_prosecution_trigger() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100400", name="병사", branch="육군", rank="병장",
        service_year=3, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.flush()
    db.add_all([
        Education(person_id=person.military_number, education_year=1, training_year=2024,
                  training_type="기본훈련", training_round=2, attendance_status="무단불참", confirmed_by="unit-test"),
        Education(person_id=person.military_number, education_year=2, training_year=2025,
                  training_type="기본훈련", training_round=1, attendance_status="무단불참", confirmed_by="unit-test"),
    ])
    db.commit()

    progress = training_progress(db, person, 3)

    assert progress["consecutive_unexcused_absences"] == 2
    assert progress["absence_recorded"] is False
    assert progress["prosecution_status"] is None
    assert progress["prosecution_risk"] is False
    db.close()


@pytest.mark.parametrize(
    "training_type",
    ["동원훈련Ⅱ형", "기본훈련", "작계훈련(전·후반기)", "학생예비군"],
)
def test_third_round_unexcused_absence_prosecutes_for_each_training_type(training_type: str) -> None:
    db = make_session()
    person = Person(
        military_number=f"26-70200{len(training_type):03d}",
        name="예비군",
        branch="육군",
        rank="병장",
        service_year=1,
        position="소총수",
        mobilization_status="학생예비군" if training_type == "학생예비군" else "동원미지정",
        status="active",
    )
    db.add(person)
    db.add(Education(
        person_id=person.military_number,
        education_year=1,
        training_year=2026,
        training_type=training_type,
        training_round=3,
        attendance_status="무단불참",
        training_hours=0,
        confirmed_by="unit-test",
    ))
    db.commit()

    progress = training_progress(db, person, 1)

    assert progress["absence_recorded"] is True
    assert progress["prosecution_status"] == "고발대상자"
    assert progress["prosecution_reason"] == f"{training_type} 3차 무단불참"
    db.close()


def test_counted_hours_satisfy_round_even_when_status_is_attended() -> None:
    db = make_session()
    person = Person(
        military_number="26-70200001", name="예비군", branch="육군", rank="병장",
        service_year=5, position="소총수", mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    db.add_all([
        Education(person_id=person.military_number, education_year=5, training_year=2026,
                  training_type="기본훈련", training_round=3, attendance_status="참석",
                  training_hours=8),
        Education(person_id=person.military_number, education_year=5, training_year=2026,
                  training_type="기본훈련", training_round=3, attendance_status="무단불참",
                  training_hours=0),
    ])
    db.commit()

    progress = training_progress(db, person, 5)

    assert progress["completed_hours"] == 8
    assert progress["prosecution_status"] is None
    assert progress["prosecution_risk"] is False
    db.close()


def test_unfinished_hours_carry_through_enlisted_years_seven_and_eight() -> None:
    db = make_session()
    person = Person(
        military_number="26-70100300", name="병사", branch="육군", rank="병장",
        service_year=8, mobilization_status="동원미지정", status="active",
    )
    db.add(person)
    for year in range(1, 5):
        db.add(Education(
            person_id=person.military_number, education_year=year, training_year=2022 + year,
            training_type="동원훈련Ⅱ형", training_round=1,
            attendance_status="completed", training_hours=32,
        ))
    db.add_all([
        Education(person_id=person.military_number, education_year=5, training_year=2026,
                  training_type="기본훈련", training_round=1,
                  attendance_status="completed", training_hours=8),
        Education(person_id=person.military_number, education_year=5, training_year=2026,
                  training_type="작계훈련(전·후반기)", training_round=1,
              attendance_status="completed", training_hours=12),
        Education(person_id=person.military_number, education_year=6, training_year=2026,
                  training_type="기본훈련", training_round=1,
              attendance_status="completed", training_hours=8),
        Education(person_id=person.military_number, education_year=6, training_year=2026,
                  training_type="작계훈련(전·후반기)", training_round=1,
              attendance_status="completed", training_hours=8),
    ])
    db.commit()

    progress = all_training_progress(db, person)

    assert progress[6]["remaining_hours"] == 4
    assert progress[7]["target_hours"] == 0
    assert progress[7]["carryover_hours"] == 4
    assert progress[7]["required_hours"] == 4
    assert progress[8]["target_hours"] == 0
    assert progress[8]["carryover_hours"] == 4
    assert len(progress) == 9
    db.close()


def test_legacy_unassigned_person_without_designation_needs_review() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099900", name="테스터", branch="육군", rank="병장",
        service_year=5, mobilization_status="해당없음", status="active",
    )
    db.add(person)
    db.commit()

    progress = training_progress(db, person, 5)

    assert progress["training_status"] == "NEEDS_REVIEW"
    assert progress["needs_review_reason"] == "missing_designated_status"
    assert progress["required_hours"] == 0
    assert progress["training_plan"] == []
    db.close()
