"""Coverage for the rank/mobilization-status-aware training rules."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import pytest
from datetime import date, timedelta

from user.app.models.person import Person
from user.app.services.training import (
	all_training_progress,
    apply_mobilization_status_change,
    mobilization_status_for_year,
    reconcile_all_due_training_absences,
    target_training_hours,
    training_plan,
    training_progress,
)
from user.app.models.education import Education


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


def test_officer_type_ii_makeup_target_increases_after_missed_round() -> None:
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
    db.add(Education(
        person_id=person.military_number,
        education_year=3,
        training_year=2026,
        training_type="동원훈련Ⅱ형",
        training_round=1,
        attendance_status="연기",
        training_hours=0,
    ))
    db.commit()

    progress = training_progress(db, person, 3)
    assert progress["officer_type_ii_makeup"] is True
    assert progress["target_hours"] == 32
    assert progress["required_hours"] == 32
    assert progress["training_plan"] == [{"name": "동원훈련Ⅱ형", "hours": 32}]

    db.close()


def test_officer_type_ii_makeup_target_increases_for_carryover() -> None:
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


def test_overdue_scheduled_type_i_becomes_unexcused_and_prosecutable() -> None:
    db = make_session()
    person = Person(
        military_number="26-70200002", name="예정 훈련", branch="육군", rank="병장",
        service_year=1, position="소총수", mobilization_status="동원지정", status="active",
    )
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
    db.add_all([person, record])
    db.commit()

    progress = all_training_progress(db, person)[1]

    assert record.attendance_status == "무단불참"
    assert progress["prosecution_reason"] == "동원훈련Ⅰ형 무단불참"
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


def test_batch_reconciliation_converts_only_overdue_scheduled_records() -> None:
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
        scheduled_date=date(2026, 10, 3), training_type="동원훈련Ⅰ형",
        attendance_status="scheduled", training_hours=0,
    )
    db.add_all([overdue_person, future_person, overdue_record, future_record])
    db.commit()

    changed = reconcile_all_due_training_absences(db, date(2026, 10, 2))

    assert changed == 1
    assert overdue_record.attendance_status == "무단불참"
    assert future_record.attendance_status == "scheduled"
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

    assert record.attendance_status == expected_status
    assert progress["prosecution_status"] is None
    db.close()


def test_local_reserve_command_officer_has_basic_and_operations_plan() -> None:
    position = "지역예비군 부중대장"
    assert target_training_hours(3, "동원미지정", "육군", "대위", position) == 20
    assert training_plan(3, "동원미지정", "육군", "대위", position) == [
        {"name": "기본훈련", "hours": 8},
        {"name": "작계훈련(전·후반기)", "hours": 12},
    ]


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
                  training_type="기본훈련", training_round=3, attendance_status="무단불참"),
        Education(person_id=person.military_number, education_year=2, training_year=2025,
                  training_round=1, attendance_status="무단불참"),
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_round=1, attendance_status="무단불참"),
    ])
    db.commit()

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
                  training_round=1, attendance_status="무단불참"),
        Education(person_id=person.military_number, education_year=2, training_year=2025,
                  training_round=1, attendance_status="연기"),
        Education(person_id=person.military_number, education_year=3, training_year=2026,
                  training_round=1, attendance_status="무단불참"),
        Education(person_id=person.military_number, education_year=4, training_year=2026,
                  training_round=2, attendance_status="무단불참"),
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
        attendance_status="무단불참", training_hours=0,
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
        attendance_status="무단불참",
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
                     attendance_status="무단불참"))
    db.commit()

    progress = training_progress(db, person, 1)

    assert progress["prosecution_status"] == "고발대상자"
    assert progress["prosecution_reason"] == "동원훈련Ⅰ형 무단불참"
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
                     attendance_status="무단불참"))
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
                  training_type="기본훈련", training_round=2, attendance_status="무단불참"),
        Education(person_id=person.military_number, education_year=2, training_year=2025,
                  training_type="기본훈련", training_round=1, attendance_status="무단불참"),
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


def test_legacy_unassigned_person_uses_non_designated_training_status() -> None:
    db = make_session()
    person = Person(
        military_number="26-70099900", name="테스터", branch="육군", rank="병장",
        service_year=5, mobilization_status="해당없음", status="active",
    )
    db.add(person)
    db.commit()

    progress = training_progress(db, person, 5)

    assert progress["mobilization_status"] == "동원미지정"
    assert progress["training_plan"] == [
        {"name": "기본훈련", "hours": 8},
        {"name": "작계훈련(전·후반기)", "hours": 12},
    ]
    db.close()
