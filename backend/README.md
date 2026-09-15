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

## Add Assignment Test Data
기존 데이터를 지우지 않고 전입·전투편성 테스트 인원 60명을 추가하려면 backend 디렉터리에서 실행합니다.

```bash
sqlite3 project_ai_tf.db < sql/sample_transfer_60.sql
```

샘플 군번은 `26-TEST-001`부터 `26-TEST-060`까지이며, 모두 미배정 상태로 생성됩니다. SQL은 `INSERT OR IGNORE`를 사용하므로 여러 번 실행해도 중복되지 않습니다.

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

## The Checklists:
1. 전투편성
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

1. 📊 메인 대시보드 (Dashboard) 탭 구현 (추천 1순위)
백엔드에 구현되어 있는 GET /dashboard API를 프론트엔드와 연동합니다.
대시보드 화면에 전체 인원, 가용 인원, 연기/보류 인원 요약 카운터 및 고발 위험 예비군 알림 카드를 구성합니다.
- in the dashboard, I want to show the graph, data results, resluts and current situations, as a 자원 현항, 훈련 관리등등. 
2. 📝 보류 및 연기 (Postponements) 신청/결재 관리 UI
백엔드 /postponements API와 연동하여 예비군의 연기/보류 신청 등록 및 담당자 승인/반려(Workflow) 화면을 구현합니다.

### Core API Examples
예비군
GET    /persons
GET    /persons/{id}
POST   /persons
PATCH  /persons/{id}
DELETE /persons/{id}

편성
GET  /assignments
POST /assignments
PATCH /assignments/{id}

보류 / 연기
GET   /postponements
POST  /postponements
PATCH /postponements/{id}/approve
PATCH /postponements/{id}/reject

Dashboard
GET /dashboard/summary
GET /dashboard/statistics

Data Model
주요 데이터는 다음과 같이 구성합니다.

User
 │
 ├── Permission / Role
 │
 └── AuditLog

Person
 │
 ├── Assignment
 ├── Education
 └── Postponement

Squad
 │
 └── Assignment

Postponement
 │
 ├── Approval
 └── Notification