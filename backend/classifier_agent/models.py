"""
도메인 모델.
"""
from __future__ import annotations

import enum
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------
# 군번  YY-NNNNNNNN
# ---------------------------------------------------------------------

SERVICE_NUMBER_RE = re.compile(r"^\d{2}-\d{8}$")


def validate_service_number(value: str) -> str:
    v = str(value).strip()
    if not SERVICE_NUMBER_RE.match(v):
        raise ValueError(f"군번 형식 오류: {value!r} (예: 26-76014241)")
    return v


def add_months(d: date, months: int) -> date:
    """개월 단위 덧셈. '하선 후 3개월' 처럼 일수로 환산하면 안 되는 규정용.

    90일로 계산하면 달 길이에 따라 며칠씩 어긋납니다.
    """
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


# ---------------------------------------------------------------------
# 군별 / 훈련
# ---------------------------------------------------------------------


class Branch(str, enum.Enum):
    ARMY = "육군"
    NAVY = "해군"
    AIR_FORCE = "공군"
    MARINE = "해병"

    @property
    def is_army_style(self) -> bool:
        """동미참훈련 형태. 육군은 출퇴근 4일, 해·공군은 2박3일 입영.

        VERIFY: 해병은 해군에 준하는 것으로 두었습니다. 확인 필요.
        """
        return self == Branch.ARMY


class TrainingType(str, enum.Enum):
    NONE = "훈련없음"
    MOBILIZATION = "동원훈련"          # 2박3일 입영
    NON_DESIGNATED = "동미참훈련"       # 육군 출퇴근 4일 / 해공군 2박3일
    BASIC_OPS = "기본훈련+작계훈련"      # 기본 8h + 작계 12h
    MAKEUP = "보충훈련"
    CARRYOVER = "미이수 이월훈련"


class MobilizationEffect(str, enum.Enum):
    """보류가 동원훈련에 미치는 영향."""

    ASSIGNED = "동원대상"
    EXEMPT = "동원 비대상"
    LOSS_REPLACEMENT = "손실보충부대 지정"


class EducationEffect(str, enum.Enum):
    """보류가 예비군교육훈련에 미치는 영향."""

    AS_ASSIGNED = "정상부과"
    REDUCED = "일부부과"   # hours 로 시간 지정
    EXEMPT = "면제"


# ---------------------------------------------------------------------
# 보류
# ---------------------------------------------------------------------


class ExemptionType(str, enum.Enum):
    STATUTORY = "법규보류"       # 예비군법 5조, 시행령 11조
    POLICY = "방침보류"          # 예비군법 5조, 시행령 11조
    PRIORITY_ADJ = "후순위조정"   # 병역법 67조, 시행령 142조


class ReleaseReason(str, enum.Enum):
    """보류 해소 사유."""

    LEAVE = "휴학"
    GRADUATION = "졸업"
    RESIGNATION = "면직·퇴직"
    PERIOD_END = "기간만료"
    LOST_QUALIFICATION = "자격상실"
    RETURN_HOME = "귀국"          # 국외체류 보류
    NO_REBOARDING = "미승선"       # 외항선원
    OTHER = "기타"


class TrainingOutcome(str, enum.Enum):
    SCHEDULED = "예정"
    COMPLETED = "이수"
    PARTIAL = "일부이수"
    ABSENT = "불참"
    POSTPONED = "연기"       # 연기 승인 — 미이수분 이월
    EXEMPTED = "보류면제"     # 보류로 면제 — 이월 안 됨

    @property
    def carries_over(self) -> bool:
        """미이수분이 다음 해로 넘어가는가.

        보류면제는 넘어가지 않습니다 — 안 받아도 되는 훈련이기 때문입니다.
        연기·불참·일부이수는 넘어갑니다.
        """
        return self in (TrainingOutcome.PARTIAL, TrainingOutcome.ABSENT,
                        TrainingOutcome.POSTPONED)


@dataclass
class TrainingRecord:
    """연도별 훈련 부과·이수 기록.

    이게 없으면 이월이 허구가 됩니다 — '부과됐는데 못 받은 시간'을
    계산할 근거가 사라지고, 이월 시간을 사람이 손으로 넣어야 합니다.
    """

    year: int
    training_type: "TrainingType"
    assigned_hours: float
    completed_hours: float = 0.0
    outcome: TrainingOutcome = TrainingOutcome.SCHEDULED
    completed_date: date | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.assigned_hours < 0 or self.completed_hours < 0:
            raise ValueError("훈련 시간은 음수일 수 없습니다.")

    @property
    def balance(self) -> float:
        """부과 대비 잔액. 양수면 미이수, 음수면 초과이수(크레딧).
        """
        diff = self.assigned_hours - self.completed_hours
        if diff < 0:
            return diff
        return diff if self.outcome.carries_over else 0.0

    @property
    def unfinished(self) -> float:
        """미이수 시간 (표시용). 초과이수는 0으로 봅니다."""
        return max(0.0, self.balance)

    @property
    def credit(self) -> float:
        """초과이수 시간 (표시용)."""
        return max(0.0, -self.balance)


@dataclass
class Exemption:

    rule_code: str
    start: date
    end: date | None = None                     # 종료 예정일, None = 무기한
    released: date | None = None                # 실제 해소일
    release_reason: ReleaseReason | None = None
    recheck_due: date | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise ValueError(f"보류 종료일({self.end})이 시작일({self.start})보다 빠릅니다.")
        if self.released is not None and self.released < self.start:
            raise ValueError(f"보류 해소일({self.released})이 시작일({self.start})보다 빠릅니다.")
        if self.released is not None and self.release_reason is None:
            raise ValueError("보류를 해소하려면 해소 사유가 필요합니다.")

    def is_active_on(self, as_of: date) -> bool:
        if self.start > as_of:
            return False
        if self.released is not None and self.released <= as_of:
            return False
        if self.end is not None and self.end < as_of:
            return False          # 기간만료 — 계산으로 해소
        return True

    def expired_on(self, as_of: date) -> bool:
        return self.end is not None and self.end < as_of and self.released is None

    def needs_recheck(self, as_of: date) -> bool:
        return (
            self.is_active_on(as_of)
            and self.recheck_due is not None
            and self.recheck_due < as_of
        )


# ---------------------------------------------------------------------
# 서류
# ---------------------------------------------------------------------


class DocStatus(str, enum.Enum):
    PENDING = "검토대기"
    ACCEPTED = "승인"
    REJECTED = "반려"
    NEEDS_VERIFY = "확인요청"


class DocType(str, enum.Enum):
    EMPLOYMENT = "재직증명서"
    ENROLLMENT = "재학증명서"
    EXIT_ENTRY = "출귀국자명부"
    BOARDING = "승선증명서"
    DISEMBARK = "하선증명서"
    MEDICAL = "진단서"
    DEATH = "사망진단서"
    DISASTER = "재해증명서"
    EXIT_PLAN = "출국예정확인서"
    EXAM = "수험표"
    ATTENDANCE = "출석수업통지서"
    COMPETITION = "대회참가확인서"
    WEDDING = "청첩장"
    BUSINESS = "업무확인서"
    FARMING = "농어업경영체등록확인서"
    PERSONAL_STATEMENT = "개인사유서"


# VERIFY: 서류별 유효기간. 훈령 확인 필요.
VALIDITY_DAYS = {
    DocType.EMPLOYMENT: 90, DocType.ENROLLMENT: 90, DocType.EXIT_ENTRY: 90,
    DocType.BOARDING: 180, DocType.DISEMBARK: 180, DocType.MEDICAL: 30,
    DocType.DEATH: 90, DocType.DISASTER: 90, DocType.EXIT_PLAN: 60,
    DocType.EXAM: 30, DocType.ATTENDANCE: 60, DocType.COMPETITION: 60,
    DocType.WEDDING: 60, DocType.BUSINESS: 90, DocType.FARMING: 365,
    DocType.PERSONAL_STATEMENT: 90,
}


class RejectReason(str, enum.Enum):
    ILLEGIBLE = "판독불가"
    WRONG_TYPE = "서류종류 불일치"
    EXPIRED = "유효기간 만료"
    MISMATCH = "인적사항 불일치"
    INCOMPLETE = "기재사항 누락"
    BAD_ISSUER = "발급기관 부적합"
    NO_SEAL = "도장 누락"
    WRONG_PURPOSE = "용도 부적합"
    DUPLICATE = "중복 제출"
    OTHER = "기타"


REJECT_GUIDE: dict[RejectReason, tuple[bool, str]] = {
    RejectReason.ILLEGIBLE: (True, "서류가 흐리거나 일부가 잘렸습니다. 전체가 선명하게 보이도록 다시 제출해 주세요."),
    RejectReason.WRONG_TYPE: (True, "요구된 서류와 다른 종류가 제출되었습니다. 안내된 서류를 확인 후 다시 제출해 주세요."),
    RejectReason.EXPIRED: (True, "서류의 유효기간이 지났습니다. 최근 발급분으로 다시 제출해 주세요."),
    RejectReason.MISMATCH: (True, "서류의 성명·군번이 등록 정보와 일치하지 않습니다. 확인 후 다시 제출해 주세요."),
    RejectReason.INCOMPLETE: (True, "발급일자 등 필수 기재사항이 누락되었습니다. 보완 후 다시 제출해 주세요."),
    RejectReason.BAD_ISSUER: (True, "발급기관이 적합하지 않습니다. 해당 기관에서 발급받아 다시 제출해 주세요."),
    RejectReason.NO_SEAL: (True, "의사·병원 직인 또는 원본대조필이 누락되었습니다. 날인 후 다시 제출해 주세요."),
    RejectReason.WRONG_PURPOSE: (True, "용도가 예비군 제출용으로 기재되지 않았습니다. 용도를 명시해 다시 발급받아 주세요."),
    RejectReason.DUPLICATE: (False, "이미 제출된 서류입니다. 추가 제출이 필요하지 않습니다."),
    RejectReason.OTHER: (True, ""),
}


class VerifyReason(str, enum.Enum):
    FORGERY = "위변조 의심"
    ISSUER_CHECK = "발급기관 확인 필요"
    DUPLICATE_FILE = "동일 파일 중복 제출"
    OTHER = "기타"


@dataclass
class MedicalCheck:
    """진단서 확인 항목. 실무자 체크리스트.

    주신 확인사항 그대로입니다. 하나라도 빠지면 반려 사유가 됩니다.
    """

    serial_no: bool = False        # 연번
    diagnosis_date: bool = False   # 진단일
    issue_date: bool = False       # 발행일
    seal_doctor: bool = False      # 의사 도장
    seal_hospital: bool = False    # 병원 도장
    seal_verified: bool = False    # 원본대조필
    purpose_ok: bool = False       # 용도 (예비군중대 제출용 등)

    def missing(self) -> list[str]:
        labels = {
            "serial_no": "연번", "diagnosis_date": "진단일", "issue_date": "발행일",
            "seal_doctor": "의사 도장", "seal_hospital": "병원 도장",
            "seal_verified": "원본대조필", "purpose_ok": "용도",
        }
        return [v for k, v in labels.items() if not getattr(self, k)]

    @property
    def complete(self) -> bool:
        return not self.missing()


@dataclass
class ReviewEvent:
    """검토 이력 한 줄. 재검토해도 이전 기록이 덮이지 않습니다."""

    at: datetime
    actor: str
    action: str          # ACCEPT / REJECT / VERIFY / REOPEN
    detail: str = ""


@dataclass
class Document:
    doc_type: DocType
    issued_date: date
    valid_until: date | None = None
    status: DocStatus = DocStatus.PENDING
    file_path: str = ""
    file_name: str = ""
    verify_number: str = ""
    # 진단서 전용
    medical: MedicalCheck | None = None
    diagnosis_hash: str = ""
    # 검토 결과
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    reject_reason: RejectReason | None = None
    reject_note: str = ""
    verify_reason: VerifyReason | None = None
    verify_note: str = ""
    history: list[ReviewEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.valid_until is not None and self.valid_until < self.issued_date:
            raise ValueError(
                f"서류 유효기한({self.valid_until})이 발급일({self.issued_date})보다 빠릅니다.")

    def expiry(self) -> date:
        if self.valid_until:
            return self.valid_until
        return self.issued_date + timedelta(days=VALIDITY_DAYS.get(self.doc_type, 90))

    def is_valid_on(self, as_of: date) -> bool:
        return (
            self.status == DocStatus.ACCEPTED
            and self.issued_date <= as_of <= self.expiry()
        )

    @property
    def guide_message(self) -> str:
        if self.reject_reason is None:
            return ""
        if self.reject_reason == RejectReason.OTHER:
            return self.reject_note
        return REJECT_GUIDE[self.reject_reason][1]


def accept(doc: Document, reviewer: str, *, at: datetime | None = None,
           doc_type: DocType | None = None, issued_date: date | None = None) -> Document:
    if doc_type is not None:
        doc.doc_type = doc_type
    if issued_date is not None:
        doc.issued_date = issued_date
    doc.status = DocStatus.ACCEPTED
    doc.reviewer = reviewer
    doc.reviewed_at = at or datetime.now()
    doc.reject_reason = None
    doc.reject_note = ""
    doc.verify_reason = None
    doc.verify_note = ""
    doc.history.append(ReviewEvent(doc.reviewed_at, reviewer, "ACCEPT",
                                   f"{doc.doc_type.value} 발급 {doc.issued_date}"))
    return doc


def reject(doc: Document, reviewer: str, reason: RejectReason, *,
           note: str = "", at: datetime | None = None) -> Document:
    if not isinstance(reason, RejectReason):
        raise ValueError(f"반려 사유는 RejectReason 중에서 골라야 합니다: {reason!r}")
    if reason == RejectReason.OTHER and not note.strip():
        raise ValueError("'기타' 반려는 설명을 적어야 합니다.")
    doc.status = DocStatus.REJECTED
    doc.reviewer = reviewer
    doc.reviewed_at = at or datetime.now()
    doc.reject_reason = reason
    doc.reject_note = note
    doc.history.append(ReviewEvent(doc.reviewed_at, reviewer, "REJECT",
                                   reason.value + (f" | {note}" if note else "")))
    return doc


def needs_verify(doc: Document, reviewer: str, reason: VerifyReason, *,
                 note: str = "", at: datetime | None = None) -> Document:
    if not isinstance(reason, VerifyReason):
        raise ValueError(f"확인요청 사유는 VerifyReason 중에서 골라야 합니다: {reason!r}")
    if reason == VerifyReason.OTHER and not note.strip():
        raise ValueError("'기타' 확인요청은 설명을 적어야 합니다.")
    doc.status = DocStatus.NEEDS_VERIFY
    doc.reviewer = reviewer
    doc.reviewed_at = at or datetime.now()
    doc.verify_reason = reason
    doc.verify_note = note
    doc.history.append(ReviewEvent(doc.reviewed_at, reviewer, "VERIFY",
                                   reason.value + (f" | {note}" if note else "")))
    return doc


def set_diagnosis(doc: Document, diagnosis: str) -> Document:
    """병명을 해시로만 저장합니다.

    상습연기 판단에 필요한 것은 '같은 병명인가'뿐입니다. 원문을 들고
    있을 이유가 없고, 들고 있으면 유출 시 피해가 커집니다.
    """
    norm = diagnosis.strip().replace(" ", "")
    doc.diagnosis_hash = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16] if norm else ""
    return doc


# ---------------------------------------------------------------------
# 연기
# ---------------------------------------------------------------------


class PostponeReason(str, enum.Enum):
    ILLNESS = "질병_심신장애"
    FAMILY = "직계존비속_위독_사망"
    DISASTER = "천재지변_재난"
    OVERSEAS = "출국_예정"
    OVERSEAS_STAY = "국외체류_1년미만"
    EXAM = "각종시험_응시"
    CLASS = "방송통신_출석수업"
    COMPETITION = "운동경기_기능경기_콩쿠르"
    WEDDING = "본인결혼_부모회갑"
    DUTY = "주요업무_수행"
    FARMING = "농어업_종사"
    REBOARDING_WAIT = "하선후_재승선대기"


@dataclass
class Postponement:
    reason: PostponeReason
    submitted: date
    documents: list[Document] = field(default_factory=list)
    approved: bool = False           # 중대장 결재
    approver: str = ""
    period_start: date | None = None
    period_end: date | None = None
    year: int | None = None          # 어느 해 훈련을 미뤘는지

    def diagnosis_keys(self) -> list[str]:
        return [d.diagnosis_hash for d in self.documents if d.diagnosis_hash]


# ---------------------------------------------------------------------
# 국외 / 승선
# ---------------------------------------------------------------------


@dataclass
class Trip:
    departure: date
    return_date: date | None = None


@dataclass
class Seafarer:
    onboard: bool
    disembark_date: date | None = None


# ---------------------------------------------------------------------
# 예비군
# ---------------------------------------------------------------------


@dataclass
class Person:
    person_id: str
    name: str
    discharge_year: int                      # 전역 연도 → 연차 계산
    branch: Branch = Branch.ARMY
    occupation: str | None = None
    mobilization_designated: bool = False    # 동원지정 여부
    # 이수 기록 이전의 미이수분(개시 잔액). 기록이 있으면 그 위에 더해집니다.
    carryover_hours: float = 0.0

    training_records: list[TrainingRecord] = field(default_factory=list)
    exemptions: list[Exemption] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    postponements: list[Postponement] = field(default_factory=list)
    trips: list[Trip] = field(default_factory=list)
    seafarer: Seafarer | None = None

    unverified: set[str] = field(default_factory=set)
    note: str = ""

    def __post_init__(self) -> None:
        self.person_id = validate_service_number(self.person_id)

    def resource_year(self, as_of: date) -> int:
        """연차. 전역 당해가 0년차, 다음 해부터 1년차."""
        return max(0, as_of.year - self.discharge_year)

    def carryover_as_of(self, year: int) -> float:
        """해당 연도 시작 시점의 이월 시간.

        저장하지 않고 이수 기록에서 계산합니다. 저장하면 갱신을 누가
        언제 하는지가 문제가 되고, 과거 시점 재조회도 불가능해집니다.
        """
        return self.carryover_hours + sum(
            r.balance for r in self.training_records if r.year < year)

    def record_for(self, year: int) -> TrainingRecord | None:
        return next((r for r in self.training_records if r.year == year), None)

    def overlapping_exemptions(self) -> list[tuple[Exemption, Exemption]]:
        """같은 규칙의 보류가 기간이 겹치는 쌍. 등록 시 검사용."""
        out = []
        items = sorted(self.exemptions, key=lambda e: e.start)
        for i, a in enumerate(items):
            a_end = a.released or a.end or date(9999, 12, 31)
            for b in items[i + 1:]:
                if b.rule_code != a.rule_code:
                    continue
                if b.start <= a_end:
                    out.append((a, b))
        return out

    def active_exemption(self, as_of: date) -> Exemption | None:
        live = [e for e in self.exemptions if e.is_active_on(as_of)]
        return live[0] if live else None

    def valid_doc(self, doc_type: DocType, as_of: date) -> Document | None:
        ok = [d for d in self.documents if d.doc_type == doc_type and d.is_valid_on(as_of)]
        return max(ok, key=lambda d: d.expiry()) if ok else None

    def docs_of(self, doc_type: DocType) -> list[Document]:
        return [d for d in self.documents if d.doc_type == doc_type]


# ---------------------------------------------------------------------
# 판정 결과
# ---------------------------------------------------------------------


@dataclass
class Assessment:
    """이 사람이 해당 연도에 받아야 할 훈련.

    보류/연기는 최종 답이 아니라 이 계산의 입력값입니다. 라벨만 내놓으면
    "교사인데 8시간은 받아야 한다"를 표현할 수 없습니다.
    """

    person_id: str
    name: str
    year: int
    resource_year: int

    # 보류 적용 전
    base_training: TrainingType = TrainingType.NONE
    base_hours: float = 0.0

    # 보류 적용 후
    exemption_type: ExemptionType | None = None
    exemption_rule: str | None = None
    mobilization: MobilizationEffect = MobilizationEffect.ASSIGNED
    training: TrainingType = TrainingType.NONE
    hours: float = 0.0

    carryover: float = 0.0
    postponed: bool = False
    # 연기분이 당해 연도 보충훈련으로 재편성된 시간
    makeup_hours: float = 0.0

    reasons: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        """실제로 받아야 할 시간. 크레딧이 남아도 음수가 되지는 않습니다."""
        return max(0.0, self.hours + self.makeup_hours + self.carryover)

    @property
    def label(self) -> str:
        """한 줄 요약용."""
        if self.postponed:
            return "연기"
        if self.exemption_type:
            return self.exemption_type.value
        return "일반"
