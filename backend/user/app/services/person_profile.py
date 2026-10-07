import re

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from user.app.models.audit_log import AuditLog
from user.app.models.person import Person
from user.app.services.assignment import BRANCHES, POSITION_SPECIALTIES
from user.app.services.training import apply_mobilization_status_change
from user.app.services.training_recalculation import recalculate_person

STATUSES = {"active": "복무 중", "on_leave": "휴가 중", "inactive": "비활성"}
MOBILIZATION = ["동원지정", "동원미지정", "학생예비군", "일부보류", "해당없음"]


class ProfileError(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__("입력 내용을 확인해 주세요.")


def profile_options():
    return {"branches": list(BRANCHES), "statuses": STATUSES,
            "mobilization_statuses": MOBILIZATION,
            "specialties": {position: list(primary + similar)
                            for position, (primary, similar) in POSITION_SPECIALTIES.items()}}


def save_profile(
    db: Session, person: Person, values: dict, actor: str = "미인증 요청",
    actor_user_id: int | None = None,
) -> Person:
    values = {key: value.strip() if isinstance(value, str) else value for key, value in values.items()}
    errors = {}
    number = values["military_number"]
    if not number or len(number) > 50 or not re.fullmatch(r"[0-9-]+", number):
        errors["military_number"] = "군번은 숫자와 하이픈으로 1~50자 입력하세요."
    elif number != person.military_number and db.get(Person, number) is not None:
        errors["military_number"] = "이미 등록된 군번입니다. 다른 사람과 중복될 수 없습니다."
    if not values["name"] or len(values["name"]) > 100:
        errors["name"] = "성명은 1~100자로 입력하세요."
    if len(values["unit"]) > 100:
        errors["unit"] = "소속 부대는 100자 이내로 입력하세요."
    if values["branch"] not in BRANCHES:
        errors["branch"] = "올바른 군별을 선택하세요."
    if values["status"] not in STATUSES and values["status"] != person.status:
        errors["status"] = "올바른 상태를 선택하세요."
    mobilization = values["mobilization_status"]
    if mobilization not in MOBILIZATION and mobilization != person.mobilization_status:
        errors["mobilization_status"] = "올바른 동원 상태를 선택하세요."
    if 1 <= (person.service_year or 0) <= 4 and mobilization in {"", "해당없음"}:
        errors["mobilization_status"] = "1~4년차는 동원 상태를 지정해야 합니다."
    code = re.sub(r"[\s-]", "", values["specialty"])
    matching = [position for position, groups in POSITION_SPECIALTIES.items()
                if code in groups[0] + groups[1]]
    if not matching:
        errors["specialty"] = "등록된 주특기 번호가 아닙니다. 주특기 기준표를 확인하세요."
    elif values["position"] not in matching:
        errors["position"] = f"입력한 주특기에 맞는 직책은 {', '.join(matching)}입니다."
    if errors:
        raise ProfileError(errors)

    try:
        if number != person.military_number:
            old_number = person.military_number
            copied = {column.name: getattr(person, column.name) for column in Person.__table__.columns}
            copied["military_number"] = number
            replacement = Person(**copied)
            db.add(replacement)
            db.flush()
            # Move every declared foreign-key reference before deleting the old identity.
            for table in Person.metadata.sorted_tables:
                for fk in table.foreign_keys:
                    if fk.target_fullname == "person.military_number":
                        db.execute(update(table).where(fk.parent == old_number).values({fk.parent.name: number}))
            db.execute(delete(Person).where(Person.military_number == old_number).execution_options(synchronize_session=False))
            db.expunge(person)
            db.expire_all()
            person = replacement
        for field in ("name", "branch", "status", "position"):
            setattr(person, field, values[field])
        person.unit = values["unit"] or None
        person.specialty = code
        if "discharge_date" in values:
            person.discharge_date = values["discharge_date"]
        if "callup_release_date" in values:
            person.callup_release_date = values["callup_release_date"]
        if mobilization != (person.mobilization_status or ""):
            apply_mobilization_status_change(db, person, mobilization)
        recalculate_person(
            db, person.military_number, 1, "status_change", actor,
            actor_user_id=actor_user_id,
        )
        db.commit()
        db.refresh(person)
        return person
    except Exception:
        db.rollback()
        raise
