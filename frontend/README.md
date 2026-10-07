# AITF 프론트엔드

예비군 업무체계 AITF의 웹 화면입니다. React, TypeScript, Vite를 사용합니다.

## 개발 환경 실행 (Windows PowerShell)

Node.js와 npm이 설치되어 있어야 합니다. 아래 명령은 **프로젝트 최상위 `AITF` 폴더**에서 실행합니다.

```powershell
cd .\frontend
npm install
npm run dev
```

개발 서버가 출력하는 주소(일반적으로 `http://localhost:5173`)를 브라우저에서 엽니다. 이후 다시 실행할 때는 `frontend` 폴더에서 `npm run dev`만 실행하면 됩니다. 종료하려면 실행 중인 터미널에서 `Ctrl + C`를 누릅니다.

### 백엔드 연결

프론트엔드에서 API를 사용하는 기능은 백엔드 서버도 필요합니다. **별도의 PowerShell 터미널**에서 프로젝트 최상위 `AITF` 폴더를 기준으로 실행합니다.

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m uvicorn user.app.main:app --host 127.0.0.1 --port 8002
```

`frontend/vite.config.ts`는 개발 중 `/api`로 시작하는 요청을 `http://localhost:8002`로 전달하고, 전달 전에 `/api` 접두사를 제거합니다. 백엔드 설치 및 가상환경 준비는 [`backend/README.md`](../backend/README.md)를 참고하세요.

법령 챗봇(화면 오른쪽 위 **법령 챗봇** 버튼)은 RAG 서버가 따로 필요합니다. `/rag-api` 요청은 `http://127.0.0.1:8004`로 전달되며, 실행 방법은 [`backend/README.md`](../backend/README.md#run-law-chatbot-rag-windows-powershell)를 참고하세요. 챗봇을 열면 오른쪽에 패널이 생기고 작업 화면이 그만큼 왼쪽으로 밀립니다.

## 개발 명령

### 보류·연기 문서 처리

기존 업무 백엔드(8002) 외에 프로젝트 루트의 별도 터미널에서 새 문서 API를 실행합니다.

```powershell
backend/.venv/Scripts/python.exe -m uvicorn backend.classifier_agent.API:app --host 127.0.0.1 --port 8003
```

Ollama에 `qwen3:4b-instruct`가 설치되어 있어야 합니다. `/classifier-api`는 8003으로 전달됩니다.
서류 AI 판정·검토함·명부는 실제 제출 및 신청 DB를 공유하며 `public/data.json`을 읽지 않습니다.
승인·반려·확인요청은 저장됩니다. 확인요청은 내부 기록이며 외부 발송은 하지 않습니다.
추출하지 않는 도장·서명 감지나 정확도 확률은 표시하지 않습니다.
훈련시간·적용 기간을 계산할 수 없는 항목은 `—`/확인 필요로 표시합니다.

다른 배포 경로는 `VITE_API_BASE_URL`, `VITE_CLASSIFIER_API_BASE_URL`로 지정할 수 있습니다.
운영 웹 서버도 `/api`(8002), `/classifier-api`(8003) 프록시를 설정해야 합니다.
문서 분석은 수 분 걸릴 수 있으므로 프록시의 처리 시간을 충분히 허용하세요.
설치·저장 경로는 [문서 API 안내](../backend/classifier_agent/README.md)를 참고하세요.

데이터 연결 회귀 테스트: `node --test tests/review-api.test.mjs`.

다음 명령은 모두 `frontend` 폴더에서 실행합니다.

| 명령 | 용도 |
| --- | --- |
| `npm run dev` | Vite 개발 서버 실행 |
| `npm run build` | TypeScript 검사 후 배포용 파일 생성 (`dist/`) |
| `npm run lint` | ESLint 검사 |
| `npm run preview` | 빌드된 결과를 로컬에서 미리보기 (`npm run build` 후 실행) |

## 주요 설정 파일

- `package.json`: 의존성 및 개발 명령
- `vite.config.ts`: Vite 플러그인과 개발 서버의 API 프록시 설정
- `eslint.config.js`: 코드 검사 규칙
