"""Person service functions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from user.app.models.education import Education
from user.app.models.person import Person
from user.app.schemas.person import PersonCreate
from user.app.services.training import target_training_hours


def determine_registration_type(previous_training_hours: int | None) -> str:
    """Return '예비군 전입' if training hours are completed (> 0), otherwise '신규'."""
    if previous_training_hours is not None and previous_training_hours > 0:
        return "예비군 전입"
    return "신규"


def create_person(db: Session, payload: PersonCreate) -> Person:
    """Create a new person and differentiate between new and transferred reservists.

    Condition:
    - If previous_training_hours is null/None or <= 0, they are classified as '신규'.
    - If previous_training_hours > 0 (completed at least some hours), they are classified as '예비군 전입'.
    """
    previous_hours = payload.previous_training_hours

    # Differentiate registration type based on previous training hours
    computed_reg_type = determine_registration_type(previous_hours)

    person_data = payload.model_dump(exclude={"previous_training_hours"})
    if not person_data.get("registration_type"):
        person_data["registration_type"] = computed_reg_type

    person = Person(**person_data)
    db.add(person)
    db.flush()

    if previous_hours is not None and previous_hours > 0:
        target_year = person.service_year if person.service_year is not None and person.service_year >= 1 else 1
        remaining_hours = previous_hours

        # Sequentially allocate previous training hours from year 1 up to target_year,
        # capping each year at its target required hours so no year exceeds its training hours requirement.
        for y in range(1, target_year + 1):
            if remaining_hours <= 0:
                break

            target = target_training_hours(y, person.mobilization_status, person.branch)
            if target <= 0:
                continue

            allocated = min(remaining_hours, target)

            if allocated > 0:
                education = Education(
                    person_id=person.military_number,
                    education_year=y,
                    training_year=y,
                    training_type="기본훈련",
                    training_round=1,
                    attendance_status="completed",
                    training_hours=allocated,
                    notes=f"타 부대 전입 이수 훈련시간 ({y}년차)",
                )
                db.add(education)
                remaining_hours -= allocated

    db.commit()
    db.refresh(person)
    return person
