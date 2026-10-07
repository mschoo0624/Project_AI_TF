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
