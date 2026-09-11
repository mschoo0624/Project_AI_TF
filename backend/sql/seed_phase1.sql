USE project_ai_tf;

INSERT INTO squad (name, description) VALUES
    ('1분대', '제1분대'),
    ('2분대', '제2분대');
/*
군번, 이름, 계급, 부대, 특기, 상태, 소속분대.
*/
INSERT INTO person (military_number, name, rank, unit, specialty, status, squad_id) VALUES
    ('22-72007385', '홍길동', '병장', '31사단', '정비', 'active', 1),
    ('21-72007386', '김철수', '상병', '31사단', '통신', 'active', 2),
    ('18-72007387', '박영희', '일병', '31사단', '의무', 'on_leave', NULL);

INSERT INTO assignment (person_id, squad_id, assigned_date, status) VALUES
    ('22-72007385', 1, '2026-09-01', 'assigned'),
    ('21-72007386', 2, '2026-09-01', 'assigned');

INSERT INTO education (person_id, education_year, training_hours, notes) VALUES
    ('22-72007385', 2026, 40, '기본 교육 완료'),
    ('21-72007386', 2026, 32, '보충 교육 진행 중');

INSERT INTO postponement (person_id, type, reason, status) VALUES
    ('18-72007387', 'delay', '개인 사유', 'pending');

INSERT INTO app_user (username, password_hash, role) VALUES
    ('admin', 'placeholder_hash', 'admin');

INSERT INTO audit_log (user_id, action, table_name, record_id) VALUES
    (1, 'CREATE', 'person', 1),
    (1, 'CREATE', 'squad', 1);
