# Qwen 고정 입력 평가

`qwen_cases.json`은 기존 frontend 전자 PDF 16개의 pdfplumber 추출 텍스트와
110개 항목의 수작업 기대값이다. 실제 신청 자료가 아닌 저장소의 시연용 서류다.
`qwen_common_fields.json`은 해당 평가 당시의 필드 명세다.

Ollama에 `qwen3:4b-instruct`를 설치하고 실행한 뒤:

```powershell
backend/.venv/Scripts/python.exe backend/classifier_agent/evaluation/run_qwen.py --output backend/classifier_agent/evaluation/runs/my-qwen
backend/.venv/Scripts/python.exe backend/classifier_agent/evaluation/analyze_runs.py backend/classifier_agent/evaluation/runs/my-qwen
backend/.venv/Scripts/python.exe backend/classifier_agent/evaluation/export_pdf_review.py backend/classifier_agent/evaluation/runs/my-qwen
```

새 출력 경로를 사용한다. 이전 문서 대화를 전달하지 않으며 요청마다 모델을 내린다.
입력·정답·설정·원문 응답·채점 결과를 저장한다. runs는 Git에서 제외된다.
평가기는 512토큰 단일 요청이고, 운영 추출기는 페이지/항목 묶음별 호출과 결과 검증을
추가했으므로 이 평가기 결과를 운영 구현의 성능 수치로 사용하면 안 된다.

`prepare_pdf_cases.py`는 원본 PDF에서 입력을 다시 준비하는 도구다.
`test_scoring.py`는 형식/근거/자료형 채점 및 정답 누출 방지를 검사한다.

## 사용자 작성 PDF를 운영 파이프라인으로 확인

```powershell
backend/.venv/Scripts/python.exe -m backend.classifier_agent.evaluation.test_two_user_pdfs
```

`frontend/public/pdfs/홍길동.pdf`(질병), `홍진호.pdf`(시험)를 읽어 PDF 추출부터
Qwen 항목 추출·규칙 검증까지 실행한다. 파일 해시, 입력, 모델 원문 응답, 추출값,
검증 결과를 `runs/user_pdfs_실행시각`에 저장한다. 업무 DB는 정확한 성명 일치 조회만
수행하며 제출·승인·훈련 기록을 쓰지 않는다. 훈련일이나 본인 확인 정보를 만들어 넣지 않는다.
두 문서는 사용자가 작성한 검증용 문서이며, 전체 문서군의 정확도 수치로 일반화할 수 없다.

후처리 변경을 확인할 때 `--reuse-responses 이전실행폴더`를 지정할 수 있다.
모델 입력 메시지가 완전히 일치하는 경우에만 저장된 응답을 재사용한다. 신규 요청이나
실패 항목 재시도는 실제 Qwen을 호출한다. 각 호출의 `reused_response`와 manifest의
`reused_run`으로 구분하며, 이를 전부 새 추론을 한 실험으로 보고해서는 안 된다.
