# Qwen 신청 문서 정보 추출

전자 PDF를 pdfplumber로 읽고, 신청 유형별 명세에 지정된 항목을 로컬
`qwen3:4b-instruct`로 추출한다. 모델 학습·외부 추론 서비스는 사용하지 않는다.
기준 목록은 [specifications/README.md](specifications/README.md)를 참고한다.

## 설치 및 실행

Python 3.10 이상, Ollama가 필요하다. 프로젝트 루트에서:

```powershell
python -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\classifier_agent\requirements.txt
ollama pull qwen3:4b-instruct
# Ollama 앱/서버가 실행 중이어야 한다. 미실행 환경은 별도 터미널에서 ollama serve.
.\backend\.venv\Scripts\python.exe -m uvicorn backend.classifier_agent.API:app --host 127.0.0.1 --port 8003
```

위 명령은 프로젝트 루트에서 실행한다. `backend` 폴더 안에서 실행하려면 앱 경로를
`classifier_agent.API:app`으로 바꾸고 실행 파일을 `.\.venv\Scripts\python.exe`로 지정한다.

기존 가상환경이 있으면 생성은 생략한다. Linux/macOS는 `Scripts/python.exe` 대신
`bin/python`을 사용한다. 모델은 Ollama 저장소에 설치되며 Git에 포함하지 않는다.
환경 변수 `OLLAMA_URL` 기본값은 `http://127.0.0.1:11434`,
`CLASSIFIER_MODEL` 기본값은 `qwen3:4b-instruct`다. Qwen 계열만 지원한다.
환경 변수를 사용하려면 서버를 시작하는 프로세스에 설정한다(.env 자동 로딩 없음).

## API

- `GET /application-types`: 신청 유형 ID·라벨·명세 목록.
- `POST /extract-pdf`: multipart `file`(전자 PDF, 최대 20MB), `application_type`(목록의 ID),
  선택값 `applicant_name`(여러 인물 중 신청자 지정).
- 대화형 API 문서: `http://127.0.0.1:8003/docs`.
- 잘못된 유형/PDF는 422, 용량 초과는 413, 처리 중 요청은 429, 모델 실패는 503.
- 한 프로세스에서 한 문서씩 처리한다. 각 요청의 임시 PDF는 종료 시 제거한다.
  기본 localhost 실행용이며 외부 공개 서비스의 인증은 포함하지 않는다.

CLI도 같은 구현을 사용한다:

```powershell
.\backend\.venv\Scripts\python.exe -m backend.classifier_agent.extraction .\frontend\public\pdfs\old\medical.pdf --application-type postponement.illness -o extraction-result.json
```

출력 파일은 덮어쓰지 않는다. 종료 코드 0은 추출 완료, 2는 확인 필요, 1은 실행 오류다.
단순 PDF 텍스트·표·좌표만 필요한 경우 기존 `pdf_extract` 모듈을 계속 사용할 수 있다.

## 반환 계약과 검증

`fields`의 각 항목에 `value`, `status`, `evidence`, `candidates`, `errors`를 반환한다.
미기재는 `missing`과 null이며 false로 바꾸지 않는다. 명시적 부정은 `explicit_negative`다.
여러 페이지의 서로 다른 값은 `conflicting`으로 표시하고 모든 후보를 남긴다.
부분 날짜 등 근거만 있는 항목은 `unresolved`로 보존한다.
자료형/원문 인용/날짜 정밀도 검사 실패는 `invalid`이며 확정값을 null로 차단한다.

근거는 PDF SHA-256 식별자·페이지·원문 인용을 포함한다. 모델은 제공된 셀/문장의
`source_id`를 선택하고 서버가 원문과 bbox/table/row/column을 연결한다. 표에 속하지
않은 문장은 표 좌표가 null이다. `pdf.pages[].sources`에 셀·문장별 원문과 좌표를 보존한다.
바깥쪽 세로선이 없는 서식은 실제 가로선·칸막이로 셀을 복원한다. 회전된 글자는
`rotated_text`로 별도 보존해 SAMPLE 등의 문구가 성명·번호에 섞이지 않도록 한다.
원래 페이지 텍스트·단어·표도 그대로 보존한다.
`model_responses`에는 검토용 원문 응답이 있다. 개인정보가 포함될 수 있으므로
응답은 자동 파일 저장/로그 출력하지 않는다.

검증 규칙의 공통 조건과 해당 유형 조건이 참조하는 문서 항목만 사용한다. `context.*`는
DB·담당자 입력으로 처리하고 AI 추출에서 제외한다. 분기는 아직 별도 필터링하지 않으며
미기재 항목 전체를 승인 필수 요건으로 취급하지 않는다. 페이지별 최대 6000자,
한 페이지의 항목을 묶어서 요청하고 이전 대화를 전달하지 않는다. 코드로 확인된 제목은
모델 요청에서 제외한다. 기본 항목 설명의 중복과 JSON 공백을 줄인다. 모델에 보내는 sources는
id·text·label만 포함한다. kind·box·size는 보내지 않으며 원본 추출 결과의 좌표 정보는 보존한다.
셀/문장을 통째로 묶어 UTF-8 9600바이트 이내 입력으로 나누며 재시도 포함 한도는 10000바이트다.
이는 토큰 수의 직접 측정이 아닌 보수적인 크기 제한이다. 문맥은 16384토큰, 출력은 항목 수에 따라
1024~4096토큰으로 설정해 입력·출력 공간을 확보한다. 실제 입력/출력 토큰 수와 로딩·총 시간은
Ollama 응답을 받아 INFO 로그에 기록한다. 모델은 5분간 메모리에 유지하고 대화 이력은 공유하지 않는다.
단일 셀/문장이 한도를 넘거나 페이지가 6000자를 넘으면 자르지 않고 오류로 반환한다.
JSON 스키마로 출력을 제한하고, 형식·근거 검증이 실패한 항목만 한 번 재시도한다.
재시도 후에도 실패하면 해당 항목은 invalid로 남긴다. 미기재 항목은 재시도하지 않는다.
긴 문서/항목이 많은 유형은 여러 번 추론하므로 오래 걸릴 수 있다.
띄어진 숫자와 줄바꿈은 원문을 보존한 채 검증 시 정규화한다. 완전한 연월일만
날짜로 인정하며, 진단일을 치료 시작일로 간주하거나 치료기간으로 종료일을 계산하지 않는다.
시험 접수일은 접수/등록일/신청일 근거를 추가 검사한다.
발행기관이 함께 적힌 하단의 독립된 완전한 날짜도 발급일 근거로 읽는다.
등록번호를 발급기관으로 선택하거나 진단일을 치료 시작일로 선택하는 등 명백한
항목 역할 오류는 차단한다. 이름·기관명·병명 등은 선택한 근거에 실제 값이 있는지도
확인한다. 같은 치료 소견에 여러 기간이 있으면 임의로 하나를 확정하지 않고 검토 대상으로 남긴다.
`consistency_issues`는 검증 단계의 담당자 검토 사유로 전달한다. 현재 표현 차이 검사는
병명의 '염좌'와 치료 소견의 '골절' 조합에 한정하며, 포괄적인 의학적 모순 판정이 아니다.
스캔·빈 페이지가 섞이면 `needs_review`다. 인용 일치는 의미적 정확성을 보장하지 않는다.
같은 페이지에서 복수 인물·상충 정보가 있으면 모델이 놓칠 수 있어 담당자 검토가 필요하다.

추출 API는 **1단계 읽기와 2단계 추출**이며 `eligibility_decision`은 항상 null이다.
**3단계 검증**은 별도 `/verify` API에서 수행한다. [검증 API 안내](VERIFICATION.md)를 참고한다.
문서 진위는 자동 판정하지 않는다. 프런트엔드의 서류 AI 판정·검토함·명부는 새 제출 저장소를 사용한다.
담당자 승인·반려는 업무 백엔드와 새 제출 저장소에 반영하며 검증 결과와 별도로 보존한다.
분류 서비스는 `classifier_agent`(8003)만 사용한다. 구형 저장소의 코드·제출 기록을 가져오는 경로는 없다.

## 제출·프런트엔드 연결

- 업무 백엔드 8002, 새 Qwen API 8003, Ollama 11434를 실행한다.
- Vite `/api` → 8002, `/classifier-api` → 8003. 운영 배포에서도 같은 역방향 프록시가 필요하다.
- `POST /submissions`: multipart file/application_type/military_number/applicant_name. 원본 PDF와 접수 기록을 저장한 뒤 202로 즉시 반환한다. 분석은 서버 작업 큐에서 순서대로 진행한다.
- 분석 상태: `queued`/`analyzing` → `completed` 또는 `failed`/`cancelled`. 완료된 문서만 검토함에 표시한다. 서버 재시작으로 중단된 작업은 `failed`로 남기며 다시 분석할 수 있다. 이 로컬 작업 큐는 Uvicorn 단일 worker로 실행한다.
- `POST /submissions/{id}/cancel`, `/retry`: 분석 취소 및 실패 작업 재시도. 취소 상태는 즉시 저장하며, 이미 진행 중인 Qwen 요청은 응답 종료 후 결과를 버리고 후속 호출을 중단한다.
- `POST /submissions/{id}/reanalyze`: 완료된 원본을 다시 분석한다. 검토함에는 기존 문서를 유지하되 작업 중 확인·결정은 차단하고, 완료 후 체크 항목을 다시 확인한다. 이미 저장된 최종 승인·반려는 자동 취소하지 않는다. 작업 식별자로 취소된 이전 응답이 새 작업 결과를 덮어쓰는 것을 막는다.
- `BUSINESS_API_URL`(기본 `http://127.0.0.1:8002`)은 분석 후 성명으로 대상자를 연결하고 DB 본인 정보로 재검증할 업무 API 주소다. 연결 실패 시 완료 문서는 유지되며 화면에서 군번으로 연결할 수 있다.
- `GET /submissions`, `GET /submissions/{id}`, `GET /submissions/{id}/pdf`: 목록·상세·원본 조회.
- `POST /submissions/{id}/verify`: 저장된 추출 결과를 검증하며 결과와 확인 정보를 저장한다.
  화면은 DB 본인 정보를 사용하는 업무 백엔드 `/postponements/verify`를 통해 호출한다.
- 승인·반려는 업무 백엔드 `/postponements/{id}/approve|reject`에서 처리한다.
  검증 결과가 부족/검토 필요여도 담당자가 최종 판단할 수 있지만, 승인하려면 해당 유형의 근거 체크 항목을 전부 확인해야 한다. 미연결 문서의 반려는 분류기 제출 기록에 저장한다.
- `PATCH /submissions/{id}/review-checks`: 근거 항목별 확인 상태를 저장한다. revision으로 오래된 화면의 덮어쓰기를 차단하며 본인 연결·재검증 후에는 체크를 초기화한다. 최종 승인 시 서버에서도 모든 항목을 검사한다.
- `GET /submissions/{id}/pages/{page}/image`: 원본 페이지 PNG. pdfplumber의 기존 렌더링 의존성을 사용하며, 원본 PDF 좌표에 맞춰 프런트엔드에서 근거 영역을 표시한다.
- 발병일·발급기관·의사 정보는 필드 명세의 `extraction: layout`에 따라 PDF 표/라벨에서 직접 읽는다. Qwen 요청 항목에는 포함하지 않는다. 명확하지 않은 값은 미확인으로 남긴다.
- `POST /submissions/{id}/request-confirmation`: 확인요청 의견 저장. 외부 알림 발송은 하지 않는다.
- 저장 위치: `classifier_agent/data/`의 SQLite 및 PDF. `CLASSIFIER_DATA_DIR`로 변경 가능하며 Git에서 제외된다.
  `/extract-pdf`는 기존처럼 임시 처리이며 `/submissions`만 영구 저장한다.

분석할 PDF는 현재 업로드 API에 직접 제출한다. 분석은 해당 PDF와 지정한 신청 유형을 사용한다.

스캔본은 OCR을 하지 않으므로 읽기 불가 상태로 저장되며 Qwen 추론은 수행하지 않는다.
3단계에서는 읽을 수 있는 근거가 전혀 없으면 ‘근거 부족’으로 판정한다.

## 검증

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_layout_extraction.py backend/tests/test_qwen_extraction.py backend/tests/test_pdf_extract.py backend/tests/test_verification.py backend/tests/test_qwen_submissions.py -q
```

[Qwen 평가 실행기](evaluation/README.md)는 운영 구현과 분리된 고정 입력 평가용이다.

2026-10-06 연동 확인: 기존 시연용 `medical.pdf`를 질병 유형 22개 항목으로
6회 호출했다. 성명·군번·병명·치료기간 등을 추출했으며 원문에 없는 인용은
`invalid`로 차단하고 전체 결과를 `needs_review`로 반환했다.
이는 연결 및 방어 검증 확인이며 22개 항목 전체의 정확도 평가가 아니다.
추출/API 자동 테스트 9개와 평가기 테스트 5개가 통과했다.
