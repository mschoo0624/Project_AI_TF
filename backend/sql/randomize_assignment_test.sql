PRAGMA foreign_keys = ON;

DELETE FROM assignment WHERE person_id IN (
    SELECT military_number FROM person WHERE service_year IN (5, 6) AND status = 'active'
);

UPDATE person
SET squad_id = NULL
WHERE service_year IN (5, 6) AND status = 'active';

DROP TABLE IF EXISTS assignment_test_pool;
CREATE TABLE assignment_test_pool (
    person_id VARCHAR(50) PRIMARY KEY,
    position VARCHAR(50) NOT NULL,
    specialty VARCHAR(100) NOT NULL,
    sequence_number INTEGER NOT NULL
);

WITH candidates AS (
    SELECT
        military_number,
        row_number() OVER (ORDER BY random()) AS sequence_number
    FROM person
    WHERE service_year IN (5, 6)
      AND status = 'active'
      AND squad_id IS NULL
    LIMIT 10
)
INSERT INTO assignment_test_pool (person_id, position, specialty, sequence_number)
SELECT
    military_number,
    CASE (sequence_number - 1) % 5
        WHEN 0 THEN '행정병'
        WHEN 1 THEN '통신병'
        WHEN 2 THEN '의무병'
        WHEN 3 THEN '운전병'
        ELSE '보급병'
    END,
    CASE (sequence_number - 1) % 5
        WHEN 0 THEN CASE WHEN sequence_number % 2 = 0 THEN '311 102' ELSE '3111 101' END
        WHEN 1 THEN CASE WHEN sequence_number % 2 = 0 THEN '171 104' ELSE '171 101' END
        WHEN 2 THEN CASE WHEN sequence_number % 2 = 0 THEN '4112 101' ELSE '411 101' END
        WHEN 3 THEN CASE WHEN sequence_number % 2 = 0 THEN '241103' ELSE '241102' END
        ELSE CASE WHEN sequence_number % 2 = 0 THEN '231103' ELSE '231101' END
    END,
    sequence_number
FROM candidates;

UPDATE person
SET
    position = (SELECT position FROM assignment_test_pool WHERE person_id = person.military_number),
    specialty = (SELECT specialty FROM assignment_test_pool WHERE person_id = person.military_number),
    rank = CASE ((SELECT sequence_number FROM assignment_test_pool WHERE person_id = person.military_number) - 1) % 3
        WHEN 0 THEN '병장'
        WHEN 1 THEN '하사'
        ELSE '소위'
    END
WHERE military_number IN (SELECT person_id FROM assignment_test_pool);
