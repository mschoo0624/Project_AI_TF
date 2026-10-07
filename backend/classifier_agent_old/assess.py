"""판정 메인 엔진.
  올해 받아야 할 훈련과 시간
    1. 기본 훈련은 얼마인지 계산
    2. 보류(면제) 대상인지 확인
    3. 연기 대상인지 확인
    4. 이월시간이 남아 있는지 반영
    5. 최종 결과 객체를 만들어 반환
"""
from __future__ import annotations

from datetime import date, timedelta

from models import (
    Assessment,
    TrainingOutcome,
    TrainingRecord,
    ExemptionType,
    DocStatus,
    DocType,
    EducationEffect,
    Exemption,
    ExemptionType,
    MobilizationEffect,
    Person,
    PostponeReason,
    TrainingType,
    add_months,
)
from rules import (
    BY_REASON,
    OVERSEAS_EXEMPTION_DAYS,
    OVERSEAS_REGRANT_DAYS,
    REPEAT_POSTPONE_THRESHOLD,
    MAKEUP_CUTOFF_MONTH,
    RULE_BY_CODE,
    SEAFARER_GRACE_MONTHS,
    base_training,
    normalize_occupation,
)

# ---------------------------------------------------------------------
# 국외 체류
# ---------------------------------------------------------------------
def overseas_status(person: Person, as_of: date):
    """(상태, 기준일, 일수) 또는 None.

    상태: 'exempt' 1년 이상 체류 → 보류
          'postpone' 1년 미만 체류 → 연기
          'released' 귀국 → 해소
    """
    trips = sorted(person.trips, key=lambda t: t.departure)
    if not trips:
        return None

    chain = [trips[0]]
    for t in trips[1:]:
        prev = chain[-1]
        if prev.return_date is not None and 0 <= (t.departure - prev.return_date).days <= OVERSEAS_REGRANT_DAYS:
            chain.append(t)
        else:
            chain = [t]          # 끊김 — 새 체류

    effective_start = chain[0].departure
    last = chain[-1]
    abroad = last.return_date is None or last.return_date > as_of

    if abroad:
        days = (as_of - effective_start).days
        kind = "exempt" if days >= OVERSEAS_EXEMPTION_DAYS else "postpone"
        return kind, effective_start, days

    # 귀국 완료 — 귀국 당일 해소, 다음날부터 훈련 부과
    return "released", last.return_date, (as_of - last.return_date).days


def seafarer_status(person: Person, as_of: date):
    """(상태, 기한) 또는 None.

    승선 중이면 보류. 하선 후 3개월 이내면 재승선 대기(연기).
    3개월 경과 미승선이면 보류 해소.
    """
    rec = person.seafarer
    if rec is None:
        return None
    if rec.onboard:
        return "exempt", None
    if rec.disembark_date is None:
        return None
    deadline = add_months(rec.disembark_date, SEAFARER_GRACE_MONTHS)
    return ("postpone" if as_of <= deadline else "released"), deadline


# ---------------------------------------------------------------------
# 보류 확인
# ---------------------------------------------------------------------


def check_exemption_docs(person: Person, rule, as_of: date) -> list[str]:
    """보류 근거 서류 점검. 문제가 있어도 **자동 해소하지 않습니다.**

    서류 갱신이 늦었다고 멀쩡한 경찰관을 훈련 대상으로 만들면 안 됩니다.
    대신 알람으로 띄워 실무자가 확인하게 합니다.
    """
    problems = []
    for dt in rule.required_docs:
        if person.valid_doc(dt, as_of):
            continue
        all_docs = person.docs_of(dt)
        if not all_docs:
            problems.append(f"{dt.value} 미제출")
        elif any(d.status == DocStatus.PENDING for d in all_docs):
            problems.append(f"{dt.value} 검토 대기")
        elif any(d.status == DocStatus.NEEDS_VERIFY for d in all_docs):
            problems.append(f"{dt.value} 확인요청 중")
        elif any(d.status == DocStatus.REJECTED for d in all_docs):
            problems.append(f"{dt.value} 반려됨")
        else:
            newest = max(all_docs, key=lambda d: d.expiry())
            problems.append(f"{dt.value} 유효기간 만료(~{newest.expiry()})")
    return problems


# 보류 판정
def resolve_exemption(person: Person, as_of: date, training_date: date):
    """적용할 보류 1건을 찾습니다. (Exemption, rule, reasons, alerts)
    """
    reasons: list[str] = []
    alerts: list[str] = []

    for a_, b_ in person.overlapping_exemptions():
        alerts.append(
            f"보류 기록 중복 — {a_.rule_code} {a_.start} 과 {b_.start} 기간 겹침")

    # 1) 등록된 보류
    # 우선순위: 법규 > 방침 > 후순위조정 
    def _priority(e):
        rule = RULE_BY_CODE.get(e.rule_code)
        order = {ExemptionType.STATUTORY: 0, ExemptionType.POLICY: 1,
                 ExemptionType.PRIORITY_ADJ: 2}
        return (order.get(rule.kind, 9) if rule else 9, e.start)

    for ex in sorted(person.exemptions, key=_priority):
        rule = RULE_BY_CODE.get(ex.rule_code)
        if rule is None:
            alerts.append(f"미등록 규칙코드: {ex.rule_code}")
            continue
        if ex.is_active_on(as_of):
            if not ex.is_active_on(training_date):
                reasons.append(
                    f"{rule.kind.value} {ex.rule_code}: 훈련일({training_date}) 이전 해소 "
                    f"— 해당 훈련은 부과")
                alerts.append(
                    f"보류가 훈련일 전 종료 ({ex.end or ex.released}) — 훈련 부과 대상")
                continue
            reasons.append(f"{rule.kind.value} 적용: {rule.name} ({ex.start}~{ex.end or '무기한'})")
            problems = check_exemption_docs(person, rule, as_of)
            if problems:
                alerts.append("보류 근거 서류 확인 필요 — " + ", ".join(problems))
            if ex.needs_recheck(as_of):
                alerts.append(f"자격 재확인 기한 경과 ({ex.recheck_due}) — 휴학·졸업·퇴직 여부 확인")
            return ex, rule, reasons, alerts
        if ex.expired_on(as_of):
            reasons.append(f"보류 기간 만료로 해소 ({ex.end})")
        elif ex.released is not None and ex.released <= as_of:
            why = ex.release_reason.value if ex.release_reason else "사유 미상"
            reasons.append(f"보류 해소 ({ex.released}, {why})")

    # 2) 국외 체류 — 기록이 없어도 이력으로 판정
    ov = overseas_status(person, as_of)
    if ov:
        kind, ref, days = ov
        if kind == "exempt":
            rule = RULE_BY_CODE["ST-OVERSEAS"]
            reasons.append(f"국외 체류 {days}일 (보류 시작 {ref}, 최초 출국일 소급)")
            problems = check_exemption_docs(person, rule, as_of)
            if problems:
                alerts.append("국외체류 보류 근거 확인 필요 — " + ", ".join(problems)
                              + " (서류 보완 전까지 연기 처리)")
            else:
                ex = Exemption("ST-OVERSEAS", start=ref,
                               recheck_due=add_months(as_of, rule.recheck_months))
                alerts.append("국외체류 보류 미등록 — 보류원서 근거로 등록 필요")
                return ex, rule, reasons, alerts
        elif kind == "postpone":
            reasons.append(f"국외 체류 {days}일 — 1년 미만이므로 연기 대상")
        else:
            reasons.append(f"귀국 {ref} — 보류 해소, 다음날부터 훈련 부과")
            if days <= OVERSEAS_REGRANT_DAYS:
                alerts.append(
                    f"귀국 후 {days}일 — {OVERSEAS_REGRANT_DAYS}일 이내 재출국 시 "
                    f"최초 출국일로 소급 보류 처리 필요")

    # 3) 외항선원
    sf = seafarer_status(person, as_of)
    if sf:
        kind, deadline = sf
        if kind == "exempt":
            rule = RULE_BY_CODE["ST-SEAFARER"]
            reasons.append("승선 중")
            problems = check_exemption_docs(person, rule, as_of)
            if problems:
                alerts.append("승선 보류 근거 확인 필요 — " + ", ".join(problems))
            else:
                ex = Exemption("ST-SEAFARER", start=as_of,
                               recheck_due=add_months(as_of, rule.recheck_months))
                return ex, rule, reasons, alerts
        elif kind == "postpone":
            reasons.append(f"하선 후 재승선 대기 (기한 {deadline})")
            alerts.append(f"{deadline}까지 미승선 시 보류 해소")
        else:
            reasons.append(f"하선 후 3개월 경과 미승선 ({deadline}) — 보류 해소")

    return None, None, reasons, alerts


# ---------------------------------------------------------------------
# 연기
# ---------------------------------------------------------------------


def check_postponement(person: Person, as_of: date, training_date: date):
    """(연기여부, reasons, alerts)"""
    reasons: list[str] = []
    alerts: list[str] = []

    keys: dict[str, int] = {}
    for req in person.postponements:
        for k in req.diagnosis_keys():
            keys[k] = keys.get(k, 0) + 1
    for c in keys.values():
        if c >= REPEAT_POSTPONE_THRESHOLD:
            alerts.append(f"상습연기 의심 — 동일 병명 진단서 {c}회 제출")

    # 국외 체류 1년 미만 / 하선 대기는 서류 없이도 연기
    ov = overseas_status(person, as_of)
    if ov and ov[0] in ("postpone", "exempt"):
        return True, [], alerts
    sf = seafarer_status(person, as_of)
    if sf and sf[0] == "postpone":
        return True, [f"하선 후 재승선 대기 (기한 {sf[1]}) — 연기"], alerts

    for req in person.postponements:
        rule = BY_REASON.get(req.reason)
        if rule is None:
            reasons.append(f"미등록 연기사유: {req.reason}")
            continue
        reasons.append(f"연기 신청: {rule.name}")

        if not req.approved:
            reasons.append("중대장 결재 미승인")
            continue

        deadline = training_date - timedelta(days=rule.apply_before)
        if req.submitted <= deadline:
            reasons.append(f"기한 내 신청 ({req.submitted})")
        elif rule.retroactive and req.submitted <= training_date + timedelta(days=rule.retroactive):
            reasons.append(f"사후 신청 인정 ({req.submitted})")
        else:
            reasons.append(f"신청 기한 초과 (기한 {deadline}, 신청 {req.submitted})")
            continue

        # 구비서류는 기준일이 아니라 **훈련일** 기준으로 봅니다.
        valid = [d for d in req.documents
                 if d.doc_type in rule.docs and d.is_valid_on(training_date)]
        if not valid:
            submitted = [d for d in req.documents if d.doc_type in rule.docs]
            if not submitted:
                reasons.append("구비서류 미제출 (필요: " + "/".join(t.value for t in rule.docs) + ")")
            elif any(d.status == DocStatus.PENDING for d in submitted):
                reasons.append("구비서류 검토 대기")
            elif any(d.status == DocStatus.NEEDS_VERIFY for d in submitted):
                reasons.append("구비서류 확인요청 중")
            else:
                reasons.append("구비서류 무효 (반려 또는 유효기간 만료)")
            continue
        reasons.append("/".join(d.doc_type.value for d in valid) + " 승인·유효")

        # 진단서 체크리스트
        for d in valid:
            if d.doc_type == DocType.MEDICAL and d.medical and not d.medical.complete:
                alerts.append("진단서 확인항목 누락 — " + ", ".join(d.medical.missing()))

        if req.period_start is None and req.period_end is None:
            reasons.append(f"기간 미기재 — 훈련일 기준 적용")
        else:
            start = req.period_start or req.submitted
            end = req.period_end or (start + timedelta(days=rule.duration))
            if not (start <= training_date <= end):
                reasons.append(f"효력기간({start}~{end})이 훈련일 {training_date}을 포함하지 않음")
                continue
            reasons.append(f"연기 효력기간 {start}~{end}")

        return True, reasons, alerts

    return False, reasons, alerts


# ---------------------------------------------------------------------
# 최종 판정
# ---------------------------------------------------------------------


def assess(person: Person, as_of: date, training_date: date) -> Assessment:
    ry = person.resource_year(as_of)
    base_type, base_hours = base_training(ry, person.mobilization_designated, person.branch)

    a = Assessment(
        person_id=person.person_id, name=person.name,
        year=as_of.year, resource_year=ry,
        base_training=base_type, base_hours=base_hours,
        training=base_type, hours=base_hours,
        carryover=person.carryover_as_of(as_of.year),
        mobilization=(MobilizationEffect.ASSIGNED if person.mobilization_designated
                      else MobilizationEffect.EXEMPT),
    )
    a.reasons.append(f"{ry}년차 — {base_type.value}" + (f" {base_hours:g}시간" if base_hours else ""))

    # 미확인 자료 알람은 0년차 조기 반환 전에 붙여야 합니다.
    labels = {"trips": "출입국 자료", "documents": "제출 서류",
              "seafarer": "승선 기록", "exemptions": "보류 기록"}
    for key in sorted(person.unverified):
        a.alerts.append(f"{labels.get(key, key)} 미확인 — 판정 불완전")

    if ry == 0:
        a.reasons.append("전역 당해 — 편성만, 훈련 없음")
        return a

    # --- 보류 ---
    ex, rule, ex_reasons, ex_alerts = resolve_exemption(person, as_of, training_date)
    a.reasons += ex_reasons
    a.alerts += ex_alerts

    if ex is not None and rule is not None:
        a.exemption_type = rule.kind
        a.exemption_rule = rule.code
        a.mobilization = rule.mobilization

        if rule.education == EducationEffect.EXEMPT:
            a.training = TrainingType.NONE
            a.hours = 0.0
            a.reasons.append(f"{rule.kind.value} — 교육훈련 면제")
        elif rule.education == EducationEffect.REDUCED:
            # 기본 부과를 상한으로 둡니다. 보류는 부과를 '줄이는' 것이지
            # 없던 훈련을 만들어내면 안 됩니다 — 7~8년차는 신규 훈련이
            # 없으므로 방침보류라도 0시간이어야 합니다.
            capped = min(rule.education_hours, base_hours)
            if capped <= 0:
                a.training = TrainingType.NONE if base_hours <= 0 else base_type
                a.hours = 0.0
                a.reasons.append(f"{rule.kind.value} — 부과 대상 훈련 없음")
            else:
                a.training = TrainingType.BASIC_OPS
                a.hours = capped
                a.reasons.append(f"{rule.kind.value} — 교육훈련 {capped:g}시간 부과")
        else:
            # 후순위조정: 동원 비대상이지만 동원미지정훈련은 받습니다.
            # 면제로 처리하면 이 사람들이 통째로 빠집니다.
            a.training, a.hours = base_training(ry, False, person.branch)
            a.reasons.append(
                f"{rule.kind.value} — 동원 비대상, {a.training.value} {a.hours:g}시간 부과")

        if rule.mobilization == MobilizationEffect.LOSS_REPLACEMENT:
            a.reasons.append("동원훈련: 손실보충부대 지정")

    # --- 연기 ---

    postponed, po_reasons, po_alerts = check_postponement(person, as_of, training_date)
    a.reasons += po_reasons
    a.alerts += po_alerts
    if postponed and a.hours > 0:
        a.postponed = True
        moved = a.hours
        a.hours = 0.0
        if training_date.month < MAKEUP_CUTOFF_MONTH:
            a.makeup_hours = moved
            a.reasons.append(f"연기 — 당해 연도 보충훈련 {moved:g}시간으로 재편성")
        else:
            a.carryover += moved
            a.reasons.append(f"연기 — 재편성 기한 경과, {moved:g}시간 이월")
    elif postponed:
        a.reasons.append("연기 사유 있으나 부과 훈련이 없어 해당 없음")

    # --- 이월 ---
    if ry > 8 and a.carryover:
        a.alerts.append(f"8년차 경과({ry}년차)인데 미이수 {a.carryover:g}시간 남음 — 처리 확인 필요")
    elif ry >= 7:
        a.reasons.append(f"7~8년차 — 신규 훈련 없음, 미이수 {a.carryover:g}시간만 이수")
    elif a.carryover:
        a.reasons.append(f"전년도까지 미이수 {a.carryover:g}시간 있음")

    return a


def assess_all(people: list[Person], as_of: date, training_date: date) -> list[Assessment]:
    return [assess(p, as_of, training_date) for p in people]


def record_assessment(person: Person, a: Assessment) -> TrainingRecord:
    """판정 결과를 이수 기록으로 남깁니다.

    이걸 호출해야 다음 해 이월이 자동으로 계산됩니다. 호출하지 않으면
    carryover 를 사람이 손으로 넣어야 하고, 그건 사실상 가짜 데이터입니다.
    실제 이수 여부는 나중에 complete_training() 으로 갱신합니다.
    """
    if a.exemption_type and a.hours == 0 and a.makeup_hours == 0:
        outcome = TrainingOutcome.EXEMPTED
    elif a.postponed:
        outcome = TrainingOutcome.POSTPONED
    else:
        outcome = TrainingOutcome.SCHEDULED

    rec = person.record_for(a.year)
    assigned = a.hours + a.makeup_hours
    if rec is None:
        rec = TrainingRecord(a.year, a.training, assigned, 0.0, outcome)
        person.training_records.append(rec)
    else:
        rec.training_type = a.training
        rec.assigned_hours = assigned
        rec.outcome = outcome
    return rec


def complete_training(person: Person, year: int, hours: float,
                      on: date | None = None) -> TrainingRecord:
    """실제 이수 시간을 기록합니다."""
    rec = person.record_for(year)
    if rec is None:
        raise ValueError(f"{year}년 훈련 기록이 없습니다. record_assessment() 를 먼저 호출하십시오.")
    rec.completed_hours = hours   # 초과 이수 허용 — 다음 해 크레딧이 됩니다
    rec.completed_date = on
    rec.outcome = (TrainingOutcome.COMPLETED if hours >= rec.assigned_hours
                   else TrainingOutcome.PARTIAL)
    return rec
