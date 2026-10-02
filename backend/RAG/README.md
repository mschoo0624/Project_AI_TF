# 예비군 법령 RAG

예비군 관련 법령(예비군법, 시행령, 시행규칙, 국방부령)에 대해 질문하면, 관련 조문을 찾아서
그 조문만을 근거로 LLM이 답변하는 RAG(Retrieval-Augmented Generation) 시스템입니다.

> [Legal-RAG](https://github.com/Fan-Luo/Legal-RAG) (Apache 2.0, 중국 민법전/미국 UCC용)를 바탕으로
> 한국어 + 예비군 법령 전용으로 새로 작성했습니다. 원본 파일은 `_old_original/` 폴더에 보관되어 있습니다.

---

## 1. 빠른 시작 (Windows)

```powershell
# 0) 가상환경 + 패키지 설치 (최초 1회)
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 1) 법령 파일 -> 조문 단위 데이터   (data/raw/*.doc -> data/processed/laws.jsonl)
python -m scripts.preprocess

# 2) 벡터 인덱스 생성              (-> data/index/embeddings.npy)
#    최초 실행 시 임베딩 모델(BAAI/bge-m3, 약 2.3GB)을 다운로드합니다.
python -m scripts.build_index

# 3) LLM 설정 (둘 중 하나. 설정하지 않으면 "조문 검색"만 동작)
$env:OPENAI_API_KEY = "sk-..."                       # (A) OpenAI
$env:OPENAI_MODEL   = "gpt-4o-mini"
# $env:OPENAI_BASE_URL = "http://localhost:11434/v1"  # (B) Ollama (무료, 로컬)
# $env:OPENAI_MODEL    = "qwen2.5:7b" # 현재 우리 메인 모델

# 4-a) 웹 UI
python -m uvicorn legalrag.server:app --port 8000
#      -> 브라우저에서 http://127.0.0.1:8000

# 4-b) 또는 터미널에서
python -m scripts.ask "예비군 훈련은 1년에 최대 며칠까지 받나요?"
python -m scripts.ask --search-only "직장 보장"      # LLM 없이 조문만 확인
```

법령을 추가/교체할 때: 국가법령정보센터(law.go.kr)에서 법령을 **한글(.doc)** 로 저장해 `data/raw/`에 넣고
1), 2) 단계를 다시 실행하면 됩니다.

---

## 2. 동작 원리

```
[오프라인: 1회]
 data/raw/*.doc ──(rtf.py)──> 텍스트 ──(parser.py)──> 조문 단위 레코드 ──> laws.jsonl
   (실제로는 RTF 파일)                  + references.py: 조문 간 인용 관계 추출
                                                      │
                                     (store.py) bge-m3 임베딩 ──> embeddings.npy

[온라인: 질문마다]
 질문 ─┬─> ① 벡터 검색 (의미 유사도, bge-m3)      ─┐
       ├─> ② 키워드 검색 (BM25, 한국어 토크나이저) ─┼─> ③ 점수 융합(RRF) ─> ⑤ 버전 정리 ─> ⑥ 참조 조문 추가
       └─> ④ 조문 직접 지정 ("시행령 제14조")      ─┘                                        │
                                                                                          ▼
                                     LLM (prompts.py의 한국어 지시문 + 조문) ──> 답변 + 근거 조문
```

1. **전처리** – law.go.kr의 `.doc` 파일은 사실 RTF 파일입니다. `rtf.py`가 텍스트를 뽑고,
   `parser.py`가 앞부분 목차를 건너뛴 뒤 `제N장`, `제N조(의M)(제목)`, `부칙` 단위로 자릅니다.
   조문 하나 = 검색 단위 하나(chunk)입니다. 각 조문에는 법령명, 법령 종류, 공포번호, 시행일, 장, 조문번호가 붙습니다.
2. **인용 관계** – `references.py`가 "법 제6조", "영 제32조", "「예비군법」 제14조의3", "같은 법 시행령 제32조"
   같은 표현을 찾아 어떤 조문이 어떤 조문을 인용하는지 기록합니다. (예비군 하위법령에서 "법" = 예비군법, "영" = 예비군법 시행령)
3. **하이브리드 검색** – 의미 검색(비슷한 뜻)과 키워드 검색(같은 단어)을 함께 사용하고 순위를 합칩니다.
   한국어는 조사가 붙어서("훈련비를", "훈련비는") 단어가 정확히 일치하지 않으므로 `tokenizer.py`는 조사를 떼고 2글자 단위로도 색인합니다.
4. **조문 직접 지정** – 질문에 "시행령 제14조"처럼 조문 번호가 있으면 그 조문을 항상 맨 앞에 넣습니다.
5. **버전 처리** – `예비군법`은 두 버전이 있습니다 (제21388호 시행 2026-08-28 / 제21770호 시행 2026-12-10).
   기준일(기본: 오늘)에 시행 중인 최신 버전 = **현행**, 아직 시행 전인 버전 = **시행 예정**, 그 이전 = 종전(제외).
   시행 예정 조문은 현행과 내용이 다를 때만 함께 보여주고, LLM에게 둘을 구분해서 설명하도록 지시합니다.
6. **참조 조문 확장** – 상위 검색 결과가 인용하거나, 상위 결과를 인용하는 조문을 최대 4개 추가합니다.
   예: 예비군법 제6조(훈련, "대통령령으로 정하는 바에 따라")가 검색되면 이를 구체화한 시행령 조문이 함께 들어옵니다.
7. **답변 생성** – `prompts.py`의 지시문: 제공된 조문만 근거로, 「법령명」 제N조 형식으로 인용, 모르면 모른다고 답변.

---

## 3. 폴더 구조

```
RAG/
├── data/
│   ├── raw/                 원본 법령 파일 (.doc = RTF)  ← 여기에 법령을 넣으세요
│   ├── processed/laws.jsonl 조문 단위 데이터 (자동 생성)
│   └── index/               임베딩 벡터 (자동 생성)
├── legalrag/                핵심 코드
│   ├── config.py            모든 설정값 (환경변수로 변경 가능)
│   ├── rtf.py               .doc(RTF) -> 텍스트
│   ├── parser.py            텍스트 -> 조문 레코드 (장/조/부칙/삭제 조문 처리)
│   ├── references.py        조문 간 인용 관계 추출, 질문 속 조문번호 인식
│   ├── tokenizer.py         BM25용 한국어 토크나이저
│   ├── store.py             laws.jsonl / 임베딩 저장·불러오기
│   ├── retriever.py         하이브리드 검색 + 버전 처리 + 참조 확장
│   ├── prompts.py           LLM 지시문 (답변 스타일은 여기서 수정)
│   ├── llm.py               OpenAI 호환 LLM 클라이언트 (OpenAI / Ollama 등)
│   ├── pipeline.py          검색 + LLM 을 묶은 RagPipeline
│   └── server.py            FastAPI 웹 서버
├── scripts/
│   ├── preprocess.py        1단계: 전처리
│   ├── build_index.py       2단계: 인덱스 생성
│   └── ask.py               터미널에서 질문
├── ui/index.html            웹 화면
├── tests/                   python -m pytest
└── _old_original/           원본 Legal-RAG 파일 보관 (필요 없으면 삭제해도 됨)
```

---

## 4. 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | (없음) | OpenAI 키. 없고 `OPENAI_BASE_URL`도 없으면 검색 전용 모드 |
| `OPENAI_BASE_URL` | (없음) | OpenAI 호환 서버 주소 (Ollama: `http://localhost:11434/v1`) |
| `OPENAI_MODEL` | `gpt-4o-mini` | 사용할 LLM 모델 이름 |
| `RAG_TOP_K` | `6` | LLM에 넘기는 조문 수 (참조 확장 조문은 별도로 최대 4개 추가) |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-m3` | 임베딩 모델. 바꾸면 `build_index` 다시 실행 |
| `RAG_RERANK` | `false` | `true`면 bge-reranker-v2-m3로 재정렬 (더 정확, CPU에서 느림, 모델 2.3GB 추가) |
| `RAG_EXPAND_REFS` | `true` | 인용 관계 조문 추가 여부 |
| `RAG_INCLUDE_ADDENDA` | `true` | 부칙 조문 검색 포함 여부 |
| `RAG_REFERENCE_DATE` | 오늘 | 현행/시행 예정 판단 기준일 (예: `2026-12-10`) |

---



## License

Apache License 2.0 (원본 Legal-RAG 저작권 고지는 `LICENSE` 참조).
