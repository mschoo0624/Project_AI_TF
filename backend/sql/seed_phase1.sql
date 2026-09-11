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
    CASE (number - 1) % 5
        WHEN 0 THEN '보병'
        WHEN 1 THEN '통신'
        WHEN 2 THEN '정비'
        WHEN 3 THEN '의무'
        ELSE '운전'
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

/* Add one education record for every person. */
WITH RECURSIVE numbers(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM numbers WHERE number < 500
)
INSERT INTO education (person_id, education_year, training_hours, notes)
SELECT
    printf('26-%08d', 72000000 + number),
    2026,
    (number * 8) % 41,
    printf('2026년 교육 기록 %03d', number)
FROM numbers;

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
    (1, 'SEED', 'education', 500),
    (1, 'SEED', 'postponement', 50),
    (1, 'SEED', 'app_user', 1);
