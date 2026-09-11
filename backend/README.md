## installiation Steps:
1. sudo apt update
2. sudo apt install python3 python3-pip python3-venv -y
3. And check for the python version.

## To run the server
1. ACtivate the Soruce file (source venv/bin/activate)
2. and run the command "uv run fastapi dev --port 8001"
which is going to open the backend server. 

## Development Roadmap
### Phase 1 — Database
 PostgreSQL 설정
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