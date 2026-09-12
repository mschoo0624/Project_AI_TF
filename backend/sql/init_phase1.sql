PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS squad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS person (
    military_number VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    branch VARCHAR(50) NOT NULL DEFAULT '육군',
    rank VARCHAR(50),
    unit VARCHAR(100),
    specialty VARCHAR(100),
    origin_type VARCHAR(50),
    service_year INT,
    position VARCHAR(50),
    mobilization_status VARCHAR(20),
    status VARCHAR(50) DEFAULT 'active',
    squad_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (squad_id) REFERENCES squad(id)
);

CREATE TABLE IF NOT EXISTS annual_status (
    person_id VARCHAR(50) NOT NULL,
    service_year INT NOT NULL,
    mobilization_status VARCHAR(20) NOT NULL,
    PRIMARY KEY (person_id, service_year),
    FOREIGN KEY (person_id) REFERENCES person(military_number)
);

CREATE TABLE IF NOT EXISTS assignment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id VARCHAR(50) NOT NULL,
    squad_id INT NOT NULL,
    assigned_date DATE NOT NULL,
    status VARCHAR(50) DEFAULT 'assigned',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (person_id) REFERENCES person(military_number),
    FOREIGN KEY (squad_id) REFERENCES squad(id)
);

CREATE TABLE IF NOT EXISTS education (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id VARCHAR(50) NOT NULL,
    education_year INT NOT NULL,
    training_year INT,
    training_type VARCHAR(50) NOT NULL DEFAULT '기본훈련',
    training_round INT NOT NULL DEFAULT 1,
    attendance_status VARCHAR(20) NOT NULL DEFAULT 'completed',
    training_hours INT NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (person_id) REFERENCES person(military_number)
);

CREATE TABLE IF NOT EXISTS postponement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id VARCHAR(50) NOT NULL,
    type VARCHAR(50) NOT NULL,
    reason TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP NULL,
    FOREIGN KEY (person_id) REFERENCES person(military_number)
);

CREATE TABLE IF NOT EXISTS app_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) DEFAULT 'staff',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INT,
    action VARCHAR(200) NOT NULL,
    table_name VARCHAR(100),
    record_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES app_user(id)
);
