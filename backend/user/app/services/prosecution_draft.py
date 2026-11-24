"""Read-only source facts for a staff-reviewed complaint draft."""
from datetime import date, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from user.app.models.education import Education
from user.app.models.organization import OrganizationNode
from user.app.models.person import Person
from user.app.services.training import (
    UNEXCUSED_ABSENCE, _approved_excusal_record_ids, all_training_progress,
)


def _reserve_unit(db: Session, person: Person) -> str:
    if person.squad is None:
        return ''
    nodes = {node.id: node for node in db.scalars(select(OrganizationNode)).all()}
    node = next((item for item in nodes.values() if item.squad_id == person.squad_id), None)
    names, visited = [], set()
    while node is not None and node.id not in visited:
        names.append(node.name)
        visited.add(node.id)
        node = nodes.get(node.parent_id)
    return ' > '.join(reversed(names)) or person.squad.name


def draft_sources(db: Session, person: Person, *, today: date | None = None) -> dict:
    today = today or date.today()
    targets = [row for row in all_training_progress(db, person)
               if row.get('prosecution_status') == '고발대상자']
    years = {row['service_year'] for row in targets}
    records = list(db.scalars(select(Education).where(
        Education.person_id == person.military_number,
    ).order_by(Education.scheduled_date, Education.id)).all())
    excluded = _approved_excusal_record_ids(db, person.military_number, records)
    candidates = []
    for record in records:
        if (record.education_year not in years or record.id in excluded
                or record.attendance_status not in UNEXCUSED_ABSENCE
                or not record.confirmed_by):
            continue
        sessions = record.schedule.sessions if record.schedule else []
        dates = sorted({session.session_date for session in sessions})
        if not dates and record.scheduled_date:
            dates = [record.scheduled_date]
        # Demo early results must not turn future training into a complaint fact.
        if dates and dates[-1] >= today:
            continue
        confirmed_at = record.confirmed_at
        # Training results are stored as UTC-naive timestamps by training_results._now().
        if confirmed_at is not None and confirmed_at.tzinfo is None:
            confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)
        candidates.append({
            'id': record.id, 'training_type': record.training_type,
            'training_round': record.training_round, 'service_year': record.education_year,
            'dates': [day.isoformat() for day in dates],
            'attendance_status': record.attendance_status,
            'confirmed_by': record.confirmed_by,
            'schedule_title': record.schedule.title if record.schedule else '',
            'training_year': record.training_year,
            # Session credited_hours is the allowed credit ceiling, not attended hours.
            'scheduled_hours': sum(session.credited_hours for session in sessions) if sessions else None,
            'completed_hours': record.training_hours,
            'confirmed_at': confirmed_at.astimezone(timezone.utc).isoformat() if confirmed_at else None,
        })
    return {
        'person': {'military_number': person.military_number, 'name': person.name,
                   'rank': person.rank or '', 'reserve_unit': _reserve_unit(db, person)},
        'is_target': bool(targets),
        'reasons': list(dict.fromkeys(str(row['prosecution_reason']) for row in targets
                                     if row.get('prosecution_reason'))),
        'records': candidates,
    }
