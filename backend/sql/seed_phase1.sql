-- Development seed: reset the sample data before generating 500 people.
PRAGMA foreign_keys = ON;

DELETE FROM audit_log;
DELETE FROM postponement;
DELETE FROM education;
DELETE FROM annual_status;
DELETE FROM assignment;
DELETE FROM person;
DELETE FROM app_user;
DELETE FROM squad;

INSERT INTO squad (id, name, description) VALUES
    (1, '1분대', '제1분대'),
    (2, '2분대', '제2분대'),
    (3, '3분대', '제3분대'),
    (4, '4분대', '제4분대'),
    (5, '5분대', '제5분대'),
    (6, '6분대', '제6분대'),
    (7, '7분대', '제7분대'),
    (8, '8분대', '제8분대'),
    (9, '9분대', '제9분대'),
    (10, '10분대', '제10분대'),
    (11, '11분대', '제11분대'),
    (12, '12분대', '제12분대'),
    (13, '13분대', '제13분대'),
    (14, '14분대', '제14분대'),
    (15, '15분대', '제15분대'),
    (16, '16분대', '제16분대'),
    (17, '17분대', '제17분대'),
    (18, '18분대', '제18분대'),
    (19, '19분대', '제19분대'),
    (20, '20분대', '제20분대');

/* Generate 500 people with unique military numbers and names. */
WITH RECURSIVE numbers(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM numbers WHERE number < 500
)
INSERT INTO person (
    military_number,
    name,
    branch,
    rank,
    unit,
    specialty,
    service_year,
    position,
    mobilization_status,
    status,
    squad_id
)
SELECT
    printf('26-%08d', 72000000 + number),
    printf('훈련병%03d', number),
    CASE ((number * 17 + number / 4 * 3) % 4)
        WHEN 0 THEN '육군'
        WHEN 1 THEN '해군'
        WHEN 2 THEN '공군'
        ELSE '해병대'
    END,
    CASE (number - 1) % 12
        WHEN 0 THEN '이병'
        WHEN 1 THEN '일병'
        WHEN 2 THEN '상병'
        WHEN 3 THEN '병장'
        WHEN 4 THEN '하사'
        WHEN 5 THEN '중사'
        WHEN 6 THEN '상사'
        WHEN 7 THEN '원사'
        WHEN 8 THEN '소위'
        WHEN 9 THEN '중위'
        WHEN 10 THEN '대위'
        ELSE '소령'
    END,
    CASE ((number * 17 + number / 4 * 3) % 4)
        WHEN 0 THEN printf('육군-%02d연대', ((number - 1) % 5) + 1)
        WHEN 1 THEN printf('해군-%02d전대', ((number - 1) % 5) + 1)
        WHEN 2 THEN printf('공군-%02d전투비행단', ((number - 1) % 5) + 1)
        ELSE printf('해병대-%02d연대', ((number - 1) % 5) + 1)
    END,
    CASE (number - 1) % 6
        WHEN 0 THEN '3111 101'
        WHEN 1 THEN '171 101'
        WHEN 2 THEN '222 101'
        WHEN 3 THEN '411 101'
        WHEN 4 THEN '241102'
        ELSE '231101'
    END,
    ((number - 1) % 6) + 1,
    CASE (number - 1) % 6
        WHEN 0 THEN '행정병'
        WHEN 1 THEN '통신병'
        WHEN 2 THEN '병기취급병'
        WHEN 3 THEN '의무병'
        WHEN 4 THEN '운전병'
        ELSE '보급병'
    END,
    CASE
        WHEN ((number - 1) % 6) + 1 BETWEEN 1 AND 4 AND number % 10 = 0 THEN '학생예비군'
        WHEN ((number - 1) % 6) + 1 BETWEEN 1 AND 4 AND number % 2 = 0 THEN '동원지정'
        WHEN ((number - 1) % 6) + 1 BETWEEN 1 AND 4 THEN '동원미지정'
        ELSE '해당없음'
    END,
    CASE WHEN number % 10 = 0 THEN 'on_leave' ELSE 'active' END,
    NULL
FROM numbers;

/* Spread active people from each branch/personnel category across 20 squads. */
WITH ranked_people AS (
    SELECT
        military_number,
        ((ROW_NUMBER() OVER (
            PARTITION BY branch,
                CASE
                    WHEN rank IN ('이병', '일병', '상병', '병장') THEN '병사'
                    WHEN rank IN ('하사', '중사', '상사', '원사') THEN '부사관'
                    WHEN rank IN ('소위', '중위', '대위', '소령', '중령', '대령') THEN '장교'
                    ELSE '기타'
                END
            ORDER BY military_number
        ) - 1) % 20) + 1 AS squad_id
    FROM person
    WHERE status = 'active'
)
UPDATE person
SET squad_id = (
    SELECT ranked_people.squad_id
    FROM ranked_people
    WHERE ranked_people.military_number = person.military_number
)
WHERE military_number IN (SELECT military_number FROM ranked_people);

/* Mobilization status is assigned independently for each service year. */
WITH RECURSIVE people(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM people WHERE number < 500
), years(service_year) AS (
    SELECT 0
    UNION ALL
    SELECT service_year + 1 FROM years WHERE service_year < 8
)
INSERT INTO annual_status (person_id, service_year, mobilization_status)
SELECT
    printf('26-%08d', 72000000 + people.number),
    years.service_year,
    CASE
        WHEN years.service_year BETWEEN 1 AND 4 AND people.number % 10 = 0 THEN '학생예비군'
        WHEN years.service_year BETWEEN 1 AND 4 AND people.number % 2 = 0 THEN '동원지정'
        WHEN years.service_year BETWEEN 1 AND 4 THEN '동원미지정'
        ELSE '해당없음'
    END
FROM people CROSS JOIN years;

/* Add assignments for every person assigned to a squad. */
WITH RECURSIVE numbers(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM numbers WHERE number < 500
)
INSERT INTO assignment (person_id, squad_id, assigned_date, status)
SELECT
    printf('26-%08d', 72000000 + number),
    (SELECT squad_id FROM person WHERE military_number = printf('26-%08d', 72000000 + number)),
    date('2026-09-01', printf('+%d day', (number - 1) % 30)),
    'assigned'
FROM numbers
WHERE number % 10 <> 0;

/* Seed completed training that matches each person's annual training plan.
   The calendar year is derived from the current year and service-year offset. */
WITH training_candidates AS (
    SELECT
        person.military_number,
        person.branch,
        person.rank,
        person.service_year AS current_service_year,
        annual_status.service_year,
        annual_status.mobilization_status,
        CASE
            WHEN annual_status.service_year BETWEEN 1 AND 6
                AND person.rank IN ('하사', '중사', '상사', '원사', '소위', '중위', '대위', '소령', '중령', '대령')
                AND annual_status.mobilization_status = '동원지정'
                THEN 'type_i'
            WHEN annual_status.service_year BETWEEN 1 AND 6
                AND person.rank IN ('하사', '중사', '상사', '원사', '소위', '중위', '대위', '소령', '중령', '대령')
                THEN 'type_ii'
            WHEN annual_status.service_year BETWEEN 1 AND 6
                AND annual_status.mobilization_status = '학생예비군'
                THEN 'student'
            WHEN annual_status.service_year BETWEEN 1 AND 4
                AND annual_status.mobilization_status = '동원지정'
                THEN 'type_i'
            WHEN annual_status.service_year BETWEEN 1 AND 4
                AND annual_status.mobilization_status = '동원미지정'
                THEN 'type_ii'
            WHEN annual_status.service_year BETWEEN 5 AND 6
                THEN 'basic_and_operations'
            ELSE 'none'
        END AS plan_kind
    FROM person
    JOIN annual_status ON annual_status.person_id = person.military_number
    WHERE annual_status.service_year BETWEEN 1 AND person.service_year
), training_records AS (
    SELECT
        military_number,
        current_service_year,
        service_year,
        CASE plan_kind
            WHEN 'type_i' THEN '동원훈련Ⅰ형'
            WHEN 'type_ii' THEN '동원훈련Ⅱ형'
            WHEN 'student' THEN '학생예비군'
            WHEN 'basic_and_operations' THEN '기본훈련'
        END AS training_type,
        CASE
            WHEN plan_kind = 'student' THEN 8
            WHEN plan_kind = 'type_i' THEN 28
            WHEN plan_kind = 'type_ii' AND branch = '공군' THEN 28
            WHEN plan_kind = 'type_ii' AND rank IN ('하사', '중사', '상사', '원사', '소위', '중위', '대위', '소령', '중령', '대령') THEN 28
            WHEN plan_kind = 'type_ii' THEN 32
            WHEN plan_kind = 'basic_and_operations' THEN 8
        END AS training_hours
    FROM training_candidates
    WHERE plan_kind <> 'none'
    UNION ALL
    SELECT
        military_number,
        current_service_year,
        service_year,
        '작계훈련(전·후반기)',
        12
    FROM training_candidates
    WHERE plan_kind = 'basic_and_operations'
)
INSERT INTO education (
    person_id,
    education_year,
    training_year,
    training_type,
    training_round,
    attendance_status,
    training_hours,
    notes
)
SELECT
    military_number,
    service_year,
    CAST(strftime('%Y', 'now') AS INTEGER) - current_service_year + service_year,
    training_type,
    1,
    'completed',
    training_hours,
    '개발용 연차별 훈련계획 이수 기록'
FROM training_records;

/* Add a pending postponement for every tenth person. */
WITH RECURSIVE numbers(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM numbers WHERE number < 500
)
INSERT INTO postponement (person_id, type, reason, status)
SELECT
    printf('26-%08d', 72000000 + number),
    CASE WHEN number % 20 = 0 THEN 'hold' ELSE 'delay' END,
    printf('자동 생성 사유 %03d', number),
    'pending'
FROM numbers
WHERE number % 10 = 0;

INSERT INTO app_user (id, username, password_hash, role) VALUES
    (1, 'admin', 'placeholder_hash', 'admin');

INSERT INTO audit_log (user_id, action, table_name, record_id) VALUES
    (1, 'SEED', 'person', 500),
    (1, 'SEED', 'squad', 9),
    (1, 'SEED', 'assignment', 450),
    (1, 'SEED', 'education', (SELECT COUNT(*) FROM education)),
    (1, 'SEED', 'postponement', 50),
    (1, 'SEED', 'app_user', 1);
