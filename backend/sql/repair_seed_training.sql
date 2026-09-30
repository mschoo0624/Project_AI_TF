/* Repair only the original development-seed training rows.
   Rows with other notes, including transferred-history records, are preserved. */
PRAGMA foreign_keys = ON;

DELETE FROM education
WHERE person_id LIKE '26-7200%'
  AND notes IN (
      '무단불참 이월 훈련 기록',
      '부분 이수 후 잔여시간 이월 기록',
      '훈련시간 전부 이수 기록'
  );

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
    WHERE person.military_number LIKE '26-7200%'
      AND annual_status.service_year BETWEEN 1 AND person.service_year
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
    SELECT military_number, current_service_year, service_year,
           '작계훈련(전·후반기)', 12
    FROM training_candidates
    WHERE plan_kind = 'basic_and_operations'
)
INSERT INTO education (
    person_id, education_year, training_year, training_type,
    training_round, attendance_status, training_hours, notes
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