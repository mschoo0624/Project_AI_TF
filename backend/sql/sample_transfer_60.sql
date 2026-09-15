-- Add 60 idempotent, unassigned transfer-in records for assignment testing.
PRAGMA foreign_keys = ON;

WITH RECURSIVE sample(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM sample WHERE number < 60
), generated AS (
    SELECT
        number,
        abs(random()) % 4 AS branch_index,
        abs(random()) % 3 AS category_index,
        abs(random()) % 9 AS service_year,
        abs(random()) % 5 AS position_index,
        abs(random()) % 4 AS specialty_index
    FROM sample
), values_for_person AS (
    SELECT
        number,
        CASE branch_index
            WHEN 0 THEN '육군'
            WHEN 1 THEN '해군'
            WHEN 2 THEN '공군'
            ELSE '해병대'
        END AS branch,
        CASE category_index
            WHEN 0 THEN CASE number % 4 WHEN 0 THEN '이병' WHEN 1 THEN '일병' WHEN 2 THEN '상병' ELSE '병장' END
            WHEN 1 THEN CASE number % 4 WHEN 0 THEN '하사' WHEN 1 THEN '중사' WHEN 2 THEN '상사' ELSE '원사' END
            ELSE CASE number % 6 WHEN 0 THEN '소위' WHEN 1 THEN '중위' WHEN 2 THEN '대위' WHEN 3 THEN '소령' WHEN 4 THEN '중령' ELSE '대령' END
        END AS rank,
        CASE position_index
            WHEN 0 THEN '행정병'
            WHEN 1 THEN '통신병'
            WHEN 2 THEN '의무병'
            WHEN 3 THEN '운전병'
            ELSE '보급병'
        END AS position,
        CASE position_index
            WHEN 0 THEN CASE specialty_index WHEN 0 THEN '3111 101' WHEN 1 THEN '311 102' WHEN 2 THEN '999 999' ELSE NULL END
            WHEN 1 THEN CASE specialty_index WHEN 0 THEN '171 101' WHEN 1 THEN '171 104' WHEN 2 THEN '999 999' ELSE NULL END
            WHEN 2 THEN CASE specialty_index WHEN 0 THEN '411 101' WHEN 1 THEN '4112 101' WHEN 2 THEN '999 999' ELSE NULL END
            WHEN 3 THEN CASE specialty_index WHEN 0 THEN '241102' WHEN 1 THEN '241103' WHEN 2 THEN '999 999' ELSE NULL END
            ELSE CASE specialty_index WHEN 0 THEN '231101' WHEN 1 THEN '231103' WHEN 2 THEN '999 999' ELSE NULL END
        END AS specialty,
        service_year
    FROM generated
)
INSERT OR IGNORE INTO person (
    military_number,
    name,
    branch,
    rank,
    unit,
    specialty,
    origin_type,
    registration_type,
    service_year,
    position,
    mobilization_status,
    status,
    squad_id
)
SELECT
    printf('26-TEST-%03d', number),
    printf('전입테스트%03d', number),
    branch,
    rank,
    printf('%s-%02d부대', branch, (number % 5) + 1),
    specialty,
    CASE WHEN position = '의무병' AND number % 7 = 0 THEN '공중보건의출신' ELSE NULL END,
    '예비군 전입',
    service_year,
    position,
    CASE
        WHEN service_year BETWEEN 1 AND 4 AND number % 3 = 0 THEN '동원지정'
        WHEN service_year BETWEEN 1 AND 4 AND number % 3 = 1 THEN '동원미지정'
        WHEN service_year BETWEEN 1 AND 4 THEN '학생예비군'
        ELSE '해당없음'
    END,
    'active',
    NULL
FROM values_for_person;

WITH RECURSIVE sample(number) AS (
    SELECT 1
    UNION ALL
    SELECT number + 1 FROM sample WHERE number < 60
)
INSERT OR IGNORE INTO annual_status (person_id, service_year, mobilization_status)
SELECT
    printf('26-TEST-%03d', sample.number),
    years.service_year,
    CASE
        WHEN years.service_year BETWEEN 1 AND 4 AND sample.number % 3 = 0 THEN '동원지정'
        WHEN years.service_year BETWEEN 1 AND 4 AND sample.number % 3 = 1 THEN '동원미지정'
        WHEN years.service_year BETWEEN 1 AND 4 THEN '학생예비군'
        ELSE '해당없음'
    END
FROM sample
CROSS JOIN (
    SELECT 0 AS service_year UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
    SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL
    SELECT 7 UNION ALL SELECT 8
) AS years;
