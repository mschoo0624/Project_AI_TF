import type { CSSProperties } from 'react'
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
  const completion = summary.required_hours > 0
    ? Math.min(1, Math.max(0, summary.recognized_hours / summary.required_hours))
    : 1
  const progressPercent = summary.required_hours > 0 ? completion * 100 : null
  const showProgressScale = size === 'full' && progressPercent !== null && !needsReview(summary)
  const progressHue = completion * 120
  const segments = [
    ['counted', summary.counted_hours],
    ['credited', summary.credited_hours],
    ['carryover', summary.carryover_hours],
    ['remaining', summary.unmet_required_hours],
  ] as const
  const ariaLabel = `${accessibleSummary(summary)}${progressPercent === null ? '' : `, 달성률 ${progressPercent.toFixed(1)}%`}`
  const track = <div
    className={`training-hours-track training-hours-track--${size}${needsReview(summary) ? ' is-review' : ''}${summary.training_status === '훈련 미이수' ? ' is-incomplete' : ''}${summary.over_limit ? ' is-over-limit' : ''}${showProgressScale ? ' is-progress-scale' : ''}`}
    style={{
      '--training-progress-hue': `${progressHue}deg`,
      ...(progressPercent === null ? {} : { '--training-progress-percent': `${progressPercent}%` }),
    } as CSSProperties}
    role="img"
    aria-label={ariaLabel}
  >
    {needsReview(summary) ? <span className="training-hours-review-fill" /> : showProgressScale
      ? <span className="training-hours-progress-marker" aria-hidden="true" />
      : <>
        {segments.map(([kind, hours]) => hours > 0 && <span
          key={kind}
          className={`training-hours-segment training-hours-segment--${kind}`}
          style={{ width: `${hours / scale * 100}%` }}
        />)}
        {summary.over_limit && <span className="training-hours-overflow" aria-hidden="true">초과</span>}
      </>}
  </div>
  const visual = showProgressScale
    ? <div className={`training-hours-scale${progressPercent === 0 ? ' is-start' : ''}${progressPercent === 100 ? ' is-end' : ''}`}>
      {track}
      <span className="training-hours-percent" style={{ left: `${progressPercent}%` }}>{progressPercent.toFixed(1)}%</span>
    </div>
    : track
  return visual
}

/**
 * Current-year bar (올해): recognized hours out of this year's required hours only.
 * The cumulative bar (VisualBar) scales to required + carry-over, so a person with
 * 28/28 this year and 56 carried over looks 1/3 full there. This bar answers
 * "did they finish THIS year?" on its own scale.
 */
function YearBar({ summary }: { summary: TrainingHoursSummary }) {
  const required = summary.required_hours
  const recognized = Math.min(required, Math.max(0, summary.recognized_hours))
  const completion = required > 0 ? recognized / required : 0
  const percent = completion * 100
  return <div
    className={`training-hours-track training-hours-track--year${completion >= 1 ? ' is-complete' : ''}`}
    style={{ '--training-progress-hue': `${completion * 120}deg` } as CSSProperties}
    role="img"
    aria-label={`올해 ${hoursText(required)} 중 ${hoursText(recognized)} 인정, 달성률 ${percent.toFixed(1)}%`}
  >
    <span className="training-hours-year-fill" style={{ width: `${percent}%` }} />
  </div>
}

/**
 * Cumulative bar (누적): the combined carry-over (이월) from all previous years.
 * Current-year completed hours are deliberately left out (the 올해 bar shows them).
 * The whole bar is the carried-over total, so it is filled completely; the exact
 * amount is the number next to it.
 */
function CarryBar({ summary }: { summary: TrainingHoursSummary }) {
  const carry = Math.max(0, summary.carryover_hours)
  return <div
    className="training-hours-track training-hours-track--compact"
    role="img"
    aria-label={`누적 이월 ${hoursText(carry)}`}
  >
    <span className="training-hours-segment training-hours-segment--carryover" style={{ width: '100%' }} />
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

  // Compact (roster table):
  //  - carry-over > 0  -> two bars: 올해 (this year) + 누적 (cumulative incl. carry-over)
  //  - carry-over = 0  -> only the 올해 bar (nothing cumulative to show)
  //  - no obligation this year / NEEDS_REVIEW -> the original single bar
  const hasYearBar = size === 'compact' && summary.required_hours > 0 && !needsReview(summary)
  const hasCumulativeBar = hasYearBar && summary.carryover_hours > 0
  const visual = hasCumulativeBar
    ? <div className="training-hours-bars">
      <div className="training-hours-bar-row">
        <span className="training-hours-bar-label">올해</span>
        <YearBar summary={summary} />
        <span className="training-hours-bar-value">{Math.min(summary.recognized_hours, summary.required_hours)}/{summary.required_hours}h</span>
      </div>
      <div className="training-hours-bar-row">
        <span className="training-hours-bar-label">누적</span>
        <CarryBar summary={summary} />
        <span className="training-hours-bar-value">{summary.carryover_hours}h</span>
      </div>
    </div>
    : hasYearBar
      ? <YearBar summary={summary} />
      : <VisualBar summary={summary} size={size} />

  const content = <>
    {visual}
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