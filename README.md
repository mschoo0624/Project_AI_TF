# Project_AI_TF

## 고발대상자 관리·고발장 작성

자원관리 → 고발대상자에서 대상자 검색·훈련 이력 확인과 고발장 작성·저장·인쇄를 제공합니다. 훈련 미이수 검토 목록은 고발대상자 목록과 구분합니다.

- **자동 작성:** 대상자를 선택하면 확정된 무단불참 훈련을 기본 선택하고, 성명·군번·계급·편성부대 전체 경로·훈련기간·사실요약을 채웁니다. 훈련 선택 변경 시 연동 항목만 갱신하며 수동 입력은 유지합니다. 승인된 보류·연기, 미확정, 당일·미래 훈련은 자동 작성 후보에서 제외합니다.
- **수동 보완:** DB에 없는 주소·주민번호·연락처·훈련장소·통지서 전달 정보 등은 담당자가 입력합니다. 비어 있는 출력 항목은 빈칸으로 남습니다.
- **저장·열람:** `prosecution_document` 테이블에 작성 내용, 선택한 훈련의 저장 당시 정보, 작성자·저장 시각·버전을 보관합니다. 저장된 고발장은 검색·재열기·수정할 수 있으며 최신 훈련 정보로 덮어쓰지 않습니다. 최초 저장 시 근거 변경을 확인하고, 중복 요청과 동시 수정 충돌을 검사합니다.
- **인쇄:** 저장 후 인쇄 미리보기에서 프린터 또는 PDF 저장을 선택합니다. 별지 제6호서식의 항목을 따른 A4 HTML 양식이며, DB에는 PDF 파일 대신 작성 데이터를 저장합니다. 고발 접수·전송, 서명·관인 생성, 인원·훈련 데이터 수정은 수행하지 않습니다.

기본 DB는 `backend/project_ai_tf.db`이며 `DB_PATH`/`DATABASE_URL` 설정을 따릅니다. 미저장 내용은 새로고침하면 사라집니다. 데스크톱 시연판은 매 실행 시 빌드 당시 DB로 복원하므로 이전 실행에서 저장한 고발장도 초기화됩니다.

### 코드 구조

| 위치 | 역할 |
| --- | --- |
| `frontend/src/features/prosecution/ProsecutionPage.tsx`, `ProsecutionRoster.tsx`, `ProsecutionProfile.tsx` | 탭·목록·훈련 이력 |
| 같은 폴더의 `ProsecutionDraft.tsx`, `useProsecutionDraft.ts`, `draft.ts` | 작성 화면·상태/저장 흐름·양식 및 자동 입력 규칙 |
| 같은 폴더의 `DraftDocument.tsx`, `ProsecutionPrintDialog.tsx`, `ProsecutionSavedDocuments.tsx` | 출력 양식·인쇄·저장 목록 |
| 같은 폴더의 `api.ts`, `types.ts`, `useProsecutionQuery.ts`, `prosecution.css` | API 요청·자료형·조회 상태·기능 전용 스타일 |
| `backend/user/app/api/prosecution_documents.py`, `schemas/prosecution_document.py` | HTTP 라우팅·권한·요청 검증 |
| `backend/user/app/services/prosecution_documents.py`, `services/prosecution_draft.py` | 저장·조회·버전 검사 및 인원/훈련 근거 조회 |
| `backend/user/app/models/prosecution_document.py` | 저장 테이블 |

기존 API 주소를 유지합니다: 목록 `GET /reservists/prosecution-targets`, 미이수 검토 `GET /reservists/training-review-targets`, 작성 근거 `GET /reservists/{military_number}/prosecution-draft`, 문서 목록/생성 `GET/POST /prosecution-documents`, 상세/수정 `GET/PUT /prosecution-documents/{id}`.

검증 명령:

- `backend`에서 `.\.venv\Scripts\python.exe -m pytest tests/test_prosecution_draft.py tests/test_prosecution_documents.py -q` (임시 DB 사용)
- `frontend`에서 `npm run build`

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
