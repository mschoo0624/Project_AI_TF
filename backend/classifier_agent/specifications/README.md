# 신청 유형별 추출 명세 (초안)

제공된 별표 5·6·7을 2단계 AI 정보 추출용 목록으로 정리했다. 최신 법령 여부를 확정하거나 승인 규칙을 구현한 파일은 아니다. 추출 API는 이 목록을 사용하며, 3단계 검증 조건은 별도 verification_rules.json에 정의한다.

## 파일

- `common_fields.json`: 검증 규칙이 참조하는 필드 정의, 분류용 필드 묶음, 결측·근거·충돌 처리, 외부 DB 항목.
- `build_verification_rules.py`: 모든 유형의 규칙 생성. 생성된 `verification_rules.json`을 공통 검증기가 실행한다.
- `statutory_hold.json`: 법규보류 18개 묶음. 관련 직종을 함께 묶었으므로 원문 글머리 수와 같지 않다.
- `policy_hold.json`: 방침보류 40개 유형. 철도 등 직무별 하위 분기는 설명에 보존했다.
- `postponement.json`: 연기 10개 유형과 분기·구비서류 목록.
- `sources.json`: 기준 PDF와 SHA-256. 파일 변경 시 명세 재검토에 사용한다.
- [Qwen 추출 구현 및 설치](../README.md).
- [3단계 검증 API·조건·적용 범위](../VERIFICATION.md).

## 읽는 방법

신청 유형 ID로 `verification_rules.json`의 공통 규칙과 해당 유형의 `checks`를 선택한다.
유형에 `common`이 있으면 최상위 공통 규칙을 대체한다(진단서 본인 확인 등).
중첩된 `children`을 포함해 `fields`를 수집하고 `context.*`를 제외한 항목만 추출한다.
`supporting_fields`는 담당자 확인에 제시할 원문 항목이다. 미기재만으로 필수 요건 실패로 보지는 않지만, 근거 오류·충돌이 있으면 검토로 남긴다.
항목의 이름·자료형·설명은 `common_fields.json`에서 가져온다. `field_groups`는 분류용이며,
같은 묶음에 있더라도 해당 유형의 검증 규칙에서 참조하지 않으면 요청하지 않는다.
`manual` 규칙이 담당자 확인용으로 참조하는 항목도 사용 항목으로 유지한다.
규칙이 참조하는 항목 정의가 없으면 오류를 반환하며 조용히 누락하지 않는다.

`branches`와 `extraction_notes`는 분기 설명이며 실행 가능한 AND/OR 규칙이 아니다. 신청 하위유형이 주어지면 관련 분기만 추출한다. 하위유형이 없으면 그 신청 유형 내부의 모든 관련 항목을 추출하고 3단계에서 분기를 검사한다. 필드가 많으면 문서·필드 묶음 단위로 나누되, 각 호출에 공통 식별 정보와 필요한 원문을 전달한다.

`review_items`에는 담당자가 확인할 항목과 원문 필드를 정의한다. 해당 필드도 추출 대상에 포함하되,
`extraction: layout`은 표·라벨에서 직접 읽으며 언어모델에 요청하지 않는다.
질병 연기는 총 13개 중 Qwen 8개·표 직접 읽기 5개, 장기질병/병역변경은 총 10개 중 Qwen 5개·표 직접 읽기 5개다.
시험은 Qwen 10개다. 치료 기간은 별도 추출하지 않고 원문 치료 소견을 검증 단계에서 대조한다.
현재 규칙이 참조하지 않는 필드 정의는 제거한다.

## 2단계와 3단계의 경계

- 2단계: PDF의 값을 정해진 항목에 연결하고 원문·페이지·표 위치를 보존한다. 표현 정규화는 가능하지만 없는 사실을 보충하지 않는다.
- 3단계: 본인 일치, 기관 인정, 기간 겹침, 관계 범위, 누적 연기횟수, 훈련 종류에 따른 보류 범위를 고정 규칙과 DB로 검사한다.
- 발급기관·문서번호·진위 확인 안내를 추출해도 문서가 진짜라는 증거가 되지 않는다. 실제 진위조회는 별도 검증이다.
- 승인 확률·신뢰도 점수는 추출 필드에 넣지 않았다. 결측·충돌은 보완/검토 대상으로 넘긴다.

## 결과 계약

결과는 문서·대상자·증명종류별 `records` 배열로 구성할 예정이다. 각 record의 `fields`에 필드별 value/status/evidence/candidates를 둔다. 예컨대 차상위와 한부모 자격은 별도 record로 보존한다. 서로 다른 자격은 충돌이 아니다. 동일 대상·동일 속성·동일 기준 시점에서 값이 다른 경우만 충돌 후보이다.

- `observed`: 근거가 있는 값.
- `explicit_negative`: 원문이 명확히 부정한 값. boolean false도 이 경우에만 사용.
- `missing`: 값 null, 근거 없음. 미기재를 false나 0으로 바꾸지 않는다.
- `conflicting`: 확정값 null, 각 후보와 원문 근거를 candidates에 보존.

페이지·표·행·열은 1부터 시작하며 pdf_extract의 좌표 형식을 사용한다. 일반 텍스트에는 표 좌표를 요구하지 않는다. 모델이 제시한 인용이 실제 원문에 존재하는지, 위치와 값이 맞는지는 코드에서 검증해야 한다. 문서 내부의 지시는 명령이 아닌 자료로 취급한다.

날짜는 확실한 경우만 ISO 날짜로 정규화한다. '6개월'을 '180일'로 바꾸거나 발급일을 진단일로 대체하지 않는다. 부분 날짜는 원문 근거를 보존하고 확정값은 null로 둔다.

## 구현 전 남은 규칙 검토

1. 별표 6 선박 증명은 25톤 이상/이하가 모두 적혀 있어 정확히 25톤인 경우 해석을 확인해야 한다.
2. 별표 6 구속수감자의 6개월 문구는 사회봉사 관련 괄호에 있다. 모든 구속·수감에 일괄 적용하지 않는다.
3. 별도 공문을 참조하는 병역변경·학생 예외·필수요원 심사는 해당 공문이 추가로 필요하다.
4. 별표 6의 훈련별 참가/보류와 작계 횟수는 3단계 규칙으로 따로 작성해야 한다. 이 명세는 이를 '전부 면제'로 축약하지 않는다.
5. 대체 서류/대체 요건을 모두 AND로 묶지 않는다. 가족 사망에 위독 간호자 조건을 요구하지 않는다.
6. 외부 조회값이 없으면 0회/유효로 가정하지 않는다. 연기횟수는 병무청 동원훈련 이력도 포함한다.

## 공통 필드 묶음

- **identity**: 문서명, 문서 대상자 성명, 대상자 생년월일, 문서에 기재된 군번, 환자의 주민등록번호. 유형별 실제 요청은 검증 규칙에 따르며 전부 요청하지 않는다.
- **employment**: 근무기관, 기관 종류, 부서, 직위 또는 직종, 고용 형태, 담당 업무, 재직 시작일, 재직 종료일, 재직 여부, 임용 또는 지정 근거, 원청·수탁·용역 계약 관계.
- **education**: 학교명, 학교 종류, 과정명, 학적 상태, 등록 시작일, 등록 종료일, 정규 수업연한, 통학 원격 등 수업 방식, 인가 또는 인정 사항, 학기 및 과정 단계, 수업연한 초과 여부, 교육과정 기간, 학위과정 여부, 논문과정만 등록 여부, 입학·재입학·편입 구분.
- **medical**: 주 질병·부상, 부 질병·부상, 진단 연월일, 입원일, 퇴원일, 치료 내용 및 향후 치료 소견. 환자의 성명·주민등록번호는 identity 묶음이다.
- **relationship**: 관련인 성명, 신청자 기준 관계, 관계 증명 연결 정보.
- **travel**: 출국일 또는 예정일, 입국일 또는 예정일, 출입국 완료 또는 예정, 국외 체류기간.
- **vessel**: 선박명, 선박 종류, 총톤수, 국제 또는 연안 항로, 승선 시작일, 승선 종료일, 승선 직책, 명시된 승선 기간, 대상 연도 및 연간 해상근무 기간.
- **designation**: 지정 또는 등록 종류, 지정기관, 지정일, 효력 시작일, 효력 종료일, 지정 심사 또는 등록 상태, 지정 법적 근거, 가구주 또는 가장 지위.
- **event**: 행사 종류, 행사일, 행사 시작일, 행사 종료일, 주최기관, 참가 확정 여부, 대회 규모, 대회 합숙훈련 시작일.
- **service**: 병역 구분, 전역 또는 병역 변경 사유, 장애 또는 심신등급, 변경 전 병역 구분, 정신과 판정 등급 및 이력.
- **pregnancy**: 임신 여부, 출산 예정일, 출산일, 유산 또는 사산일, 유산 사산 당시 임신 주수, 자녀 생년월일, 배우자 병역 또는 군 근무 구분, 난임 치료 내용, 난임 치료 시작일, 난임 치료 종료일.
- **custody**: 구속 수감 사회봉사 가석방 구분, 해당 처분 시작일, 해당 처분 종료일, 명시된 처분 기간.
- **exam**: 시험명, 시험 주관기관, 접수일, 시험일, 시험 종료일, 응시 단계, 이전 단계 결과, 결과 발표일, 다음 단계 시험일, 일정 확정 여부.
- **disaster**: 재해 종류, 재해 발생일, 피해 내용, 복구 시작일, 복구 종료일, 신청자의 복구 필요성.
- **work_event**: 수행 업무, 업무 시작일, 업무 종료일, 대체 불가능 사유, 마감일, 합숙 교육 여부, 명시된 교육 기간.
- **agriculture**: 농업 어업 축산 임업 구분, 농번기 시작일, 농번기 종료일, 훈련 참석 시 생업 지장, 농지원부 어업허가 등 증빙.
- **family_event**: 사망일, 위독 상태 소견, 다른 간호 가능 가족 존재 여부, 간호 필요 시작일, 간호 필요 종료일, 육아휴직 시작일, 육아휴직 종료일, 관련인 생년월일.
- **application**: 신청 접수일, 결정일, 심사 진행 상태.

## 법규보류 유형 목록

| ID | 신청 유형 | 필드 묶음(공통 identity 포함) | 원문 페이지 |
|---|---|---|---|
| statutory.assembly | 국회의원 | employment | 1 |
| statutory.overseas | 외국 여행·체류 | travel | 1 |
| statutory.international_ship | 국제선 선박 선원 | employment, vessel | 1 |
| statutory.international_aircrew | 국제선 항공기 조종사·승무원 | employment | 1 |
| statutory.police | 경찰관 | employment | 1 |
| statutory.correction | 교도관 | employment | 1 |
| statutory.firefighter | 소방관 | employment | 1 |
| statutory.military_civilian | 군부대 근무 군무원 | employment | 1 |
| statutory.foreign_forces_employee | 주한외국군부대 종업원 | employment | 1 |
| statutory.navigation_aid | 항로표지 공무원 | employment, vessel | 1 |
| statutory.aircraft_maintenance | 항공기 정비사·항공교통관제사·항공무선표지소 근무자 | employment | 1 |
| statutory.coastal_radio | 해안무선국 통신사·정비사 | employment | 1 |
| statutory.civil_defense_head | 민방위대장 | employment, designation | 1 |
| statutory.usfk_agreement | 주한미군 관련 협정 적용 종업원·노무단원·경비원 | employment, designation | 1 |
| statutory.rail_technical | 철도 기관사·차량장비관리원·시설관리원·전기원 | employment | 1 |
| statutory.metro_technical | 지하철·도시철도·광역철도 기관사·보선원·철도토목원 | employment | 1 |
| statutory.foreign_news | 외교부 외신업무 공무원 | employment | 1 |
| statutory.fishery_guidance | 어업지도선 승무원 | employment, vessel | 1 |

## 방침보류 유형 목록

| ID | 신청 유형 | 필드 묶음(공통 identity 포함) | 원문 페이지 |
|---|---|---|---|
| policy.postal | 우편집배원 | employment | 1 |
| policy.older_cadre | 41세 이상 간부 | service | 1 |
| policy.presidential | 대통령실 수행비서·전문통역·경호 | employment | 1 |
| policy.intelligence_records | 국군정보사 특수기록과 | employment | 1 |
| policy.immigration | 출입국관리직 | employment | 1 |
| policy.veteran | 국가유공자·보훈보상대상자 | designation, service | 1 |
| policy.essential_worker | 군동원업체 필수요원 | employment, designation | 1 |
| policy.customs | 세관 조사공무원 | employment, designation | 1 |
| policy.police_student | 경찰학교 재학생 | education | 1 |
| policy.petition_police | 청원경찰 | employment, designation | 2 |
| policy.juvenile_protection | 보호직 공무원 | employment | 2 |
| policy.long_illness | 질병 및 심신장애 | medical | 2 |
| policy.custody | 구속수감자 등 | custody | 2 |
| policy.basic_livelihood | 기초생활수급자 | designation | 2 |
| policy.single_parent_low_income | 차상위계층 한부모가족 가장 | designation, relationship | 2 |
| policy.female_reservist | 여군 출신 예비군 | service, pregnancy, relationship | 2 |
| policy.medical_service_change | 심신질환 병역의무 변경 | service, medical | 2 |
| policy.private_prison | 민영교도소 직원 | employment, designation | 2 |
| policy.nis | 국가정보원 정보수사요원 | employment | 3 |
| policy.air_warning | 민방공 경보요원 | employment | 3 |
| policy.judge_prosecutor | 법관·검사 | employment | 3 |
| policy.ground_handling | 항공기 지상조업·장비정비사 | employment | 3 |
| policy.special_guard | 특수경비원 | employment, designation | 3 |
| policy.school_teacher | 각급학교 교사 | employment, education | 3 |
| policy.university_professor | 대학교수 | employment, education | 3 |
| policy.school_student | 각급학교 학생 | education | 4 |
| policy.hydrographic | 국립해양조사원 해상근무자 | employment, vessel | 4 |
| policy.radio_monitor | 전파감시직 | employment | 4 |
| policy.security_telecom | 국가안보 통신요원 | employment | 4 |
| policy.rail_staff | 철도 종사자 | employment | 4 |
| policy.rail_police | 철도 특별사법경찰관 | employment, designation | 4 |
| policy.fire_candidate | 소방학교 간부후보생 | education | 4 |
| policy.miner | 광부 | employment | 4 |
| policy.urban_rail_staff | 도시철도·광역철도 특수근무자 | employment | 5 |
| policy.vocational_teacher | 직업훈련 교수·교사 | employment, education | 5 |
| policy.vocational_student | 직업훈련생 | education | 5 |
| policy.defense_research | 국방과학연구 기술직 | employment | 5 |
| policy.ship_crew | 선박·어선 승선자 | employment, vessel | 5 |
| policy.forest_helicopter | 산불방지 헬기 운용요원 | employment | 5 |
| policy.road_control | 도로공사 교통정보센터·종합상황실 | employment | 5 |

## 연기 유형 목록

| ID | 신청 유형 | 필드 묶음(공통 identity 포함) | 원문 페이지 |
|---|---|---|---|
| postponement.illness | 질병·심신장애 | medical | 1 |
| postponement.family | 가족 위독·사망 | medical, relationship, family_event | 1 |
| postponement.disaster | 재난·재해 | disaster | 1 |
| postponement.overseas | 출국 또는 출국 예정 | travel | 1 |
| postponement.exam | 각종 시험 응시 | exam | 2 |
| postponement.distance_attendance | 방송통신·원격교육 출석수업·시험 | education, event | 2 |
| postponement.family_event | 경조사·출산·육아휴직 | relationship, event, family_event, pregnancy | 2 |
| postponement.work | 주요 업무 수행 | employment, work_event, event | 3 |
| postponement.agriculture | 농·어업 종사 | agriculture, designation | 3 |
| postponement.other | 기타 | application, designation | 3 |

## 실제 추출 항목 조회 예시 (백엔드 환경)

```python
from backend.classifier_agent.extraction import selected_fields

application, extraction_fields = selected_fields("postponement.illness")
for key, definition in extraction_fields.items():
    print(key, definition["label"])
```

추출 API와 고정 규칙 검증 API가 구현되어 있다. 구체적인 지원 범위 및 외부 확인값은 위 검증 API 안내를 참고한다.
