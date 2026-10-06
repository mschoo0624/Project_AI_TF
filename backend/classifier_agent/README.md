# 새 문서 처리 작업 공간

전자 PDF의 표·셀·텍스트 추출부터 단계적으로 구현할 디렉터리입니다.
`pdfplumber`로 표·텍스트·좌표를 추출하는 독립 모듈입니다. 기존 코드나 Ollama에 의존하지 않으며 API 서버는 아직 제공하지 않습니다.

## 설치

Python 3.10 이상을 사용하세요. 현재 검증 환경은 Windows / Python 3.14입니다.
프로젝트 루트에서 다음을 실행합니다.

```powershell
python -m venv backend/.venv
# 이미 가상환경이 있으면 생성 단계는 생략합니다.
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

새 추출기만 설치하려면 다음 명령을 사용합니다.

```powershell
backend/.venv/Scripts/python.exe -m pip install -r backend/classifier_agent/requirements.txt
```

Linux/macOS에서는 실행 파일을 `backend/.venv/bin/python`으로 바꿉니다.
`pdfplumber==0.11.10`과 PDF 파싱·이미지 처리 의존 패키지는 pip가 함께 설치합니다.
추가 언어모델, GPU, OCR 엔진, 학습 데이터는 필요하지 않습니다.

## 사용

프로젝트 루트에서 실행합니다. 출력 디렉터리는 미리 존재해야 하며, 기존 출력 파일은 덮어쓰지 않습니다.

```powershell
backend/.venv/Scripts/python.exe -m backend.classifier_agent.pdf_extract "문서.pdf" -o "추출결과.json"
```

선이 없는 표는 다음 옵션을 시도할 수 있습니다. 일반 문장을 표로 인식할 수 있으므로 결과 확인이 필요합니다.

```powershell
backend/.venv/Scripts/python.exe -m backend.classifier_agent.pdf_extract "문서.pdf" --table-strategy text -o "추출결과.json"
```

Python에서 사용:

```python
from backend.classifier_agent.pdf_extract import extract_pdf

result = extract_pdf("문서.pdf")
```

`backend` 디렉터리에서 실행하는 경우 모듈 경로는 `classifier_agent.pdf_extract`입니다.

## 결과와 한계

- UTF-8 JSON: 페이지별 `text`, 단어 좌표 `words`, 표 `tables`, 항목 후보 `field_candidates`를 반환합니다.
- 표는 `rows` 안에 셀의 `text`, `bbox`를 저장합니다. 병합 셀로 생긴 빈 격자 위치는 `null`로 보존합니다.
- 좌표는 PDF 포인트 단위이며 왼쪽 위 원점 기준 `[x0, top, x1, bottom]`입니다. 페이지·표·행·열 번호는 1부터 시작합니다.
- 정확히 일치하는 알려진 항목명(성명, 군번, 직위 등)의 바로 오른쪽 셀만 항목 후보로 연결합니다. `성 명`도 `성명`으로 연결합니다. 후보는 배열이므로 같은 항목이 여러 번 나와도 덮어쓰지 않습니다.
- 항목 후보는 위치 기반 결과입니다. 표의 아래 셀 연결, 복잡한 병합 구조, 직업·사유 추론이나 신청 판정은 하지 않습니다. 인식되지 않은 항목도 원문 표에는 남습니다.
- 한국어를 번역하지 않고 내장 문자로 읽습니다. 잘못된 글꼴 매핑, 깨진 텍스트 레이어, 불규칙한 표에서는 결과가 부정확할 수 있습니다.
- 스캔·이미지의 글자는 읽지 않습니다. 텍스트 없는 페이지는 `no_text`, 읽을 수 있는 페이지와 없는 페이지가 섞이면 문서 상태는 `partial`입니다. 이미지가 함께 있으면 경고를 제공합니다.
- 종료 코드: `0` 모든 페이지에 텍스트 있음, `2` 일부 또는 전체 페이지에 텍스트 없음, `1` 파일·암호·출력 오류. `0`은 의미나 표 추출 정확성의 보증이 아닙니다.
- 원본 PDF와 기존 DB·제출 저장소를 변경하지 않습니다.

## 검증

백엔드 의존성을 설치한 뒤 프로젝트 루트에서:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_pdf_extract.py -q
```

테스트는 임시 전자 PDF를 생성하여 한글 셀과 좌표, 반복 항목 보존, 텍스트 없는 페이지, 잘못된 파일 처리를 확인합니다. 실제 신청서 전체에 대한 정확도 평가는 별도로 필요합니다.

## 현재 연결

- 기존 서버: `../classifier_agent_old/API.py`, 포트 `8001`.
- 프런트엔드 `/classifier-api`와 업무 백엔드 `CLASSIFIER_URL`은 기존 연결을 유지합니다.
- 기존 제출 PDF, 제출 이력, 모델과 기준 문서는 `classifier_agent_old`에 보존되어 있습니다.
- 새 구현으로 API를 전환하거나 기존 자료를 이전하는 작업은 아직 수행하지 않았습니다.

기존 서버 실행 방법은 [기존 서버 README](../classifier_agent_old/README.md)를 참고하세요.

## 첫 작업 범위

- 텍스트 레이어가 있는 전자 PDF만 취급합니다.
- 표 구조, 셀 텍스트, 페이지와 좌표를 추출합니다.
- 스캔 OCR, 신청 판정, 프런트엔드 연결은 이후 별도 단계에서 구현합니다.
