# 3단계 신청 근거 검증 API

2단계 추출 결과와 DB/담당자의 확인값을 **고정 규칙**으로 대조한다. Qwen은 호출하지 않는다.
범위는 신청한 유형에 대한 근거 검토이며 유형 추천, 승인 확률, 승인·반려 DB 저장을 수행하지 않는다.
검증 API와 별도로 제출 저장·담당자 승인/반려 경로가 연결되어 있다. [제출 API 안내](README.md#제출프런트엔드-연결)를 참고한다.

## 결과

| result | 표시 | 의미 |
|---|---|---|
| sufficient | 근거 충족 | 현재 규칙의 필요한 조건과 외부 확인값 모두 충족 |
| insufficient | 근거 부족 | 필요한 사실·날짜·이력 등이 없어 충족 입증 불가 |
| not_met | 요건 불충족 | 필수조건의 명시적 불일치 또는 제한 초과 |
| review_required | 담당자 검토 필요 | 충돌·추출 오류·미지원 표현·별도 공문·수동 조건 존재 |

`checks`는 조건 이름, `pass/fail/missing/review`, 실제 값, 원문 근거, 자식 조건,
관련 기준표를 반환한다. `missing_information`은 필요한 미제공 항목이다.
OR 요건 중 하나가 충족되면 다른 대체 요건의 미제공 항목을 보완 요구하지 않는다.
`required_for_result=false`인 자식 조건은 이미 충족된 OR의 대체 경로다.
필수조건의 명시적 실패는 다른 미확인 조건보다 우선한다. 다만 기준표 자체가 바뀌면
결론을 내리지 않고 검토로 돌린다.

`related_provisions`에는 조항명(제23/24조 관련 별표), 유형명, PDF 페이지,
원문 페이지 텍스트, SHA-256 및 PDF 열람 URL이 있다. 페이지 원문에는 같은 페이지의
다른 유형도 있으므로 `item`과 함께 표시한다. 원문 인용을 AI로 작성하지 않는다.
본인 일치 등 시스템 검사는 법조항으로 가장하지 않아 해당 check의 citation은 null이다.

## API 사용

기존 [실행 안내](README.md)에 따라 8003 서버를 실행한다.

- `GET /verification-rules`: 68개 유형의 조건·출처·적용 범위 조회.
- `GET /verification-sources/5`, `/6`, `/7`: 저장소의 원본 기준 PDF.
- `POST /verify`: 하나의 신청에 대한 추출 결과들을 검증.

요청 구조(아래 documents에는 `/extract-pdf` 응답 객체 전체를 넣는다):

```json
{
  "documents": ["이 자리에 추출 결과 객체"],
  "context": {
    "applicant_name": {"value": "홍길동", "source": "person:대상자ID"},
    "applicant_service_number": {"value": "22-76010001", "source": "person:대상자ID"},
    "training_start": {"value": "2026-05-10", "source": "training:훈련ID"},
    "training_end": {"value": "2026-05-10", "source": "training:훈련ID"},
    "documents_acceptable": {"value": true, "source": "담당자 검토기록:실제 기록 ID"},
    "training_scope_applicable": {"value": true, "source": "훈련종류별 범위 확인:실제 기록 ID"}
  }
}
```

위 예시의 확인값은 요청 구조 설명이다. 실제 검토 없이 true로 채우면 안 된다.
`context`는 신청자가 자기 확인하는 입력이 아니라 업무 백엔드/담당자의 확인 자료다.
source 문자열을 받는 것만으로 해당 자료나 담당자 권한이 인증되지는 않는다.
8003는 내부 localhost 서비스이며 외부 공개 시 인증·검토 기록 연결이 별도로 필요하다.

공통 확인값:

- `documents_acceptable`: 해당 분기의 대체/조합 구비서류, 발급주체 및 적용 기간 확인.
- `training_scope_applicable`: 별표 6의 ○/×, 작계 횟수, 법규보류 예외 등 **신청 훈련종류**의 범위 확인.
- 본인 식별: 성명 + 군번 또는 생년월일. 군번의 명시적 불일치를 생년월일 일치로 덮지 않는다.

유형별 외부 확인값은 `/verification-rules`에서 `context.`로 시작하는 필드와 조건 설명을
확인한다. 시험·주요업무 통산 횟수는 병무청 이력을 포함한 완료된 조회값이어야 한다.
누락값은 null/미제공이며 0회나 true로 대체하지 않는다. 자료형 불일치는 검토로 돌린다.

## 업무 DB 연결

업무 백엔드에 `POST /postponements/verify`를 추가했다. 요청:

```json
{
  "person_id": "대상자 군번",
  "education_id": 123,
  "documents": ["추출 결과 객체"],
  "context": {}
}
```

이 경로는 DB의 성명·군번으로 입력을 덮어쓰고, `education_id`가 있으면 해당 대상자의
훈련인지 확인해 예정일을 `training_start`로 넣는다. `VERIFICATION_URL` 기본값은
`http://127.0.0.1:8003`이며 기존 `CLASSIFIER_URL`(8001)과 분리했다.
현재 DB에는 훈련 종료일, 생년월일, 병무청 포함 통산 연기횟수 등의 완전한 자료가 없다.
종료일을 시작일과 같다고 추정하거나 현 DB 이력을 전체 이력으로 세지 않는다.
부족한 정보는 context로 검증된 값을 추가하거나 보완 필요로 남긴다. DB 스키마 변경은 없다.

## 규칙 범위와 한계

68개 유형을 모두 원문과 연결했다. `coverage`의 뜻:

- `structured` 53개: 고정 비교 조건을 작성했다. **필요한 외부 확인값까지 자동 수집한다는 의미는 아니다.**
- `partial` 14개: 비교 가능한 부분을 검사하되 일부 분기는 담당자 검토가 필요하다.
- `manual` 1개: 기타(대체역/필수요원 심사)는 별도 업무지시 등을 포함해 검토한다.

유형별 대체 분기 중 자동 검사 가능한 분기가 충족되면 partial 유형도 sufficient가 될 수 있다.
기관·직무 인정, 발급주체 적합성, 훈련범위 등은 출처가 있는 외부 확인값을 필요로 한다.
명시되지 않은 표현을 억지로 부적합 처리하지 않고 review로 돌린다.
예를 들어 `6개월`을 `180일`로 바꾸지 않으며, 정확히 25톤인 선박 서류 구분은 수동 검토다.
사망일 기준 7일은 현재 규칙에서 사망일 포함 7일(당일~6일 후)로 작성했다.
본인 결혼은 소집일 기준 ±14일, 배우자 출산은 소집기간과 ±30일 범위를 비교한다.

추출 결과의 원문 인용·자료형·완전한 날짜를 다시 검사한다. 동일 필드의 문서 간 상충은
검토 대상이다. 여러 자격/인물의 동명이인, 위조 문서, 인용의 의미적 정합성 전부를 판별하지 않는다.
문서 내용 자체를 조작한 클라이언트 요청을 인증하는 기능도 아니다.
`authenticity=not_checked`, `automatic_approval=false`를 반환한다.

규칙은 사용자 제공 PDF 해시에 고정되어 있으며 현행 법령 전체 검증 완료를 주장하지 않는다.
[국가법령정보센터의 훈령](https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000271624)은
현행본 대조용 링크다. 실행 중 웹 내용을 읽어 규칙을 자동 변경하지 않는다.

## 유지보수·검증

조건 정의: `specifications/build_verification_rules.py`.
운영 시 읽는 데이터: `specifications/verification_rules.json`.
수정 후 아래 명령으로 재생성하고 테스트한다. 생성기는 LLM 없이 명시적 조건만 사용한다.

```powershell
backend/.venv/Scripts/python.exe backend/classifier_agent/specifications/build_verification_rules.py
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_verification.py -q
```

테스트 입력은 코드 안의 가상 조건이며 모델 평가나 실제 신청자 자료가 아니다.
기간 경계·OR 대체 요건·미기재·횟수 제한·본인 불일치·상충·변조 인용·기준표 변경,
68개 유형에 빈 입력을 넣어 잘못 충족되지 않는지, DB의 본인 값 우선 적용을 검사한다.
