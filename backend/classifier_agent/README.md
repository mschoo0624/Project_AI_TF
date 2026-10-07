# Qwen 신청 문서 정보 추출

전자 PDF를 pdfplumber로 읽고, 신청 유형별 명세에 지정된 항목을 로컬
`qwen3:4b-instruct`로 추출한다. 모델 학습·외부 추론 서비스는 사용하지 않는다.
기준 목록은 [specifications/README.md](specifications/README.md)를 참고한다.

## 설치 및 실행

Python 3.10 이상, Ollama가 필요하다. 프로젝트 루트에서:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/classifier_agent/requirements.txt
ollama pull qwen3:4b-instruct
# Ollama 앱/서버가 실행 중이어야 한다. 미실행 환경은 별도 터미널에서 ollama serve.
backend/.venv/Scripts/python.exe -m uvicorn backend.classifier_agent.API:app --host 127.0.0.1 --port 8003
```

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
backend/.venv/Scripts/python.exe -m backend.classifier_agent.extraction frontend/public/pdfs/old/medical.pdf --application-type postponement.illness -o extraction-result.json
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

신청 유형의 모든 field_groups를 사용한다. 분기는 아직 별도 필터링하지 않으며
미기재 항목 전체를 승인 필수 요건으로 취급하지 않는다. 페이지별 최대 6000자,
4개 항목씩 독립 요청하고 이전 대화를 전달하지 않는다. 셀/문장을 통째로 묶어 UTF-8
6100바이트 이내의 입력으로 나누며, 재시도를 포함한 호출 한도는 6500바이트다.
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
구형 `classifier_agent_old`(8001)는 과거 코드·기록 보관용이며 새 화면은 8003을 사용한다.

## 제출·프런트엔드 연결

- 업무 백엔드 8002, 새 Qwen API 8003, Ollama 11434를 실행한다.
- Vite `/api` → 8002, `/classifier-api` → 8003. 운영 배포에서도 같은 역방향 프록시가 필요하다.
- `POST /submissions`: multipart file/application_type/military_number/applicant_name. 원본 PDF와 새 추출 결과를 저장한다.
- `GET /submissions`, `GET /submissions/{id}`, `GET /submissions/{id}/pdf`: 목록·상세·원본 조회.
- `POST /submissions/{id}/verify`: 저장된 추출 결과를 검증하며 결과와 확인 정보를 저장한다.
  화면은 DB 본인 정보를 사용하는 업무 백엔드 `/postponements/verify`를 통해 호출한다.
- 승인·반려는 업무 백엔드 `/postponements/{id}/approve|reject`에서 처리한다.
  검증 결과가 부족/검토 필요여도 담당자가 최종 판단할 수 있다.
- `POST /submissions/{id}/request-confirmation`: 확인요청 의견 저장. 외부 알림 발송은 하지 않는다.
- 저장 위치: `classifier_agent/data/`의 SQLite 및 PDF. `CLASSIFIER_DATA_DIR`로 변경 가능하며 Git에서 제외된다.
  `/extract-pdf`는 기존처럼 임시 처리이며 `/submissions`만 영구 저장한다.

과거 제출 건은 신청 유형을 담당자가 지정해 새 엔진으로 재처리한다. 기존 분석값·승인 상태를
새 결과로 복사하지 않는다. 원본 기록은 보존하고 새 기록은 검토대기로 등록한다.
동일 과거 ID의 중복 실행은 기존 재처리 결과를 반환한다.

```powershell
backend/.venv/Scripts/python.exe -m backend.classifier_agent.reprocess_legacy --submission-id 과거ID --application-type postponement.illness
```

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
