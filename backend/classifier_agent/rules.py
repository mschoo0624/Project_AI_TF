"""규칙 표 -> 그냥 데이터임
"""
from __future__ import annotations

from dataclasses import dataclass

from models import (
    Branch,
    DocType,
    EducationEffect,
    ExemptionType,
    MobilizationEffect,
    PostponeReason,
    TrainingType,
)

# ---------------------------------------------------------------------
# 연차별 훈련 부과
# ---------------------------------------------------------------------
# 0년차      전역 당해. 편성만 되고 훈련 없음
# 1~4년차    동원지정 → 동원훈련 2박3일 28시간
#            동원미지정 → 동미참훈련 (육군 출퇴근 4일 32h / 해·공군 2박3일 28h)
# 5~6년차    기본훈련 8h + 작계훈련 12h = 20h
# 7~8년차    신규 훈련 없음. 1~6년차 미이수분만 이수

MOBILIZATION_HOURS = 28.0
NON_DESIGNATED_ARMY_HOURS = 32.0
NON_DESIGNATED_NAVY_HOURS = 28.0   # VERIFY: 해·공군 2박3일 입영
BASIC_HOURS = 8.0
OPS_HOURS = 12.0                   # 전·후반기 각 6시간
BASIC_OPS_HOURS = BASIC_HOURS + OPS_HOURS   # 20.0

MAX_RESOURCE_YEAR = 8


def base_training(resource_year: int, designated: bool, branch: Branch):
    """보류·연기 적용 전, 연차만으로 정해지는 훈련. (유형, 시간)"""
    if resource_year <= 0:
        return TrainingType.NONE, 0.0
    if 1 <= resource_year <= 4:
        if designated:
            return TrainingType.MOBILIZATION, MOBILIZATION_HOURS
        hours = (NON_DESIGNATED_ARMY_HOURS if branch.is_army_style
                 else NON_DESIGNATED_NAVY_HOURS)
        return TrainingType.NON_DESIGNATED, hours
    if 5 <= resource_year <= 6:
        return TrainingType.BASIC_OPS, BASIC_OPS_HOURS
    if resource_year <= MAX_RESOURCE_YEAR:
        return TrainingType.CARRYOVER, 0.0   # 이월분만
    return TrainingType.NONE, 0.0


# ---------------------------------------------------------------------
# 보류 규칙
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class ExemptionRule:
    code: str
    kind: ExemptionType
    name: str
    legal_basis: str
    occupations: frozenset[str]
    required_docs: tuple[DocType, ...]
    mobilization: MobilizationEffect
    education: EducationEffect
    education_hours: float = 0.0     # education 이 REDUCED 일 때만 사용
    recheck_months: int = 12         # 자격 유지 재확인 주기
    handler: str | None = None


# --- 법규보류 (예비군법 5조, 시행령 11조) ---------------------------------
# 동원훈련 비대상 + 예비군교육훈련 면제
STATUTORY = (
    ExemptionRule(
        "ST-PUBLIC", ExemptionType.STATUTORY, "국회의원·경찰·소방·군무원·교도관 등",
        "예비군법 제5조, 시행령 제11조",
        frozenset({
            "국회의원", "경찰관", "소방관", "군무원", "교도관",
            "항공기정비사", "항공교통관제사", "철도종사원",
            "해안무선국통신사", "어업지도선승선요원",
        }),
        (DocType.EMPLOYMENT,),
        MobilizationEffect.EXEMPT, EducationEffect.EXEMPT,
    ),
    ExemptionRule(
        "ST-OVERSEAS", ExemptionType.STATUTORY, "국외 1년 이상 체류",
        "예비군법 제5조, 시행령 제11조",
        frozenset(), (DocType.EXIT_ENTRY,),
        MobilizationEffect.EXEMPT, EducationEffect.EXEMPT,
        handler="overseas", recheck_months=6,
    ),
    ExemptionRule(
        "ST-SEAFARER", ExemptionType.STATUTORY, "외항선원",
        "예비군법 제5조, 시행령 제11조",
        frozenset({"선원", "항해사", "기관사", "외항선원"}),
        (DocType.EMPLOYMENT, DocType.BOARDING),
        MobilizationEffect.EXEMPT, EducationEffect.EXEMPT,
        handler="seafarer", recheck_months=6,
    ),
)

# --- 방침보류 (예비군법 5조, 시행령 11조) ---------------------------------
# 동원훈련 손실보충부대 지정 + 교육훈련 면제 또는 일부(8시간)

POLICY_REDUCED_HOURS = 8.0

POLICY = (
    ExemptionRule(
        "PL-POSTAL", ExemptionType.POLICY, "우편집배원",
        "예비군법 제5조, 시행령 제11조",
        frozenset({"우편집배원"}), (DocType.EMPLOYMENT,),
        MobilizationEffect.LOSS_REPLACEMENT, EducationEffect.REDUCED,
        POLICY_REDUCED_HOURS,
    ),
    ExemptionRule(
        "PL-STUDENT", ExemptionType.POLICY, "각급학교 학생",
        "예비군법 제5조, 시행령 제11조",
        frozenset({"대학생", "대학원생", "각급학교학생", "학생"}),
        (DocType.ENROLLMENT,),
        MobilizationEffect.LOSS_REPLACEMENT, EducationEffect.REDUCED,
        POLICY_REDUCED_HOURS, recheck_months=6,   # 휴학·졸업이 잦음
    ),
    ExemptionRule(
        "PL-TEACHER", ExemptionType.POLICY, "각급학교 교사",
        "예비군법 제5조, 시행령 제11조",
        frozenset({"교사", "교수", "부교수", "조교수", "각급학교교사"}),
        (DocType.EMPLOYMENT,),
        MobilizationEffect.LOSS_REPLACEMENT, EducationEffect.REDUCED,
        POLICY_REDUCED_HOURS,
    ),
    ExemptionRule(
        "PL-VOCATIONAL", ExemptionType.POLICY, "직업훈련생",
        "예비군법 제5조, 시행령 제11조",
        frozenset({"직업훈련생"}), (DocType.ENROLLMENT,),
        MobilizationEffect.LOSS_REPLACEMENT, EducationEffect.REDUCED,
        POLICY_REDUCED_HOURS, recheck_months=6,
    ),
    ExemptionRule(
        "PL-FIRE-CADET", ExemptionType.POLICY, "소방학교 간부후보생",
        "예비군법 제5조, 시행령 제11조",
        frozenset({"소방학교간부후보생", "소방간부후보생"}), (DocType.ENROLLMENT,),
        MobilizationEffect.LOSS_REPLACEMENT, EducationEffect.EXEMPT,  # 유일한 면제
    ),
    ExemptionRule(
        "PL-SECURITY", ExemptionType.POLICY, "특수경비원",
        "예비군법 제5조, 시행령 제11조",
        frozenset({"특수경비원"}), (DocType.EMPLOYMENT,),
        MobilizationEffect.LOSS_REPLACEMENT, EducationEffect.REDUCED,
        POLICY_REDUCED_HOURS,
    ),
)

# --- 후순위조정 (병역법 67조, 시행령 142조) -------------------------------
# 동원훈련 비대상이지만 **동원미지정훈련은 받습니다.**
# 보류인데 훈련을 받는 유일한 종류라, 면제로 처리하면 통째로 빠집니다.
PRIORITY_ADJ = (
    ExemptionRule(
        "PA-WARTIME", ExemptionType.PRIORITY_ADJ, "전시 동원업무 종사 공무원",
        "병역법 제67조, 시행령 제142조",
        frozenset({"전시동원업무공무원", "동원업무공무원"}), (DocType.EMPLOYMENT,),
        MobilizationEffect.EXEMPT, EducationEffect.AS_ASSIGNED,
    ),
    ExemptionRule(
        "PA-ESSENTIAL", ExemptionType.PRIORITY_ADJ, "동원업체 필수요원",
        "병역법 제67조, 시행령 제142조",
        frozenset({"동원업체필수요원", "필수요원"}), (DocType.EMPLOYMENT,),
        MobilizationEffect.EXEMPT, EducationEffect.AS_ASSIGNED,
    ),
    ExemptionRule(
        "PA-LEADER", ExemptionType.PRIORITY_ADJ, "예비군지휘자",
        "병역법 제67조, 시행령 제142조",
        frozenset({"예비군지휘관", "예비군지휘자", "예비군중대장"}), (DocType.EMPLOYMENT,),
        MobilizationEffect.EXEMPT, EducationEffect.AS_ASSIGNED,
    ),
)

EXEMPTION_RULES = STATUTORY + POLICY + PRIORITY_ADJ
RULE_BY_CODE = {r.code: r for r in EXEMPTION_RULES}


# ---------------------------------------------------------------------
# 국외 체류 / 외항선원
# ---------------------------------------------------------------------

# 1년 미만은 연기, 1년 이상은 보류
OVERSEAS_EXEMPTION_DAYS = 365
# 귀국 후 이 기간 내 재출국 시 최초 출국일부터 보류 입력(소급)
# 미출국 시 귀국 다음날부터 발생하는 훈련 부과
OVERSEAS_REGRANT_DAYS = 14
# 하선 후 이 기간 내 재승선하지 않으면 보류 해소
SEAFARER_GRACE_MONTHS = 3

MAKEUP_CUTOFF_MONTH = 10


# ---------------------------------------------------------------------
# 연기 규칙
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class PostponementRule:
    code: str
    reason: PostponeReason
    name: str
    docs: tuple[DocType, ...]
    apply_before: int      # 훈련일 기준 최소 N일 전
    retroactive: int       # 사후 신청 허용 일수 (0이면 불가)
    duration: int          # 효력 기간


# VERIFY: 기한·기간 값은 훈령 확인 필요.
# 질병·사망·재난은 사전 신청이 불가능하므로 사후 신청을 허용해야 합니다.
POSTPONEMENTS = (
    PostponementRule("PO-ILLNESS", PostponeReason.ILLNESS, "질병·심신장애",
                     (DocType.MEDICAL,), 0, 5, 90),
    PostponementRule("PO-FAMILY", PostponeReason.FAMILY, "직계존비속 위독·사망",
                     (DocType.DEATH, DocType.MEDICAL), 0, 5, 30),
    PostponementRule("PO-DISASTER", PostponeReason.DISASTER, "천재지변·재난",
                     (DocType.DISASTER,), 0, 14, 60),
    PostponementRule("PO-OVERSEAS", PostponeReason.OVERSEAS, "출국·출국 예정",
                     (DocType.EXIT_PLAN, DocType.EXIT_ENTRY), 3, 0, 180),
    PostponementRule("PO-OVERSEAS-STAY", PostponeReason.OVERSEAS_STAY, "국외 체류 1년 미만",
                     (DocType.EXIT_ENTRY,), 0, 30, 365),
    PostponementRule("PO-EXAM", PostponeReason.EXAM, "각종 시험 응시",
                     (DocType.EXAM,), 3, 0, 30),
    PostponementRule("PO-CLASS", PostponeReason.CLASS, "방송통신 출석수업",
                     (DocType.ATTENDANCE,), 3, 0, 30),
    PostponementRule("PO-COMP", PostponeReason.COMPETITION, "운동·기능경기·콩쿠르",
                     (DocType.COMPETITION,), 3, 0, 30),
    PostponementRule("PO-WEDDING", PostponeReason.WEDDING, "본인 결혼·부모 회갑",
                     (DocType.WEDDING,), 3, 0, 14),
    PostponementRule("PO-DUTY", PostponeReason.DUTY, "주요업무 수행",
                     (DocType.BUSINESS, DocType.EMPLOYMENT), 5, 0, 60),
    PostponementRule("PO-FARMING", PostponeReason.FARMING, "농어업 종사",
                     (DocType.FARMING,), 5, 0, 90),
    PostponementRule("PO-REBOARD", PostponeReason.REBOARDING_WAIT, "하선 후 재승선 대기",
                     (DocType.DISEMBARK,), 0, 90, 90),
)

BY_REASON = {r.reason: r for r in POSTPONEMENTS}

# 상습연기자 판단: 동일 병명으로 이 횟수 이상 진단서 제출 시 알람
REPEAT_POSTPONE_THRESHOLD = 2


# ---------------------------------------------------------------------
# 직업명 정규화
# ---------------------------------------------------------------------
# 자유 입력은 표기가 제각각입니다. "경찰"·"순경"이 "경찰관"으로 모이지
# 않으면 보류 대상자가 예외도 경고도 없이 조용히 빠집니다.
OCCUPATION_ALIASES = {
    "경찰": "경찰관", "경찰공무원": "경찰관", "순경": "경찰관",
    "경장": "경찰관", "경사": "경찰관", "경위": "경찰관",
    "소방": "소방관", "소방공무원": "소방관", "소방사": "소방관",
    "교정직": "교도관", "교정공무원": "교도관",
    "국방부군무원": "군무원",
    "철도공사직원": "철도종사원", "코레일": "철도종사원",
    "집배원": "우편집배원", "우체국집배원": "우편집배원",
    "초등교사": "교사", "중등교사": "교사", "교원": "교사", "대학교수": "교수",
    "재학생": "대학생", "학부생": "대학생",
    "항해사": "선원", "기관사": "선원", "선장": "선원",
    "소방간부후보": "소방간부후보생",
}


def normalize_occupation(raw: str | None) -> str | None:
    if not raw:
        return None
    v = raw.strip().replace(" ", "")
    return OCCUPATION_ALIASES.get(v, v)


def rules_for_occupation(occupation: str | None):
    """이 직업에 해당하는 보류 규칙. 보류 등록 시 검증에 씁니다."""
    occ = normalize_occupation(occupation)
    if occ is None:
        return []
    return [r for r in EXEMPTION_RULES if occ in r.occupations]
