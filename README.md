# Project_AI_TF

## Description:
- Creating the Live Dashboard for more clear visualization and easy formatting and editing the individuals' information. 

# 31사단 AI TF
## 프로젝트 소개
31사단 AI TF는 예비군 관련 개인 정보를 한곳에서 관리하고, 전투편성·연기·보류·교육·결재 업무를 효율화하기 위한 내부 업무 시스템입니다.

기존에 분산되어 있던 개인 정보를 통합하고, 실무자가 필요한 정보를 대시보드에서 빠르게 확인하고 수정할 수 있도록 하는 것을 목표로 합니다.

## MVP 목표: 실시간에 가까운 통합 관리 대시보드 구축

### 주요 기능
1. 예비군 정보 통합 관리
개인 정보 통합 조회
군번, 군별, 계급, 특기, 소속부대 등 관리
전입자 정보 등록 및 관리
개인 정보 수정/삭제
데이터 변경사항 즉시 반영
2. 전투편성
개인의 정보를 기반으로 적절한 분대에 편성합니다.

### 주요 판단 기준:
소속부대
군별
간부/병사 여부
특기
동원일시
집결일시
보류/연기 여부
편성 기준이 명확한 경우 AI보다 Backend Business Logic을 우선적으로 사용합니다.

### 3. 보류 / 연기 관리
예비군을 다음과 같이 관리합니다.

일반
보류
연기
결재 대기
고발 검토
고발
보류/연기 신청 → 실무자 검토 → 승인/거절의 workflow를 제공합니다.

### 4. Dashboard
한 화면에서 주요 현황을 확인할 수 있도록 합니다.

─────────────────────────────
│                 31사단 AI TF Dashboard                │
├───────────┬───────────┬────
│ 전체 인원 │ 가용 인원 │ 연기 인원 │ 보류 인원      │
│   000명   │   000명   │   000명   │   000명        │
├───────────┴───────────┴────
│                                                       │
│                  인원 통계 / 차트                     │
│                                                       │
├────────────────────────────
│ 분대별 편성 현황                                      │
│                                                       │
│  1분대  ███████████████  12명          │
│  2분대  █████████████    10명            │
│  3분대  ███████████████  12명          │
│                                                       │
├────────────────────────────
│ ⚠ 결재 필요 인원             [더보기]                │
│                                                       │
│  홍길동    보류서 작성    [확인] [수정]               │
│  김철수    연기 신청      [확인] [수정]               │
└────────────────────────────

전체 인원
가용 인원
분대별 인원
보류 인원
연기 인원
고발 관련 인원
통계 및 시각화
결재 대기 인원

### 5. 교육시간 관리
교육연도가 변경될 때 발생하는 교육시간 관리 문제를 해결합니다.

과거 교육 기록을 보존하면서 새로운 교육연도의 교육시간을 관리하는 것을 목표로 합니다.

### 6. 알림
보류서 등 업무 요청이 생성되면 실무자가 확인할 수 있도록 알림을 제공합니다.

## AI
AI는 MVP의 필수 요소가 아닙니다.

현재 핵심 기능은 다음과 같습니다.

Data Management
       +
Business Rules
       +
Approval Workflow
       +
Dashboard

향후 필요에 따라 AI를 추가할 수 있습니다.

예:

문서 정보 자동 추출
보류/연기 사유 분류 보조
규정 검색
이상 데이터 탐지
자연어 기반 데이터 조회

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
## MVP Priority
🔴 1. Database
🔴 2. FastAPI
🔴 3. SQL / PostgreSQL
🔴 4. CRUD API
🔴 5. 편성 Business Logic
🔴 6. 보류/연기 Workflow
🔴 7. Dashboard
🟠 8. Authentication / Authorization
🟠 9. Audit Log
🟠 10. Testing
🟡 11. Docker / Deployment
🟡 12. AI

# Goal
"분산된 예비군 관련 정보를 하나의 시스템에서 관리하고, 편성·보류·연기·교육·결재 업무를 빠르고 정확하게 처리할 수 있는 통합 업무 시스템 구축."