"""Headcounts must distinguish absence, incomplete training and duplicate requests."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from user.app.database import Base
from user.app.models.person import Person
from user.app.models.education import Education
from user.app.models.annual_status import AnnualStatus
from user.app.models.postpoment import Postponement
from user.app.api.dashboard import dashboard_summary
from user.app.services.training import all_training_progress
from user.app.services.dashboard import daily_counts, composition_counts
from datetime import date, datetime


def test_summary_uses_unique_people_and_current_service_year():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        people = [Person(military_number=str(i), name='Test', branch='육군', rank='병장',
                         service_year=1, mobilization_status='동원지정', status='active') for i in range(6)]
        people[3].service_year = 7
        people[4].service_year = 2
        people[4].mobilization_status = '학생예비군'
        people[5].mobilization_status = '일부보류'
        db.add_all(people)
        db.add(AnnualStatus(person_id='4', service_year=1, mobilization_status='동원미지정'))
        db.add_all([
            Education(person_id='0', education_year=1, training_hours=28, attendance_status='completed'),
            Education(person_id='1', education_year=1, training_hours=0, attendance_status='unexcused_absence', training_round=1),
            Education(person_id='1', education_year=1, training_hours=0, attendance_status='unexcused_absence', training_round=3),
            Education(person_id='4', education_year=2, training_hours=8, attendance_status='completed'),
            Postponement(person_id='2', reason='test', training_year=1, status='approved'),
            Postponement(person_id='2', reason='duplicate', training_year=1, status='approved'),
            Postponement(person_id='0', reason='pending', training_year=1, status='pending'),
            Postponement(person_id='4', reason='past', training_year=1, status='approved'),
        ])
        db.commit()
        result = dashboard_summary(db)
        assert result['total_people'] == 6
        assert result['held_or_delayed'] == 2
        assert result['prosecution_people'] == 1
        assert result['absent_people'] == 1
        assert result['training_targets'] == 4
        assert result['training_completed'] == 1
        # The dashboard must agree with the detailed training page, including carryover.
        progress = [all_training_progress(db, person)[person.service_year] for person in people]
        assert result['training_targets'] == sum(p['required_hours'] > 0 for p in progress)
        assert result['training_completed'] == sum(p['required_hours'] > 0 and p['completed'] for p in progress)
        assert result['prosecution_people'] == sum(p['prosecution_risk'] for p in progress)


def test_empty_database_summary():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        summary = dashboard_summary(db)
        for key in ('total_people', 'held_or_delayed', 'prosecution_people', 'training_targets', 'training_completed', 'absent_people'):
            assert summary[key] == 0
        assert summary['composition']['positions'] == []
        assert sum(summary['composition']['service_years'].values()) == 0


def test_composition_counts_existing_fields_and_refreshes_after_edit():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for index, (rank, year, position) in enumerate([
            ('병장', 1, '통신병'), ('일병', 5, '통신병'), ('병장', 8, None),
            ('병장', 0, ''), ('하사', 2, '행정병'), ('대위', 3, ' 행정병 '), (None, None, '보충'),
        ]):
            db.add(Person(military_number=str(index), name='Test', branch='육군', rank=rank, service_year=year, position=position))
        db.commit()
        result = dashboard_summary(db)['composition']
        assert (result['officers'], result['soldiers'], result['other']) == (2, 4, 1)
        assert list(result['service_years'].values()) == [1, 1, 1, 1]
        assert {row['label']: row['count'] for row in result['positions']} == {'통신병': 2, '행정병': 2, '미등록': 2, '보충': 1}
        assert sum(row['count'] for row in result['positions']) == 7
        person = db.get(Person, '0')
        person.service_year = 6
        person.position = '의무병'
        db.commit()
        updated = composition_counts(db)
        assert updated['service_years']['1~4년차'] == 0
        assert updated['service_years']['5~6년차'] == 2
        assert {row['label']: row['count'] for row in updated['positions']}['의무병'] == 1


def test_daily_counts_korean_day_boundaries_and_unique_approvals():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Person(military_number='1', name='Test', branch='육군'))
        db.add_all([
            Postponement(person_id='1', type='hold', reason='test', status='approved', approved_at=datetime(2026, 9, 21, 15)),
            Postponement(person_id='1', type='hold', reason='duplicate', status='approved', approved_at=datetime(2026, 9, 22, 14, 59)),
            Postponement(person_id='1', type='delay', reason='next day', status='approved', approved_at=datetime(2026, 9, 22, 15)),
            Postponement(person_id='1', type='delay', reason='undated', status='approved'),
        ])
        db.commit()
        assert daily_counts(db, date(2026, 9, 22))['counts'] == dict(hold=1, delay=0)
