## Security Notice
Authentication and role enforcement are temporarily disabled across API workflows. Personnel and training data, exports, and write operations are accessible without a token. Do not expose this service to untrusted networks.

## Windows 시연용 데스크톱 빌드

소스와 빌드 도구는 Git으로 관리하고, `dist-desktop/`의 실행 파일·ZIP·DB는 Git에서 제외합니다. 다른 Windows 개발 PC에서도 아래 순서로 빌드할 수 있습니다. Node.js/npm, Python 가상환경 및 이 문서의 Ollama 설치를 먼저 준비하세요.

저장소 루트에서:

```powershell
cd frontend
npm ci
cd ../desktop
npm ci
npm run build
```

결과는 `dist-desktop/<빌드시간>/Onbitnuri-win32-x64/Onbitnuri.exe`와 같은 위치의 `Onbitnuri-demo.zip`입니다. 폴더 전체가 실행 단위이며, ZIP은 별도 보관·공유용입니다. Python은 `backend/.venv/Scripts/python.exe`, Ollama는 설치 경로를 빌드 시 기록합니다. 다른 PC에서 빌드하려면 그 PC에도 의존성 설치가 필요합니다. 완성된 빌드 폴더를 다른 PC로 옮기는 경우 `resources/runtime.json`에서 설치 경로를 맞추세요.

빌드 전에 `backend/project_ai_tf.db`와 `backend/classifier_agent/data/`의 DB·제출 원본 PDF를 준비하세요. Git에서 제외된 데이터는 다른 작업자에게 별도로 전달해야 합니다. 빌드 당시 현재 기록 전체가 읽기 전용 SQLite 백업으로 복사되며, 원본은 수정하지 않습니다. 실행할 때마다 `%APPDATA%/OnbitnuriDemo/data`를 이 복사본으로 초기화합니다. 시연에서 변경한 기록은 다음 실행 시 사라집니다. 브라우저 저장소도 실행마다 새로 시작합니다.

법령 가공 데이터는 빌드 후 아래에 수동 복사할 수 있습니다. 앱을 재실행하면 반영되며 재빌드할 필요는 없습니다.

```text
resources/backend/RAG/data/processed/laws.jsonl
resources/backend/RAG/data/index/embeddings.npy
resources/backend/RAG/data/index/index_info.json
```

세 파일은 같은 원본과 임베딩 모델(기본 `BAAI/bge-m3`)로 생성한 세트여야 합니다. 빠진 경우 다른 기능은 실행되지만 법령 검색은 사용할 수 없습니다. 챗봇 기본 모델은 `qwen2.5:7b`, 문서 분석은 `qwen3:4b-instruct`이며 `resources/runtime.json`에서 지정합니다.

앱은 사용 가능한 로컬 포트에 전용 백엔드와 Ollama를 실행하고, 닫을 때 해당 프로세스 트리만 종료합니다. 기존 개발 서버나 기존 Ollama를 종료하지 않습니다. 사용 중인 개발 PC의 모델 저장소를 공유하며 모델 파일 자체는 배포본에 복사하지 않습니다.

이미지는 Vite가 실제 번들에서 참조하는 자산을 포함합니다. `public/`은 통째로 복사하지 않고 빌드된 HTML·JS·CSS 등에 경로가 있는 파일만 복사합니다. 동적으로 조합하는 경로는 `desktop/public-assets.json`의 `include`에 상대 경로를 명시하세요. 포함·제외 목록과 누락된 법령 자료는 `resources/build-manifest.json`에 기록됩니다. 제출 기록에 연결된 PDF와 분류 규칙에서 참조하는 법규 PDF는 별도로 포함합니다.

개발 PC별 경로·모델 설정을 유지하려면 Git에서 제외되는 `desktop/runtime.local.json`에 `python`, `ollama`, `classifierModel`, `chatModel`을 지정할 수 있습니다. 오류 로그는 `%APPDATA%/OnbitnuriDemo/desktop.log`에 남습니다.

## Model packages

- `prediction_agent/`: dashboard population and attendance prediction, including datasets and caches.
- `classifier_agent/`: Qwen PDF extraction, rule verification and persisted document review API, served under `/classifier-api`.
- `RAG/`: legal chatbot API, served under `/rag-api`.

The business API, classifier API, and RAG API run together in the main FastAPI process on port 8002. The dashboard API uses `prediction_agent.cache`.
See [prediction setup](prediction_agent/README.md) and [classifier setup](classifier_agent/README.md).

## 통합 개발 환경 실행 (Windows PowerShell)

**문서 AI 분석에는 8002 백엔드와 별도로 Ollama 서버가 실행 중이어야 합니다.** Ollama는 Python 패키지가 아닌 외부 실행 프로그램이므로 `pip install -r requirements.txt`만으로 설치되지 않습니다. 각 작업자의 PC에서 아래 준비를 진행하세요.

### 최초 설치 및 브랜치 변경 후 의존성 갱신

1. [Ollama 설치 페이지](https://ollama.com/download)에서 운영체제에 맞는 프로그램을 설치하고 새 터미널을 엽니다.
2. 저장소 루트에서 다음 명령을 실행합니다. 기존 `.venv`가 있다면 생성 명령은 생략합니다. 브랜치 병합 후에는 의존성 설치 명령을 다시 실행합니다. 이 목록에는 classifier와 RAG 패키지도 포함됩니다.

```powershell
cd .\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

### 실행 순서

1. Ollama 실행 상태를 확인합니다.

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

연결되지 않으면 Ollama 앱을 실행하거나 **별도 터미널**에서 아래 명령을 실행한 채 유지합니다. 이미 실행 중이면 중복 실행하지 않습니다.

```powershell
ollama serve
```

2. 다른 터미널에서 문서 분석 모델을 다운로드합니다(최초 1회). `ollama list`에 해당 모델이 있으면 다운로드는 생략할 수 있습니다. 모델 파일은 Git에 포함되지 않으므로 각 PC에 설치해야 합니다.

```powershell
ollama pull qwen3:4b-instruct
ollama list
```

3. `backend` 폴더에서 통합 백엔드를 실행합니다. 문서 분석 작업 큐를 위해 단일 worker로 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn user.app.main:app --host 127.0.0.1 --port 8002
```

4. 별도 터미널의 `frontend` 폴더에서 화면을 실행합니다.

```powershell
npm install
npm run dev
```

| 구성 | 기본 주소 / 설정 |
| --- | --- |
| 통합 백엔드 | `http://127.0.0.1:8002` (문서 API: `/classifier-api`, 법령 챗봇: `/rag-api`) |
| Ollama | `http://127.0.0.1:11434` — 백엔드와 별도 프로세스 |
| 문서 분석 모델 | `qwen3:4b-instruct` |
| 프론트엔드 | `npm run dev`가 출력하는 주소 |

문서 분석의 `OLLAMA_URL` 기본값은 `http://127.0.0.1:11434`, `CLASSIFIER_MODEL` 기본값은 `qwen3:4b-instruct`입니다. 변경할 때는 백엔드를 시작하는 터미널에 환경 변수를 설정합니다(classifier는 `.env`를 자동으로 읽지 않습니다). 별도 classifier 서버(8001/8003)는 실행하지 않습니다.

법령 챗봇의 생성 모델은 문서 분석 모델과 별도 설정입니다. `RAG/.env`의 `OPENAI_MODEL`에 지정한 모델도 설치하세요(예: `ollama pull qwen2.5:7b`). 두 기능은 같은 Ollama 서버를 사용할 수 있습니다. 자세한 설정은 [RAG 안내](RAG/README.md)를 참고하세요.

Ollama가 꺼져 있거나 지정 모델이 없으면 8002 서버가 실행되어도 문서 AI 분석은 실패합니다. 연결 오류는 위 `/api/tags` 요청으로, 모델 누락은 `ollama list`로 확인하세요.

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

## Run Backend (Windows PowerShell)

VS Code의 PowerShell 터미널에서 프로젝트 최상위 `AITF` 폴더를 기준으로 실행합니다.

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m uvicorn user.app.main:app --host 127.0.0.1 --port 8002
```

이미 `backend` 폴더에 있다면 `cd .\backend`는 생략합니다. `backend\.venv`에 의존성이 설치되어 있어야 하며, 가상환경을 별도로 활성화할 필요는 없습니다.
이 서버 하나가 업무 API, 문서 API(`/classifier-api`), 법령 챗봇 API(`/rag-api`)를 모두 제공합니다. 프런트엔드 기능을 위해 별도의 classifier 또는 RAG Uvicorn 서버를 시작하지 않습니다.

가상환경이나 라이브러리가 아직 준비되지 않았다면 `backend` 폴더에서 한 번만 다음을 실행합니다.

```powershell
uv venv --python 3.14
uv pip install --python .\.venv\Scripts\python.exe -r .\requirements.txt
```

서버가 실행된 동안 <http://127.0.0.1:8002/docs>에서 API 문서를 확인할 수 있습니다. 종료하려면 서버 터미널에서 `Ctrl + C`를 누릅니다.

## Training Recalculation

Annual training results are rebuilt from source records by the service layer. The rebuild keeps obligation year separate from calendar training year, stores per-type carryover and round state separately, and writes an audit diff. It does not infer an absence from an overdue session. An absence requires a confirmer; write routes derive the actor only from a verified bearer session. Overdue sessions remain unconfirmed and appear in the training-review list.

The SQLite initializer applies additive migrations and creates the status-policy table. It does not delete or reseed the active database. Admin endpoints are `POST /reservists/training/recalculate/{military_number}`, `POST /reservists/training/recalculate-all`, `GET /reservists/training/status-policies`, and `PATCH /reservists/training/status-policies/{status_key}`. The Jan 1 rollover runs through the existing scheduled background loop and has a database year marker.

### Training Schedule and Results

The education-training workflow has separate schedule, roster assignment, and result-confirmation steps. A multi-day event has one education record per reservist; session dates are schedule details, not separate attendance results. Scheduled events can be moved or cancelled until any roster result is confirmed; moves update linked roster dates and are audited. Assignments do not create results, and overdue sessions are review work items rather than automatic absences. Result batches are atomic and idempotent, and stale edits require reloading before confirmation. Approved postponements can reverse a confirmed absence and advance the round state; the next round still requires an explicit roster assignment.

Training writes require an authenticated account. Roles are `viewer` (read), `scheduler` (schedules, rosters, and ordinary results), and `approver` (approval-sensitive results and account creation). No default training username or password is created. For the first account, call `POST /auth/bootstrap` from localhost with a username/password you choose. Bootstrap is available only until the first supported-role account exists; legacy accounts with unsupported roles do not block it. The existing `admin` account with role `admin` is not accepted by training auth, and its password cannot be recovered from its stored hash. The approver can create subsequent accounts through `POST /auth/users`; users sign in at `POST /auth/login` and send the returned bearer token as `Authorization: Bearer <token>`. Passwords must be at least 12 characters.

On the login page, choose **첫 approver 계정 만들기**, then enter the username and password for the first account. The backend only accepts this one-time setup request from a loopback address (`127.0.0.1` or `::1`); the route does not use a bootstrap token. Later accounts are created by a signed-in approver using the header's **계정 생성** action or `POST /auth/users`.

교육훈련 계정·업무 API는 위의 통합 백엔드(8002)를 사용합니다.

| Setting | Default | Behavior |
| --- | --- | --- |
| `TRAINING_RESULT_GRACE_DAYS` | `7` | Keeps completed sessions on the result worklist for this many days. |
| `EARLY_DISMISSAL_COUNTS_HOURS` | `true` | When true, `조기퇴소` requires positive hours and contributes them to recalculation; when false it requires zero hours. Confirm the applicable directive before operational use. |

Spreadsheet import is intentionally not implemented until an anonymized unit export sample and its column semantics are available. There is no automatic-absence setting: staff confirmation is required to record an absence.

Roster assignment currently records a pending notification state, but there is no delivery channel or reservist contact/account mapping configured. No notification is sent; define the approved delivery channel and recipient source before enabling delivery. The configured early-dismissal rule, Type I conversion, deferral-counter scope, and prosecution thresholds must be verified against current authoritative policy before operational use.

| Setting | Default | Status |
| --- | --- | --- |
| `TRAINING_OBLIGATION_YEAR_END_MONTH` / `TRAINING_OBLIGATION_YEAR_END_DAY` | `12` / `31` | Configurable; Dec 31 is the specified default. |
| `TRAINING_OVERDUE_GRACE_DAYS` | `0` | Configurable; verify the operational grace period. |
| `TRAINING_ROLLOVER_ENABLED` | `true` | Configurable. The job runs on Jan 1 (Korea-local calendar date). |
| `TRAINING_TYPE1_DEFERRAL_CONVERTS_TO_TYPE2` | `true` | **UNVERIFIED** legal/business rule; set `false` to retain Type I. |
| `TRAINING_LEGACY_SERVICE_YEAR_FALLBACK` | `true` | **UNVERIFIED** compatibility rule for people without a discharge/s소집해제 date. Set `false` to emit `NEEDS_REVIEW`. |
| `TRAINING_OVERSEAS_HOLD_MIN_DAYS` | `365` | Configurable minimum; shorter approved cases are treated as deferrals. |
| `TRAINING_ILLNESS_HOLD_MIN_DAYS` | `180` | Configurable minimum; shorter approved cases are treated as deferrals. |
| `TRAINING_HOLD_RESOLUTION_GRACE_DAYS` | `14` | Configurable reporting window after the hold end date. |
| `TRAINING_MOBILIZATION_DEFERRAL_LIMIT` | `2` | Configurable warning threshold; never blocks saving. |
| `TRAINING_GENERAL_DEFERRAL_LIMIT` | `6` | Configurable warning threshold; never blocks saving. |
| `TRAINING_DEFERRAL_COUNTER_SCOPE` | `reserve_period` | **UNVERIFIED** scope; `calendar_year` is also supported. |
| `TRAINING_MOBILIZATION_DEFERRAL_REASONS` | work, exam, planned overseas travel, vocational school, major event tokens | Configurable comma-separated reason/category match tokens. |

Status behavior is configurable in `training_status_policy`; defaults are inserted with `INSERT OR IGNORE`, so administrator-edited rows are preserved. Unknown statuses and missing student semester data produce `NEEDS_REVIEW`. Semester completion is not currently sourced from school records; staff can enter verified annual status with `PATCH /persons/{military_number}/annual-status/{service_year}` (`mobilization_status` and `semester_completed`). The Type I conversion default and deferral-counter scope remain unverified and must be confirmed against applicable policy before production use.

## Run Law Chatbot (RAG, Windows PowerShell)

화면 오른쪽 위 **법령 챗봇**은 통합 백엔드의 `/rag-api` 경로에서 제공됩니다. 앞의 **Run Backend** 명령만 실행하면 되며 별도 포트나 RAG 서버는 필요하지 않습니다. 시작 후 임베딩 모델(bge-m3)을 불러오는 데 1~2분이 걸릴 수 있습니다.
- 답변 생성에는 Ollama가 실행 중이어야 합니다. 모델은 `backend\RAG\.env`의 `OPENAI_MODEL`에서 정합니다 (예: `ollama pull qwen2.5:7b`). Ollama가 없으면 관련 조문 검색만 동작합니다.
- 가상환경 준비, 법령 추가, 인덱스 재생성은 [`RAG/README.md`](RAG/README.md)를 참고하세요.
- 상태 확인: <http://127.0.0.1:8002/rag-api/api/status>.
