"""Synthetic records in an in-memory DB; no production data is changed."""
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from user.app import models
from user.app.api.reservists import router
from user.app.database import get_db
from user.app.models.education import Education
from user.app.models.person import Person
from user.app.models.organization import OrganizationNode
from user.app.models.postpoment import Postponement
from user.app.models.squad import Squad
from user.app.models.training_schedule import TrainingSchedule, TrainingSession
from user.app.services.prosecution_draft import draft_sources


@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    models.Person.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def target(db):
    person = Person(military_number='test-001', name='가상대상자', branch='육군',
                    rank='병장', service_year=3, mobilization_status='동원미지정')
    db.add(person)
    db.flush()
    records = [Education(person_id=person.military_number, education_year=3,
                         training_year=2026, scheduled_date=date(2026, month, 1),
                         training_type='동원훈련Ⅱ형', training_round=month,
                         attendance_status='무단불참', confirmed_by='test-reviewer')
               for month in (1, 2, 3)]
    db.add_all(records)
    db.commit()
    return person, records


def test_sources_use_confirmed_records_without_inventing_private_details(db):
    person, records = target(db)
    result = draft_sources(db, person, today=date(2026, 11, 23))
    assert result['is_target'] is True
    assert [row['id'] for row in result['records']] == [row.id for row in records]
    assert result['records'][0]['dates'] == ['2026-01-01']
    assert result['person']['reserve_unit'] == ''
    assert 'address' not in result['person']
    assert 'birth_digits' not in result['person']
    assert result['records'][0]['schedule_title'] == ''
    assert result['records'][0]['training_year'] == 2026
    assert result['records'][0]['scheduled_hours'] is None
    assert result['records'][0]['completed_hours'] == 0
    assert result['records'][0]['confirmed_at'] is None
    assert 'location' not in result['records'][0]
    assert 'delivered_at' not in result['records'][0]
    assert not db.new and not db.dirty and not db.deleted


def test_person_unit_uses_organization_path_and_squad_fallback(db):
    person, _ = target(db)
    squad = Squad(name='1분대')
    root = OrganizationNode(name='가상동대', kind='root')
    db.add_all([squad, root])
    db.flush()
    person.squad = squad
    db.commit()
    assert draft_sources(db, person)['person']['reserve_unit'] == '1분대'
    platoon = OrganizationNode(name='2소대', kind='platoon', parent_id=root.id)
    db.add(platoon)
    db.flush()
    db.add(OrganizationNode(name='1분대', kind='squad', parent_id=platoon.id, squad_id=squad.id))
    db.commit()
    result = draft_sources(db, person)
    assert result['person'] == {
        'military_number': person.military_number, 'name': person.name,
        'rank': '병장', 'reserve_unit': '가상동대 > 2소대 > 1분대',
    }
    assert not db.new and not db.dirty and not db.deleted


def test_excludes_unconfirmed_excused_future_and_other_people(db):
    person, records = target(db)
    other = Person(military_number='other', name='다른사람')
    db.add(other)
    db.flush()
    extra = []
    for owner, confirmed, day in [(person.military_number, None, date(2026, 1, 2)),
                                   (person.military_number, 'tester', date(2027, 1, 1)),
                                   ('other', 'tester', date(2026, 1, 2)),
                                   (person.military_number, 'tester', date(2026, 1, 3))]:
        extra.append(Education(person_id=owner, education_year=3, training_year=2026,
                               training_type='작계훈련', training_round=1,
                               attendance_status='무단불참', confirmed_by=confirmed, scheduled_date=day))
    db.add_all(extra)
    db.flush()
    db.add(Postponement(person_id=person.military_number, type='delay', reason='시험',
                        status='approved', education_record_id=extra[-1].id))
    db.commit()
    result = draft_sources(db, person, today=date(2026, 11, 23))
    assert {row['id'] for row in result['records']} == {row.id for row in records}


def test_uses_session_dates_and_does_not_offer_non_target(db):
    person, records = target(db)
    schedule = TrainingSchedule(title='시험용 일정', training_type='동원훈련Ⅱ형', training_round=1, service_year=3)
    schedule.sessions = [TrainingSession(day_number=1, session_date=date(2026, 1, 1), credited_hours=8),
                         TrainingSession(day_number=2, session_date=date(2026, 1, 2), credited_hours=4)]
    db.add(schedule)
    db.flush()
    records[0].schedule_id = schedule.id
    records[0].confirmed_at = datetime(2026, 1, 3, 2, 30)
    db.commit()
    result = draft_sources(db, person, today=date(2026, 11, 23))
    assert result['records'][0]['dates'] == ['2026-01-01', '2026-01-02']
    assert result['records'][0]['schedule_title'] == '시험용 일정'
    assert result['records'][0]['scheduled_hours'] == 12
    assert result['records'][0]['completed_hours'] == 0
    assert result['records'][0]['confirmed_at'] == '2026-01-03T02:30:00+00:00'
    for record in records:
        record.attendance_status = 'completed'
    db.commit()
    result = draft_sources(db, person, today=date(2026, 11, 23))
    assert not result['is_target'] and not result['records']


def test_endpoint_handles_missing_person(db):
    person, _ = target(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        assert client.get('/reservists/missing/prosecution-draft').status_code == 404
        response = client.get(f'/reservists/{person.military_number}/prosecution-draft')
        assert response.status_code == 200
        assert response.json()['person']['name'] == '가상대상자'
