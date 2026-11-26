# Project_AI_TF

## 일일 업무일지

- 프로그램 시작 시 한국 시간(Asia/Seoul) 기준 오늘 일지를 생성합니다. 업무일지 화면에서 날짜별 처리 내역과 당시 대상자 인적사항을 확인하고 비고를 작성할 수 있습니다.
- **PDF 미리보기**는 업무 내역 오른쪽의 기본 창에 표시됩니다. 업무 내역과 입력 중인 비고가 바뀌면 자동 갱신하며, **확인**을 눌러야 비고와 PDF를 저장합니다. 저장본과 원본 양식도 같은 창에서 열람합니다.
- 인원·편성·편제·훈련·전입·보류/연기·고발장 업무의 성공한 변경을 자동 기록합니다. 단순 조회나 실패·변경 없는 요청은 기록하지 않으며, 적용 전 과거 작업은 소급 생성하지 않습니다. 전출·출국/귀국은 현재 처리 API가 없어 양식의 해당 칸을 비워 둡니다.
- **확인**을 누르면 원본 양식 한 장의 날짜·대상자·내용 칸을 채운 PDF를 저장합니다. 보류자/연기자 구역의 여덟 번째 칸에는 신청 구분에 따라 `보류` 또는 `연기`를 기입합니다(구분 정보가 없는 과거 기록은 `보류/연기`). 원본의 연락망 확인·서류 발송 등 실제 처리 여부를 알 수 없는 칸은 비워 둡니다. 같은 내용의 재확인은 중복 저장하지 않고, 추가 업무나 비고 변경 후 확인하면 새 버전을 보존합니다. 저장본은 날짜·버전별로 열람하고 다운로드할 수 있습니다.
- 원본 양식은 `frontend/public/pdfs/양식/일일 업무일지 양식.pdf` 하나입니다. PDF 생성에는 `backend/requirements.txt`의 PyMuPDF가 필요합니다: `backend`에서 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- 처리 내역과 확정 PDF는 별도 SQLite인 `backend/worklogs.sqlite3`에 저장합니다(`WORKLOG_DB_PATH`로 변경). 데스크톱 시연판은 `%APPDATA%/OnbitnuriDemo/archives/worklogs.sqlite3`를 사용하여 일반 시연 DB 초기화와 관계없이 기록을 유지합니다. 이 파일을 백업하면 PDF도 함께 보존됩니다.

코드는 `frontend/src/features/worklog`와 `backend/user/app/worklog`에 있습니다. API는 `/worklogs/today`, `/worklogs`, `/worklogs/{date}`, `/worklogs/{date}/preview`, `/worklogs/{date}/confirm`, `/worklogs/{date}/revisions/{revision}/pdf`, `/worklogs/template`입니다. 데스크톱 빌드 시 양식을 자동 포함하며 `WORKLOG_TEMPLATE_PATH`로 양식 경로를 지정할 수도 있습니다.

자동 기록은 업무 API의 성공 응답 후 별도 저장 트랜잭션으로 남깁니다. 업무 저장 직후 강제 종료 또는 기록 DB 장애가 발생하면 누락될 수 있으며, 기록 실패는 서버 로그에 표시됩니다. 서버 내부 정기 재계산·외부 DB 직접 수정은 사용자 업무 요청 기록에 포함하지 않습니다.

서류 처리에서는 제출·분석 취소/재요청·대상자 연결·재검증·승인/반려를 기록합니다. 비동기 AI 분석 완료 시점은 별도 업무 행으로 추가하지 않습니다. 검증은 `backend`에서 `.\.venv\Scripts\python.exe -m pytest tests/test_worklog.py tests/test_worklog_events.py tests/test_worklog_integration.py -q`, `frontend`에서 `npm run build`로 실행합니다.

## 고발대상자 관리·고발장 작성

자원관리 → 고발대상자에서 대상자 검색·훈련 이력 확인과 고발장 작성·저장·인쇄를 제공합니다. 훈련 미이수 검토 목록은 고발대상자 목록과 구분합니다.

- **자동 작성:** 대상자를 선택하면 확정된 무단불참 훈련을 기본 선택하고, 성명·군번·계급·편성부대 전체 경로·훈련기간·사실요약을 채웁니다. 훈련 선택 변경 시 연동 항목만 갱신하며 수동 입력은 유지합니다. 승인된 보류·연기, 미확정, 당일·미래 훈련은 자동 작성 후보에서 제외합니다.
- **수동 보완:** DB에 없는 주소·주민번호·연락처·훈련장소·통지서 전달 정보 등은 담당자가 입력합니다. 비어 있는 출력 항목은 빈칸으로 남습니다.
- **저장·열람:** `prosecution_document` 테이블에 작성 내용, 선택한 훈련의 저장 당시 정보, 작성자·저장 시각·버전을 보관합니다. 저장된 고발장은 검색·재열기·수정할 수 있으며 최신 훈련 정보로 덮어쓰지 않습니다. 최초 저장 시 근거 변경을 확인하고, 중복 요청과 동시 수정 충돌을 검사합니다.
- **인쇄:** 저장 후 인쇄 미리보기에서 프린터 또는 PDF 저장을 선택합니다. 별지 제6호서식의 항목을 따른 A4 HTML 양식이며, DB에는 PDF 파일 대신 작성 데이터를 저장합니다. 고발 접수·전송, 서명·관인 생성, 인원·훈련 데이터 수정은 수행하지 않습니다.

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
