import './TrainingHoursBar.css'

export type TrainingHoursSummary = {
  required_hours: number
  counted_hours: number
  credited_hours: number
  recognized_hours: number
  carryover_hours: number
  unmet_required_hours: number
  remaining_hours: number
  training_status: string
  needs_review_reason?: string | null
  latest_round?: number | null
  latest_status?: string | null
  latest_schedule_id?: number | null
  over_limit?: boolean
  is_incomplete?: boolean
}

type Props = {
  summary: TrainingHoursSummary
  size: 'compact' | 'full'
  statusLabel?: string
  onActivate?: () => void
}

const hoursText = (hours: number) => `${hours.toLocaleString('ko-KR')}시간`
const needsReview = (summary: TrainingHoursSummary) => summary.training_status === 'NEEDS_REVIEW'
const reviewReason = (summary: TrainingHoursSummary) =>
  summary.needs_review_reason || '훈련 기록 검토 필요'

function accessibleSummary(summary: TrainingHoursSummary) {
  if (needsReview(summary)) return `훈련시간 검토 필요: ${reviewReason(summary)}`
  if (summary.required_hours === 0) {
    return summary.carryover_hours > 0
      ? `의무 없음, 이월 ${hoursText(summary.carryover_hours)}, 잔여 ${hoursText(summary.remaining_hours)}`
      : '의무 없음'
  }
  return `${hoursText(summary.required_hours)} 중 ${hoursText(summary.recognized_hours)} 인정, 잔여 ${hoursText(summary.remaining_hours)}, 이월 ${hoursText(summary.carryover_hours)}`
}

function VisualBar({ summary, size }: { summary: TrainingHoursSummary; size: Props['size'] }) {
  const denominator = summary.required_hours + summary.carryover_hours
  const scale = denominator > 0 ? denominator : Math.max(summary.recognized_hours, summary.remaining_hours, 1)
  const segments = [
    ['counted', summary.counted_hours],
    ['credited', summary.credited_hours],
    ['carryover', summary.carryover_hours],
    ['remaining', summary.unmet_required_hours],
  ] as const
  const ariaLabel = accessibleSummary(summary)
  return <div
    className={`training-hours-track training-hours-track--${size}${needsReview(summary) ? ' is-review' : ''}${summary.over_limit ? ' is-over-limit' : ''}`}
    role="img"
    aria-label={ariaLabel}
  >
    {needsReview(summary) ? <span className="training-hours-review-fill" /> : <>
      {segments.map(([kind, hours]) => hours > 0 && <span
        key={kind}
        className={`training-hours-segment training-hours-segment--${kind}`}
        style={{ width: `${hours / scale * 100}%` }}
      />)}
      {summary.over_limit && <span className="training-hours-overflow" aria-hidden="true">초과</span>}
    </>}
  </div>
}

function StatusChip({ summary, statusLabel }: Pick<Props, 'summary' | 'statusLabel'>) {
  const label = statusLabel || summary.training_status
  const className = `training-hours-status${summary.training_status === 'NEEDS_REVIEW' ? ' is-review' : ''}${summary.training_status === '훈련 미이수' ? ' is-incomplete' : ''}`
  return <span className={className}>{label}</span>
}

export default function TrainingHoursBar({ summary, size, statusLabel, onActivate }: Props) {
  const showLabel = !needsReview(summary)
  const numericLabel = summary.required_hours === 0
    ? summary.carryover_hours > 0
      ? `의무 없음 · 이월 ${hoursText(summary.carryover_hours)} · 잔여 ${hoursText(summary.remaining_hours)}`
      : '의무 없음'
    : `${summary.recognized_hours}/${summary.required_hours}시간 · 잔여${summary.remaining_hours}시간`
  const detail = needsReview(summary)
    ? reviewReason(summary)
    : size === 'compact'
      ? `이수 ${summary.counted_hours} · 보류 ${summary.credited_hours} · 이월 ${summary.carryover_hours}`
      : `${summary.counted_hours > 0 ? `이수/참석 ${hoursText(summary.counted_hours)}` : '이수/참석 0시간'} · 보류 ${hoursText(summary.credited_hours)} · 이월 ${hoursText(summary.carryover_hours)}`
  const content = <>
    <VisualBar summary={summary} size={size} />
    <span className={`training-hours-copy${needsReview(summary) ? ' is-review' : ''}`}>
      <strong>{showLabel ? numericLabel : 'NEEDS_REVIEW'}</strong>
      <small>{detail}</small>
    </span>
    {size === 'compact' && <StatusChip summary={summary} statusLabel={statusLabel} />}
    {size === 'full' && summary.over_limit && <span className="training-hours-over-limit-label">승인 초과</span>}
  </>

  return onActivate
    ? <button
        type="button"
        className={`training-hours-bar training-hours-bar--${size} is-action`}
        aria-label={`${accessibleSummary(summary)}${statusLabel ? `, 상태 ${statusLabel}` : ''}`}
        onClick={event => { event.stopPropagation(); onActivate() }}
      >{content}</button>
    : <div className={`training-hours-bar training-hours-bar--${size}`}>{content}</div>
}

export function TrainingStatusChip({ summary, statusLabel }: Pick<Props, 'summary' | 'statusLabel'>) {
  return <StatusChip summary={summary} statusLabel={statusLabel} />
}
