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

## 개발 명령

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
