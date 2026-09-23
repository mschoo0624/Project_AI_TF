"""Dashboard headcounts based on current service years, not calendar years."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.models.annual_status import AnnualStatus
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.postpoment import Postponement
from user.app.services.assignment import personnel_category
from user.app.services.training import COMPLETED, DESIGNATED, PARTIAL_HOLD, UNEXCUSED_ABSENCE, target_training_hours


def dashboard_counts(db: Session) -> dict[str, int]:
    people = db.scalars(select(Person)).all()
    annual = {(row.person_id, row.service_year): row.mobilization_status
              for row in db.scalars(select(AnnualStatus)).all()}
    records = defaultdict(list)
    for row in db.scalars(select(Education)).all():
        records[row.person_id].append(row)
    approved = defaultdict(set)
    for row in db.scalars(select(Postponement).where(Postponement.status == "approved")).all():
        approved[row.person_id].add(row.training_year)

    counts = dict(total_people=len(people), held_or_delayed=0, prosecution_people=0,
                  training_targets=0, training_completed=0, absent_people=0)
    for person in people:
        current = person.service_year
        status = annual.get((person.military_number, current), person.mobilization_status)
        if (status in PARTIAL_HOLD
                or person.status in {"hold", "on_hold", "delay", "delayed", "postponed", "보류", "연기"}
                or (current is not None and current in approved[person.military_number])):
            counts["held_or_delayed"] += 1
        if current is None or not 0 <= current <= 8:
            continue

        completed = defaultdict(int)
        risk = False
        absent = False
        for row in records[person.military_number]:
            if row.attendance_status in COMPLETED:
                completed[row.education_year] += row.training_hours
            if row.attendance_status in UNEXCUSED_ABSENCE:
                absent |= row.education_year == current
                row_status = annual.get((person.military_number, row.education_year), person.mobilization_status)
                risk |= row.education_year <= current and (
                    row.training_round >= 3 or (1 <= row.education_year <= 4 and row_status in DESIGNATED))
        counts["prosecution_people"] += int(risk)
        counts["absent_people"] += int(absent)

        carryover = 0
        required = 0
        remaining = 0
        for year in range(current + 1):
            year_status = annual.get((person.military_number, year), person.mobilization_status)
            target = target_training_hours(year, year_status, person.branch, person.rank)
            required = target + (carryover if 1 <= year <= 6 else 0)
            remaining = max(required - completed[year], 0)
            carryover = remaining if year < 6 else 0
        if required > 0:
            counts["training_targets"] += 1
            counts["training_completed"] += int(remaining == 0)
    return counts


def daily_counts(db: Session, selected_date: date) -> dict[str, object]:
    counts = dict(hold=0, delay=0)
    # approved_at is stored as naive UTC; dashboard days are Korean calendar days.
    start = datetime.combine(selected_date, time(), tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc).replace(tzinfo=None)
    approved = db.scalars(select(Postponement).where(Postponement.status == "approved",
                         Postponement.approved_at >= start, Postponement.approved_at < start + timedelta(days=1))).all()
    for key, types in (("hold", {"hold", "보류"}), ("delay", {"delay", "연기"})):
        counts[key] = len({row.person_id for row in approved if row.type in types})
    return {"date": selected_date.isoformat(), "counts": counts}


def composition_counts(db: Session) -> dict[str, object]:
    """Use existing rank, service year and position fields without inferring corps."""
    totals = {"officers": 0, "soldiers": 0, "other": 0}
    years = {"1~4년차": 0, "5~6년차": 0, "7~8년차": 0, "0년차/미등록": 0}
    positions = defaultdict(int)
    for rank, year, position in db.execute(select(Person.rank, Person.service_year, Person.position)):
        category = personnel_category(rank)
        key = "soldiers" if category == "병사" else "officers" if category in {"장교", "부사관"} else "other"
        totals[key] += 1
        if key == "soldiers":
            group = "1~4년차" if year in range(1, 5) else "5~6년차" if year in (5, 6) else "7~8년차" if year in (7, 8) else "0년차/미등록"
            years[group] += 1
        positions[(position or "").strip() or "미등록"] += 1
    return {**totals, "service_years": years,
            "positions": [{"label": label, "count": count} for label, count in sorted(positions.items(), key=lambda item: (-item[1], item[0]))]}
