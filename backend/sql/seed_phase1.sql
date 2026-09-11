-- Development seed: reset the sample data before generating 500 people.
PRAGMA foreign_keys = ON;

DELETE FROM audit_log;
DELETE FROM postponement;
DELETE FROM education;
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
    (9, '9분대', '제9분대');

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
    (number - 1) % 9,
    CASE (number - 1) % 6
        WHEN 0 THEN '행정병'
        WHEN 1 THEN '통신병'
        WHEN 2 THEN '병기취급병'
        WHEN 3 THEN '의무병'
        WHEN 4 THEN '운전병'
        ELSE '보급병'
    END,
    CASE
        WHEN (number - 1) % 9 BETWEEN 1 AND 4 AND number % 10 = 0 THEN '학생예비군'
        WHEN (number - 1) % 9 BETWEEN 1 AND 4 AND number % 2 = 0 THEN '동원지정'
        WHEN (number - 1) % 9 BETWEEN 1 AND 4 THEN '동원미지정'
        ELSE '해당없음'
    END,
    CASE WHEN number % 10 = 0 THEN 'on_leave' ELSE 'active' END,
    CASE WHEN number % 10 = 0 THEN NULL ELSE ((number - 1) % 9) + 1 END
FROM numbers;

/* Add assignments for every person assigned to a squad. */
WITH RECURSIVE numbers(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM numbers WHERE number < 500
)
INSERT INTO assignment (person_id, squad_id, assigned_date, status)
SELECT
    printf('26-%08d', 72000000 + number),
    ((number - 1) % 9) + 1,
    date('2026-09-01', printf('+%d day', (number - 1) % 30)),
    'assigned'
FROM numbers
WHERE number % 10 <> 0;

/* Add varied training history for portal verification.
   random() creates different values per seed run; all rows retain a unique
   person's military number through the person_id foreign key. */
WITH RECURSIVE numbers(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM numbers WHERE number < 500
), training_candidates AS (
    SELECT
        number,
        (number - 1) % 9 AS service_year,
        CASE
            WHEN (number - 1) % 9 BETWEEN 1 AND 4 AND number % 10 = 0 THEN 8
            WHEN (number - 1) % 9 BETWEEN 1 AND 4 AND number % 2 = 0 THEN 28
            WHEN (number - 1) % 9 BETWEEN 1 AND 4
                AND ((number * 17 + number / 4 * 3) % 4) IN (1, 2) THEN 28
            WHEN (number - 1) % 9 BETWEEN 1 AND 4 THEN 32
            WHEN (number - 1) % 9 BETWEEN 5 AND 6 THEN 20
            ELSE 0
        END AS required_hours,
        CASE WHEN number % 7 = 0 THEN '무단불참' ELSE 'completed' END AS attendance_status
    FROM numbers
), training_values AS (
    SELECT
        number,
        service_year,
        required_hours,
        attendance_status,
        CASE
            WHEN attendance_status = '무단불참' THEN 0
            WHEN number % 5 = 0 THEN max(required_hours, 1)
            ELSE max(1, 1 + abs(random()) % required_hours)
        END AS training_hours
    FROM training_candidates
    WHERE service_year BETWEEN 1 AND 6
      AND (number % 3 <> 0 OR number % 7 = 0)
)
INSERT INTO education (
    person_id,
    education_year,
    training_year,
    training_round,
    attendance_status,
    training_hours,
    notes
)
SELECT
    printf('26-%08d', 72000000 + number),
    service_year,
    CASE
        WHEN training_hours < required_hours THEN min(service_year + 1, 8)
        ELSE service_year
    END,
    CASE
        WHEN attendance_status = '무단불참' THEN 1 + abs(random()) % 3
        ELSE 1
    END,
    attendance_status,
    training_hours,
    CASE
        WHEN attendance_status = '무단불참' THEN '무단불참 이월 훈련 기록'
        WHEN training_hours < required_hours THEN '부분 이수 후 잔여시간 이월 기록'
        ELSE '훈련시간 전부 이수 기록'
    END
FROM training_values;

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
