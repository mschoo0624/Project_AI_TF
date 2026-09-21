# AITF Classifier 독립 서버

이 디렉터리는 `Classifier(1).zip`에서 AITF의 **서류 AI 판정**에 필요한 FastAPI, PDF 추출, 사유 분류, 서류 제출 저장소 및 판정 규칙 원본을 가져온 것입니다. `models.py`의 문법 오류 `None.` 한 곳만 `None`으로 수정했습니다. AITF의 기존 UI, DB, API는 바꾸지 않았습니다.

## Windows PowerShell 실행 (AITF 프로젝트 최상위에서)

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\classifier_agent\requirements.txt
ollama pull qwen2.5:1.5b
cd .\backend\classifier_agent
..\.venv\Scripts\python.exe -m uvicorn API:app --host 127.0.0.1 --port 8001
```

백엔드의 가상환경이 없으면 먼저 `python -m venv .\backend\.venv`로 생성하고 AITF의 `backend/requirements.txt`도 설치하세요. Ollama 앱 자체가 실행 중이어야 하며, 모델 다운로드와 Python 패키지 설치는 별도입니다. `http://127.0.0.1:8001/docs` 또는 `http://127.0.0.1:8001/submissions`로 시작 여부를 확인합니다. `/submissions`가 `[]`를 반환한다면 빈 목록이 정상입니다.

AITF는 별도 터미널에서 `backend` 폴더에서 8002 포트로, Vite는 `frontend` 폴더에서 실행합니다. 기존 `frontend/vite.config.ts`의 `/classifier-api` 프록시와 `backend/user/app/services/classifier_client.py`는 모두 8001번 포트를 사용하므로 **현재 AITF 파일에 추가 수정 없이 연결**됩니다.

## 이식 범위와 제한

- `API.py`, `ML/extraction.py`, `ML/reason_classifier.py`, `ML/submissions.py`: 8001번 서버 기능.
- `ML/reason_classifier.joblib`: 원본의 학습된 분류 모델. `ML/reason_examples.jsonl`: 재학습용 원본 예제. 신뢰할 수 있는 원본 파일에서만 joblib 모델을 로드해야 합니다.
- `models.py`, `rules.py`, `assess.py`: 원본 규칙 판정 엔진을 보존했지만 현재 서류 업로드/승인 API에서는 **호출하지 않습니다.** 별도 DB 연동과 규칙 검증이 필요합니다.
- 기존 Classifier의 `ML/submissions.jsonl`과 `ML/uploads/`은 사용자 제출 자료를 복사하지 않기 위해 **옮기지 않았습니다.** 이 서버를 처음 실행하면 신규 저장소가 생성됩니다. 기존 제출 이력을 이전하려면 별도 마이그레이션이 필요합니다.
- Ollama 모델 가중치 및 Python 가상환경은 이 ZIP에 포함하지 않습니다. API는 인식된 텍스트를 기반으로 추출하므로 이미지 전용 스캔 PDF의 OCR은 별도 준비가 필요합니다.
- AITF의 `보류/연기자 명부`와 `검토함`은 아직 `frontend/public/data.json` 및 스텁 승인 함수에 연결되어 있습니다. **서류 AI 판정 서브탭**만 현재 Classifier 서버에 연결됩니다. AITF DB의 기존 인원·훈련 판정 상태를 자동 갱신하지 않습니다.
- 이 버전은 로컬 개발용 구성입니다. 실명/군번 및 PDF를 다루는 서버의 인증·접근제어, 파일 검증, 저장소 동시성·일관성은 운영 배포 전에 보강해야 합니다.
