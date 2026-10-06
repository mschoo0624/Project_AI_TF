"""Headcounts must distinguish absence, incomplete training and duplicate requests."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from user.app.database import Base
from user.app.models.person import Person
from user.app.models.education import Education
from user.app.models.annual_status import AnnualStatus
from user.app.models.postpoment import Postponement
from user.app.api.dashboard import dashboard_summary
from user.app.api.reservists import list_prosecution_targets, list_training_review_targets
from user.app.services.training import all_training_progress
from user.app.services.dashboard import daily_counts, composition_counts
from datetime import date, datetime, timedelta


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
            Education(person_id='1', education_year=1, training_hours=0, attendance_status='unexcused_absence', training_round=1, confirmed_by='unit-test'),
            Education(person_id='1', education_year=1, training_hours=0, attendance_status='unexcused_absence', training_round=3, confirmed_by='unit-test'),
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


def test_training_review_list_includes_missing_record_and_excludes_approved_postponement():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Person(military_number='review', name='미이수', branch='육군', rank='병장',
                     service_year=1, position='소총수', mobilization_status='동원미지정', status='active'),
            Person(military_number='postponed', name='연기', branch='육군', rank='병장',
                     service_year=1, position='소총수', mobilization_status='동원미지정', status='active'),
        ])
        db.add(Postponement(
            person_id='postponed', reason='훈련 연기',
            training_year=date.today().year, status='approved',
        ))
        db.commit()

        targets = list_training_review_targets(db)

        assert len(targets) == 2
        assert {target['military_number'] for target in targets} == {'review', 'postponed'}
        assert all(target['review_years'] == [1] for target in targets)
        assert all(target['remaining_hours'] == 32 for target in targets)


def test_training_review_list_excludes_future_scheduled_session():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        person = Person(
            military_number='future-session', name='훈련 예정', branch='육군', rank='병장',
            service_year=1, position='소총수', mobilization_status='동원미지정', status='active',
        )
        db.add(person)
        db.add(Education(
            person_id=person.military_number,
            education_year=1,
            training_year=date.today().year,
            scheduled_date=date.today() + timedelta(days=1),
            training_type='동원훈련Ⅱ형',
            training_round=1,
            attendance_status='scheduled',
            training_hours=0,
        ))
        db.commit()

        assert list_training_review_targets(db) == []


def test_no_show_without_confirmer_metadata_stays_in_review_not_prosecution():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        person = Person(
            military_number='unconfirmed-no-show', name='확인자 미등록', branch='육군', rank='병장',
            service_year=3, position='소총수', mobilization_status='동원지정', status='active',
        )
        db.add(person)
        db.add(Education(
            person_id=person.military_number,
            education_year=3,
            training_year=date.today().year,
            training_type='동원훈련Ⅰ형',
            training_round=1,
            attendance_status='무단불참',
            training_hours=0,
        ))
        db.commit()

        progress = all_training_progress(db, person)[3]
        review = list_training_review_targets(db)

        assert progress['absence_recorded'] is False
        assert progress['prosecution_risk'] is False
        assert any('확인자 정보 누락' in hint for hint in progress['review_hints'])
        person_review = next(row for row in review if row['military_number'] == person.military_number)
        assert any(row['reason'] == 'confirming_user_metadata_missing' for row in person_review['review_rows'])
        assert all(row['military_number'] != person.military_number for row in list_prosecution_targets(db))


def test_training_review_hours_do_not_double_count_carryover():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Person(
            military_number='carryover-review', name='이월 검토', branch='육군', rank='병장',
            service_year=2, position='소총수', mobilization_status='동원미지정', status='active',
        ))
        db.commit()

        target = list_training_review_targets(db)[0]

        assert target['review_years'] == [1, 2]
        assert target['remaining_hours'] == 64


def test_dashboard_completes_officer_type_two_at_28_hours():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        person = Person(
            military_number='officer-makeup', name='간부 보충훈련', branch='육군',
            rank='하사', service_year=1, position='분대장',
            mobilization_status='동원미지정', status='active',
        )
        db.add(person)
        db.add(Education(
                person_id=person.military_number, education_year=1, training_year=2026,
                training_type='동원훈련Ⅱ형', training_round=2,
                attendance_status='completed', training_hours=28,
            ))
        db.commit()

        result = dashboard_summary(db)

        assert result['training_targets'] == 1
        assert result['training_completed'] == 1


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
