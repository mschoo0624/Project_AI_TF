## Installation Steps
1. sudo apt update
2. sudo apt install python3 python3-pip python3-venv -y
3. Check the Python version: `python3 --version`
4. Create and activate the virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

5. Install the backend dependencies:

```bash
python -m pip install -r requirements.txt
```

SQLite is included with Python. The `sqlite3` command-line tool is optional and
is only needed for manually running SQL files.

## Database
The backend uses SQLite. The database file is created at
`backend/project_ai_tf.db` when the application starts.

To initialize the schema manually from the `backend` directory:

```bash
sqlite3 project_ai_tf.db < sql/init_phase1.sql
sqlite3 project_ai_tf.db < sql/seed_phase1.sql
```

You can use a different database file by setting `DB_PATH`:

```bash
DB_PATH=/path/to/project_ai_tf.db uv run uvicorn user.app.main:app --reload --port 8001
```

## Run the server
1. Activate the virtual environment: `source venv/bin/activate`
2. Run `uv run uvicorn user.app.main:app --reload --port 8001`

The application creates missing tables automatically on startup.

## Development Roadmap
### Phase 1 — Database
 SQLite 설정
 Person 모델
 Squad 모델
 Assignment 모델
 Education 모델
 Postponement 모델
 User 모델
 AuditLog 모델
### Phase 2 — Basic API
 Person CRUD
 Squad CRUD
 Assignment API
 Dashboard API
### Phase 3 — Business Logic
 편성 규칙 구현
 가용 인원 계산
 보류/연기 상태 관리
 교육시간 관리
 데이터 검증
### Phase 4 — Approval System
 보류/연기 신청
 결재 대기 목록
 승인/거절
 알림
 Audit Log
### Phase 5 — Authentication
 Login
 User roles
 Permission system
 Backend authorization
### Phase 6 — Frontend Integration
 Dashboard
 인원 관리 화면
 분대 편성 화면
 결재 화면
 통계 화면
### Phase 7 — Testing & Deployment
 pytest
 API 테스트
 Business Logic 테스트
 Docker
 Linux server
 Logging
 Deployment