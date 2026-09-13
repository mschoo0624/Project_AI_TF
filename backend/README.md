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


 Updating to the new SQL database file.

 rm -f /tmp/project_ai_tf_test.db

DB_PATH=/tmp/project_ai_tf_test.db \
sqlite3 /tmp/project_ai_tf_test.db < sql/init_phase1.sql

DB_PATH=/tmp/project_ai_tf_test.db \
sqlite3 /tmp/project_ai_tf_test.db < sql/seed_phase1.sql


심 파일은 다음과 같습니다.

업무 로직: assignment.py
API: squads.py
DB 배정 모델: assignment.py
테스트 데이터: randomize_assignment_test.sql
자동 테스트: test_assignment.py

## The Checklists:
3. 교육시간 업무 규칙
다음은 중요한 업무 로직이므로 테스트를 추가하는 것이 좋습니다.

미래 복무연도 기록 입력 차단
이수 상태인데 훈련시간이 0인 경우 차단
불참 상태인데 훈련시간이 입력된 경우 차단
목표시간보다 많은 시간 입력 차단
이미 이수한 연차에 추가 입력하는 경우
교육 기록 수정 시에도 동일한 검증이 적용되는지 확인
현재 POST에는 검증이 있지만 PATCH는 상대적으로 검증이 부족해 보입니다. 교육 기록 수정 API는 다음 단계에서 반드시 보강할 영역입니다.

4. 전투편성
전투편성은 현재 자동 테스트가 가장 잘 마련된 부분입니다. 다음을 추가로 확인하세요.

정확히 quota만큼 인원이 배정되는 경우
후보자가 부족한 경우
이미 다른 분대에 배정된 인원이 재사용되지 않는 경우
같은 사람에게 중복 assignment가 생기지 않는 경우
군별 우선순위가 실제 결과에 반영되는 경우
allow_branch_merge=false일 때 군 통합이 발생하지 않는 경우
존재하지 않는 분대에 편성 요청하는 경우
quota가 음수이거나 비정상적인 값인 경우
같은 요청을 두 번 실행했을 때 중복 배정이 생기지 않는 경우
현재 테스트는 test_assignment.py에서 서비스 함수 중심으로만 검증합니다. 다음에는 FastAPI HTTP API를 호출하는 통합 테스트를 추가하는 것이 좋습니다.