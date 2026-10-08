import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { apiBase, authenticatedFetch } from './auth'
import { buildTrainingHourPresets, bulkHourExclusionReason, resolveTrainingHours } from './trainingHours.mjs'
import './TrainingManagementPage.css'

type Session = { id: number; day_number: number; session_date: string; credited_hours: number }
type Schedule = {
  id: number
  title: string
  training_type: string
  training_round: number
  service_year: number
  status: string
  version: number
  demo_early_save_enabled?: boolean
  demo_early_save_used?: boolean
  sessions: Session[]
}
type Person = { military_number: string; name: string; branch: string; rank: string | null; specialty: string | null; service_year: number | null }
type RosterRow = {
  education_id: number
  version: number
  military_number: string
  name: string
  training_type: string
  training_round: number
  attendance_status: string
  result_status: string
  training_hours: number
  required_hours: number | null
  remaining_hours: number | null
  notes: string | null
}
type DraftRow = RosterRow & {
  selected: boolean
  result: string
  hours: number
  override: boolean
  override_reason: string
  reversal_reason: string
}
type Worklists = {
  missing_results: { education_id: number; military_number: string; name: string; schedule_title: string; result_status: string }[]
  import_review: { education_id?: number; military_number?: string; error?: string }[]
  absences_scheduler_can_confirm: { education_id: number; military_number: string; name: string; schedule_title: string }[]
  absences_needing_approver: { education_id: number; military_number: string; name: string; schedule_title: string }[]
  late_deferral_review: { education_id: number; military_number: string; name: string; schedule_title: string }[]
  small_remainder_reviews: { education_id: number; military_number: string; name: string; schedule_title: string; next_round: number; remaining_hours: number; threshold_hours: number; reason: string }[]
}
type AssignmentTarget = {
  military_number: string
  training_round: number
  assignment_error: string | null
}
type PersonHistory = {
  military_number: string
  name: string
  years: { service_year: number; required_hours: number; counted_hours: number; remaining_hours: number; prosecution_status: string | null }[]
  records: { education_id: number; service_year: number; training_year: number | null; training_type: string; training_round: number; attendance_status: string; training_hours: number; counted_hours: number; source_kind: string; version: number; audit: { action: string; actor: string; created_at: string; before: unknown; after: unknown }[] }[]
}
type HistoryRosterPerson = Pick<RosterRow, 'military_number' | 'name'>

type TrainingTab = 'schedule' | 'assignment' | 'results'
type DayInput = { session_date: string; credited_hours: number }
type AssignmentGroup = 'all' | 'enlisted' | 'cadre' | 'rank' | 'branch' | 'rankYear' | 'specialty'
type ResultsGroup = 'all' | 'enlisted' | 'cadre' | 'branch'
const assignmentGroupOptions: { key: AssignmentGroup; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'enlisted', label: '용사' },
  { key: 'cadre', label: '간부' },
  { key: 'rank', label: '계급별' },
  { key: 'branch', label: '군별' },
  { key: 'rankYear', label: '계급/연차별' },
  { key: 'specialty', label: '주특기별' },
]
const SOLDIER_RANKS = new Set(['이병', '일병', '상병', '병장'])
const CADRE_RANKS = new Set(['하사', '중사', '상사', '원사', '소위', '중위', '대위', '소령', '중령', '대령'])
const TRAINING_SESSION_HOURS: Record<string, number[]> = {
  '동원훈련Ⅱ형': [8, 8, 8, 8],
  '동원훈련Ⅰ형': [12, 8, 8],
  '기본훈련': [8],
  '작계훈련(전·후반기)': [6, 6],
  '학생예비군': [8],
}
const API = apiBase()
const states = ['이수', '참석', '무단불참', '연기', '보류', '조기퇴소']
const ZERO_HOUR_STATES = new Set(['무단불참', '연기', '보류'])
const COUNTED_RESULT_STATES = new Set(['이수', '참석', '조기퇴소'])

function localDateAfter(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function defaultSessions(trainingType: string, firstDate = localDateAfter(7)): DayInput[] {
  const date = new Date(`${firstDate}T12:00:00`)
  const hours = TRAINING_SESSION_HOURS[trainingType] ?? [8]
  return hours.map((credited_hours, index) => {
    const sessionDate = new Date(date)
    sessionDate.setDate(sessionDate.getDate() + index)
    return {
      session_date: `${sessionDate.getFullYear()}-${String(sessionDate.getMonth() + 1).padStart(2, '0')}-${String(sessionDate.getDate()).padStart(2, '0')}`,
      credited_hours,
    }
  })
}

function sessionLabel(trainingType: string, index: number): string {
  if (trainingType === '작계훈련(전·후반기)') {
    return ['전반기', '후반기'][index] ?? `${index + 1}회차`
  }
  return `${index + 1}일차`
}

function isTypeIISchedule(trainingType: string | undefined): boolean {
  const normalized = trainingType?.replace(/\s/g, '')
  return ['동원훈련Ⅱ형', '동원훈련II형', '동원훈련2형'].includes(normalized ?? '')
}

function assignmentGroupKey(person: Person, group: AssignmentGroup): string {
  if (group === 'rank') return person.rank ?? '미등록'
  if (group === 'branch') return person.branch || '미등록'
  if (group === 'rankYear') return `${person.rank ?? '미등록'} · ${person.service_year ?? '미등록'}년차`
  if (group === 'specialty') return person.specialty ?? '미등록'
  return '전체'
}

function matchesPersonnelGroup(person: Person, group: AssignmentGroup): boolean {
  if (group === 'enlisted') return SOLDIER_RANKS.has(person.rank ?? '')
  if (group === 'cadre') return CADRE_RANKS.has(person.rank ?? '')
  return true
}

async function apiError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json() as { detail?: unknown }
    if (typeof payload.detail === 'string') return payload.detail
    if (payload.detail !== undefined) return JSON.stringify(payload.detail)
  } catch { /* Use the operation-specific fallback. */ }
  return fallback
}

function emptyWorklists(): Worklists {
  return {
    missing_results: [], import_review: [], absences_scheduler_can_confirm: [],
    absences_needing_approver: [], late_deferral_review: [], small_remainder_reviews: [],
  }
}

export default function TrainingManagementPage({ onDataChanged, focusScheduleId = null, onScheduleFocusHandled }: {
  onDataChanged?: () => void
  focusScheduleId?: number | null
  onScheduleFocusHandled?: () => void
} = {}) {
  const [tab, setTab] = useState<TrainingTab>('schedule')
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [revision, setRevision] = useState(0)
  const canWrite = true

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    Promise.all([
      authenticatedFetch(`${API}/reservists/training-schedules`, { signal: controller.signal }),
      authenticatedFetch(`${API}/persons`, { signal: controller.signal }),
    ]).then(async ([scheduleResponse, peopleResponse]) => {
      if (!scheduleResponse.ok) throw new Error(await apiError(scheduleResponse, '일정 목록을 불러오지 못했습니다.'))
      if (!peopleResponse.ok) throw new Error(await apiError(peopleResponse, '대상자 목록을 불러오지 못했습니다.'))
      const nextSchedules = await scheduleResponse.json() as Schedule[]
      const nextPeople = await peopleResponse.json() as Person[]
      setSchedules(nextSchedules)
      setPeople(nextPeople)
      setError('')
    }).catch(cause => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '교육훈련 자료를 불러오지 못했습니다.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [revision])

  const refresh = () => setRevision(value => value + 1)
  const activeTab = focusScheduleId !== null ? 'schedule' : tab

  return <main className="training-workspace">
    <header className="training-workspace-heading">
      <div><p>TRAINING OPERATIONS</p><h1>교육훈련</h1></div>
      <span>인증 사용 안 함</span>
    </header>
      <nav className="training-workspace-tabs" aria-label="교육훈련 구분">
        {([['schedule', '훈련일정'], ['assignment', '훈련부과'], ['results', '훈련결과']] as const).map(([id, label]) =>
          <button type="button" key={id} className={activeTab === id ? 'is-active' : ''} aria-current={activeTab === id ? 'page' : undefined} onClick={() => { setTab(id); setError(''); setMessage('') }}>{label}</button>)}
      </nav>
      {error && <p className="training-message is-error" role="alert">{error}</p>}
      {message && <p className="training-message" role="status">{message}</p>}
      {loading && <p className="training-message" role="status">불러오는 중…</p>}
      {activeTab === 'schedule' && <ScheduleWorkspace
        schedules={schedules}
        canWrite={!!canWrite}
        onCreated={refresh}
        focusScheduleId={focusScheduleId}
        onFocusHandled={onScheduleFocusHandled}
      />}
      {activeTab === 'assignment' && <AssignmentWorkspace schedules={schedules} people={people} canWrite={!!canWrite} onAssigned={refresh} />}
      {activeTab === 'results' && <ResultsWorkspace schedules={schedules} people={people} canWrite={!!canWrite} onSaved={() => { refresh(); onDataChanged?.() }} />}
  </main>
}

function ScheduleWorkspace({ schedules, canWrite, onCreated, focusScheduleId, onFocusHandled }: {
  schedules: Schedule[]
  canWrite: boolean
  onCreated: () => void
  focusScheduleId: number | null
  onFocusHandled?: () => void
}) {
  const [title, setTitle] = useState('')
  const [trainingType, setTrainingType] = useState('동원훈련Ⅱ형')
  const [serviceYear, setServiceYear] = useState(1)
  const [trainingRound, setTrainingRound] = useState(1)
  const [days, setDays] = useState<DayInput[]>(() => defaultSessions('동원훈련Ⅱ형'))
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [editingScheduleId, setEditingScheduleId] = useState<number | null>(null)
  const [editingDays, setEditingDays] = useState<DayInput[]>([])
  const [lifecycleError, setLifecycleError] = useState('')
  const [lifecycleMessage, setLifecycleMessage] = useState('')
  const [lifecycleBusy, setLifecycleBusy] = useState(false)
  const [editingTitle, setEditingTitle] = useState('')
  const [editingTrainingType, setEditingTrainingType] = useState('')
  const [editingServiceYear, setEditingServiceYear] = useState(1)
  const [editingTrainingRound, setEditingTrainingRound] = useState(1)

  useEffect(() => {
    if (focusScheduleId === null || !schedules.some(schedule => schedule.id === focusScheduleId)) return
    const frame = requestAnimationFrame(() => {
      document.getElementById(`training-schedule-${focusScheduleId}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      onFocusHandled?.()
    })
    return () => cancelAnimationFrame(frame)
  }, [focusScheduleId, schedules, onFocusHandled])

  const updateDay = (index: number, key: keyof DayInput, value: string | number) => {
    setDays(current => current.map((day, dayIndex) => dayIndex === index ? { ...day, [key]: value } : day))
  }
  const addDay = () => setDays(current => {
    const last = current[current.length - 1]
    const nextDate = last ? new Date(`${last.session_date}T12:00:00`) : new Date()
    nextDate.setDate(nextDate.getDate() + 1)
    const session_date = `${nextDate.getFullYear()}-${String(nextDate.getMonth() + 1).padStart(2, '0')}-${String(nextDate.getDate()).padStart(2, '0')}`
    const hours = TRAINING_SESSION_HOURS[trainingType] ?? [8]
    return [...current, { session_date, credited_hours: hours[Math.min(current.length, hours.length - 1)] }]
  })
  const editSchedule = (schedule: Schedule) => {
    setEditingScheduleId(schedule.id)
    setEditingTitle(schedule.title)
    setEditingTrainingType(schedule.training_type)
    setEditingServiceYear(schedule.service_year)
    setEditingTrainingRound(schedule.training_round)
    setEditingDays(schedule.sessions.map(({ session_date, credited_hours }) => ({ session_date, credited_hours })))
    setLifecycleError('')
    setLifecycleMessage('')
  }
  const addEditingDay = () => setEditingDays(current => {
    const last = current[current.length - 1]
    const nextDate = last ? new Date(`${last.session_date}T12:00:00`) : new Date()
    nextDate.setDate(nextDate.getDate() + 1)
    const session_date = `${nextDate.getFullYear()}-${String(nextDate.getMonth() + 1).padStart(2, '0')}-${String(nextDate.getDate()).padStart(2, '0')}`
    const hours = TRAINING_SESSION_HOURS[editingTrainingType] ?? [8]
    return [...current, { session_date, credited_hours: hours[Math.min(current.length, hours.length - 1)] }]
  })
  const saveScheduleEdits = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (editingScheduleId === null) return
    setLifecycleBusy(true)
    setLifecycleError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules/${editingScheduleId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_version: schedules.find(schedule => schedule.id === editingScheduleId)?.version,
          title: editingTitle,
          training_type: editingTrainingType,
          service_year: editingServiceYear,
          training_round: isTypeIISchedule(editingTrainingType) ? editingTrainingRound : 1,
          sessions: editingDays.map((day, index) => ({ ...day, day_number: index + 1 })),
        }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련일정을 수정하지 못했습니다.'))
      setLifecycleMessage('훈련일정을 수정했습니다.')
      setEditingScheduleId(null)
      onCreated()
    } catch (cause) { setLifecycleError(cause instanceof Error ? cause.message : '훈련일정을 수정하지 못했습니다.') }
    finally { setLifecycleBusy(false) }
  }
  const cancelSchedule = async (schedule: Schedule) => {
    if (!window.confirm(`'${schedule.title}' 일정을 취소할까요?`)) return
    setLifecycleBusy(true)
    setLifecycleError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules/${schedule.id}/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: schedule.version }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련일정을 취소하지 못했습니다.'))
      setLifecycleMessage('훈련일정을 취소했습니다.')
      if (editingScheduleId === schedule.id) setEditingScheduleId(null)
      onCreated()
    } catch (cause) { setLifecycleError(cause instanceof Error ? cause.message : '훈련일정을 취소하지 못했습니다.') }
    finally { setLifecycleBusy(false) }
  }
  const completeSchedule = async (schedule: Schedule) => {
    if (!window.confirm(`'${schedule.title}' 일정을 완료 처리할까요? 완료 후에는 연결된 훈련 결과를 수정할 수 없습니다.`)) return
    setLifecycleBusy(true)
    setLifecycleError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules/${schedule.id}/complete`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: schedule.version }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련일정을 완료하지 못했습니다.'))
      setLifecycleMessage('훈련일정을 완료 처리했습니다.')
      if (editingScheduleId === schedule.id) setEditingScheduleId(null)
      onCreated()
    } catch (cause) { setLifecycleError(cause instanceof Error ? cause.message : '훈련일정을 완료하지 못했습니다.') }
    finally { setLifecycleBusy(false) }
  }
  const deleteSchedule = async (schedule: Schedule) => {
    if (!window.confirm(`'${schedule.title}' 일정을 삭제할까요? 연결된 훈련기록이 있으면 삭제할 수 없습니다.`)) return
    setLifecycleBusy(true)
    setLifecycleError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules/${schedule.id}`, {
        method: 'DELETE', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: schedule.version }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련일정을 삭제하지 못했습니다.'))
      setLifecycleMessage('훈련일정을 삭제했습니다.')
      if (editingScheduleId === schedule.id) setEditingScheduleId(null)
      onCreated()
    } catch (cause) { setLifecycleError(cause instanceof Error ? cause.message : '훈련일정을 삭제하지 못했습니다.') }
    finally { setLifecycleBusy(false) }
  }

  const saveSchedule = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title, training_type: trainingType, service_year: serviceYear,
          training_round: isTypeIISchedule(trainingType) ? trainingRound : 1,
          sessions: days.map((day, index) => ({ ...day, day_number: index + 1 })),
        }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련일정을 저장하지 못했습니다.'))
      setTitle('')
      setFormError('')
      onCreated()
    } catch (cause) {
      setFormError(cause instanceof Error ? cause.message : '훈련일정을 저장하지 못했습니다.')
    } finally { setSaving(false) }
  }

  return <div className="training-columns">
    <section className="training-section">
      <header><h2>훈련일정 등록</h2><span>행사 1건 · 훈련일별 세션</span></header>
      {!canWrite && <p className="training-note">일정 등록은 scheduler 권한이 필요합니다.</p>}
      <form className="training-form" onSubmit={event => void saveSchedule(event)}>
        <label className="training-field training-field-wide">행사명<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={160} disabled={!canWrite || saving} /></label>
        <label className="training-field">훈련종류<select value={trainingType} onChange={event => { const value = event.target.value; setTrainingType(value); setTrainingRound(1); setDays(current => defaultSessions(value, current[0]?.session_date)) }} disabled={!canWrite || saving}><option>동원훈련Ⅱ형</option><option>동원훈련Ⅰ형</option><option>기본훈련</option><option>작계훈련(전·후반기)</option><option>학생예비군</option></select></label>
        <label className="training-field">복무연차<input type="number" min="1" max="99" value={serviceYear} onChange={event => setServiceYear(Number(event.target.value))} disabled={!canWrite || saving} /></label>
        {isTypeIISchedule(trainingType) && <label className="training-field">동원훈련Ⅱ형 차수<select value={trainingRound} onChange={event => setTrainingRound(Number(event.target.value))} disabled={!canWrite || saving}><option value={1}>1차</option><option value={2}>2차</option><option value={3}>3차</option></select></label>}
        <div className="training-days training-field-wide"><div className="training-inline-heading"><strong>세션 날짜와 인정 상한</strong><button type="button" onClick={addDay} disabled={!canWrite || days.length >= 30}>날짜 추가</button></div>
          {days.map((day, index) => { const label = sessionLabel(trainingType, index); return <div className="training-day-row" key={index}><span>{label}</span><input aria-label={`${label} 날짜`} type="date" value={day.session_date} onChange={event => updateDay(index, 'session_date', event.target.value)} disabled={!canWrite || saving} /><input aria-label={`${label} 시간 상한`} type="number" min="0" max="24" value={day.credited_hours} onChange={event => updateDay(index, 'credited_hours', Number(event.target.value))} disabled={!canWrite || saving} /><span>시간</span><button type="button" aria-label={`${label} 제거`} onClick={() => setDays(current => current.filter((_, dayIndex) => dayIndex !== index))} disabled={!canWrite || days.length <= 1}>제거</button></div> })}
        </div>
        {formError && <p className="training-message is-error training-field-wide" role="alert">{formError}</p>}
        <button className="training-primary training-field-wide" type="submit" disabled={!canWrite || saving}>{saving ? '저장 중…' : '일정 저장'}</button>
      </form>
    </section>
    <section className="training-section">
      <header><h2>등록된 일정</h2><strong>{schedules.length}건</strong></header>
      {lifecycleError && <p className="training-message is-error" role="alert">{lifecycleError}</p>}
      {lifecycleMessage && <p className="training-message" role="status">{lifecycleMessage}</p>}
      {schedules.length === 0 ? <p className="training-note">등록된 일정이 없습니다.</p> : <div className="training-table-wrap"><table><thead><tr><th>행사</th><th>훈련</th><th>연차·차수</th><th>기간</th><th>세션</th><th>상태</th><th>관리</th></tr></thead><tbody>{schedules.map(schedule => {
        const lastSessionDate = schedule.sessions.at(-1)?.session_date
        const sessionsHavePassed = lastSessionDate !== undefined && lastSessionDate < localDateAfter(0)
        const statusLabel = schedule.status === 'scheduled'
          ? '예정'
          : schedule.status === 'completed' ? '완료' : '취소'
        return <tr id={`training-schedule-${schedule.id}`} key={schedule.id} className={focusScheduleId === schedule.id ? 'training-schedule-focus' : undefined}>
          <td>{schedule.title}</td><td>{schedule.training_type}</td>
          <td>{schedule.service_year}년차{isTypeIISchedule(schedule.training_type) ? ` · ${schedule.training_round}차` : ''}</td>
          <td>{schedule.sessions[0]?.session_date} - {lastSessionDate}</td><td>{schedule.sessions.length}일</td><td>{statusLabel}</td>
          <td className="training-schedule-actions">{schedule.status === 'scheduled' && <>
            <button className="training-schedule-edit" type="button" disabled={!canWrite || lifecycleBusy} onClick={() => editSchedule(schedule)}>일정 편집</button>
            <button className="training-schedule-complete" type="button" disabled={!canWrite || lifecycleBusy || !sessionsHavePassed}
              title={sessionsHavePassed ? '모든 배정 결과가 확정되어야 완료할 수 있습니다.' : '모든 훈련 세션이 종료된 후 완료할 수 있습니다.'}
              aria-label={`${schedule.title} 일정 완료 처리`}
              onClick={() => void completeSchedule(schedule)}>완료</button>
            <button className="training-schedule-cancel" type="button" disabled={!canWrite || lifecycleBusy} onClick={() => void cancelSchedule(schedule)}>취소</button>
          </>}
            <button className="training-schedule-delete" type="button" disabled={!canWrite || lifecycleBusy} onClick={() => void deleteSchedule(schedule)}>삭제</button>
          </td>
        </tr>
      })}</tbody></table></div>}
      {editingScheduleId !== null && <form className="training-form training-schedule-editor" onSubmit={event => void saveScheduleEdits(event)}>
        <header className="training-field-wide"><h3>일정 편집</h3><button type="button" onClick={addEditingDay} disabled={!canWrite || lifecycleBusy || editingDays.length >= 30}>날짜 추가</button></header>
        <label className="training-field training-field-wide">행사명<input value={editingTitle} onChange={event => setEditingTitle(event.target.value)} required maxLength={160} disabled={lifecycleBusy} /></label>
        <label className="training-field">훈련종류<select value={editingTrainingType} onChange={event => { const value = event.target.value; setEditingTrainingType(value); setEditingTrainingRound(1); setEditingDays(current => defaultSessions(value, current[0]?.session_date)) }} disabled={lifecycleBusy}><option>동원훈련Ⅱ형</option><option>동원훈련Ⅰ형</option><option>기본훈련</option><option>작계훈련(전·후반기)</option><option>학생예비군</option></select></label>
        <label className="training-field">복무연차<input type="number" min="1" max="99" value={editingServiceYear} onChange={event => setEditingServiceYear(Number(event.target.value))} disabled={lifecycleBusy} /></label>
        {isTypeIISchedule(editingTrainingType) && <label className="training-field">동원훈련Ⅱ형 차수<select value={editingTrainingRound} onChange={event => setEditingTrainingRound(Number(event.target.value))} disabled={!canWrite || lifecycleBusy}><option value={1}>1차</option><option value={2}>2차</option><option value={3}>3차</option></select></label>}
        <div className="training-days training-field-wide"><strong>세션 날짜와 인정 상한</strong>
        {editingDays.map((day, index) => { const label = sessionLabel(editingTrainingType, index); return <div className="training-day-row" key={index}><span>{label}</span><input aria-label={`변경 ${label} 날짜`} type="date" value={day.session_date} onChange={event => setEditingDays(current => current.map((item, itemIndex) => itemIndex === index ? { ...item, session_date: event.target.value } : item))} disabled={!canWrite || lifecycleBusy} /><input aria-label={`변경 ${label} 시간 상한`} type="number" min="0" max="24" value={day.credited_hours} onChange={event => setEditingDays(current => current.map((item, itemIndex) => itemIndex === index ? { ...item, credited_hours: Number(event.target.value) } : item))} disabled={!canWrite || lifecycleBusy} /><span>시간</span><button type="button" aria-label={`변경 ${label} 제거`} onClick={() => setEditingDays(current => current.filter((_, itemIndex) => itemIndex !== index))} disabled={!canWrite || lifecycleBusy || editingDays.length <= 1}>제거</button></div> })}
        </div>
        {lifecycleError && <p className="training-message is-error training-field-wide" role="alert">{lifecycleError}</p>}
        <footer className="training-actions training-field-wide"><button type="button" onClick={() => setEditingScheduleId(null)} disabled={lifecycleBusy}>닫기</button><button className="training-primary" type="submit" disabled={!canWrite || lifecycleBusy}>{lifecycleBusy ? '저장 중…' : '수정 저장'}</button></footer>
      </form>}
    </section>
  </div>
}

function AssignmentWorkspace({ schedules, people, canWrite, onAssigned }: { schedules: Schedule[]; people: Person[]; canWrite: boolean; onAssigned: () => void }) {
  const [scheduleId, setScheduleId] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [assignedIds, setAssignedIds] = useState<Set<string>>(() => new Set())
  const [assignmentTargets, setAssignmentTargets] = useState<Map<string, AssignmentTarget>>(() => new Map())
  const [group, setGroup] = useState<AssignmentGroup>('all')
  const [groupValue, setGroupValue] = useState<string | null>(null)
  const [rosterLoading, setRosterLoading] = useState(false)
  const [review, setReview] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const activeScheduleId = scheduleId || (schedules[0] ? String(schedules[0].id) : '')
  const activeSchedule = schedules.find(schedule => String(schedule.id) === activeScheduleId)

  useEffect(() => {
    if (!activeScheduleId) {
      setAssignedIds(new Set())
      setAssignmentTargets(new Map())
      setRosterLoading(false)
      return
    }
    const controller = new AbortController()
    setRosterLoading(true)
    Promise.all([
      authenticatedFetch(`${API}/reservists/training-schedules/${activeScheduleId}/roster`, { signal: controller.signal }),
      authenticatedFetch(`${API}/reservists/training-schedules/${activeScheduleId}/assignment-candidates`, { signal: controller.signal }),
    ])
      .then(async ([rosterResponse, candidateResponse]) => {
        if (!rosterResponse.ok) throw new Error(await apiError(rosterResponse, '이미 부과된 인원을 불러오지 못했습니다.'))
        if (!candidateResponse.ok) throw new Error(await apiError(candidateResponse, '훈련종류별 대상자를 불러오지 못했습니다.'))
        return Promise.all([
          rosterResponse.json() as Promise<{ roster: RosterRow[] }>,
          candidateResponse.json() as Promise<{ military_numbers: string[]; training_targets?: AssignmentTarget[] }>,
        ])
      })
      .then(([roster, candidates]) => {
        if (controller.signal.aborted) return
        setAssignedIds(new Set(roster.roster.map(row => row.military_number)))
        const targets = candidates.training_targets ?? candidates.military_numbers.map(military_number => ({
          military_number,
          training_round: 1,
          assignment_error: null,
        }))
        setAssignmentTargets(new Map(targets.map(target => [target.military_number, target])))
      })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '이미 부과된 인원을 불러오지 못했습니다.') })
      .finally(() => { if (!controller.signal.aborted) setRosterLoading(false) })
    return () => controller.abort()
  }, [activeScheduleId])

  const cohort = people.filter(person => person.service_year === activeSchedule?.service_year
    && assignmentTargets.has(person.military_number))
  const unavailableReason = (person: Person) => assignedIds.has(person.military_number)
    ? '이미 이 일정에 부과된 인원입니다.'
    : assignmentTargets.get(person.military_number)?.assignment_error ?? null
  const assignableCount = cohort.filter(person => !unavailableReason(person)).length
  const searchFiltered = cohort.filter(person => {
    const needle = query.trim().toLocaleLowerCase()
    return !needle || person.military_number.toLocaleLowerCase().includes(needle) || person.name.toLocaleLowerCase().includes(needle)
  })
  const groupValues = group === 'all' || group === 'enlisted' || group === 'cadre'
    ? []
    : [...new Set(searchFiltered.map(person => assignmentGroupKey(person, group)))].sort((a, b) => a.localeCompare(b, 'ko'))
  const personnelFiltered = searchFiltered.filter(person => matchesPersonnelGroup(person, group))
  const visiblePeople = group === 'all' || group === 'enlisted' || group === 'cadre' || groupValue === null
    ? personnelFiltered
    : personnelFiltered.filter(person => assignmentGroupKey(person, group) === groupValue)

  const togglePerson = (militaryNumber: string) => setSelected(current => {
    const next = new Set(current)
    if (next.has(militaryNumber)) next.delete(militaryNumber)
    else next.add(militaryNumber)
    setReview(false)
    return next
  })


  const addGroup = (nextGroup: AssignmentGroup) => {
    setGroup(nextGroup)
    setGroupValue(null)
  }
  const confirmAssignments = async () => {
    setBusy(true)
    setError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules/${activeScheduleId}/roster`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_ids: [...selected] }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련부과를 저장하지 못했습니다.'))
      setAssignedIds(current => new Set([...current, ...selected]))
      setSelected(new Set())
      setReview(false)
      onAssigned()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '훈련부과를 저장하지 못했습니다.') }
    finally { setBusy(false) }
  }

  return <section className="training-section">
    <header><h2>훈련부과 대상 편성</h2><span>대상자를 지정해 훈련일정에 배정합니다.</span></header>
    <div className="training-toolbar">
      <label className="training-field">일정<select value={activeScheduleId} onChange={event => { setScheduleId(event.target.value); setAssignedIds(new Set()); setAssignmentTargets(new Map()); setRosterLoading(Boolean(event.target.value)); setSelected(new Set()); setGroup('all'); setGroupValue(null); setReview(false); setError('') }}><option value="">일정 선택</option>{schedules.map(schedule => <option key={schedule.id} value={schedule.id}>{schedule.title} · {schedule.service_year}년차{isTypeIISchedule(schedule.training_type) ? ` · ${schedule.training_round}차` : ''}</option>)}</select></label>
      <label className="training-field training-search">군번 또는 이름 검색<input value={query} onChange={event => { setQuery(event.target.value); setGroupValue(null) }} /></label>
    </div>
    {activeSchedule && <div className="training-assignment-summary"><strong>{activeSchedule.training_type} · {activeSchedule.service_year}년차{isTypeIISchedule(activeSchedule.training_type) ? ` · ${activeSchedule.training_round}차` : ''}</strong>{isTypeIISchedule(activeSchedule.training_type) && <span>선택한 차수와 대상자의 현재 차수가 일치하는 경우에만 부과할 수 있습니다.</span>}<span>훈련 대상 {cohort.length}명</span><span>목록 선택 가능 {cohort.length}명</span><span>부과 가능 {assignableCount}명</span><span>이미 부과 {assignedIds.size}명</span></div>}
    {activeScheduleId && <nav className="training-assignment-groups" aria-label="대상자 분류">
      {assignmentGroupOptions.map(option => <button key={option.key} type="button" className={group === option.key ? 'is-active' : ''} aria-pressed={group === option.key} onClick={() => addGroup(option.key)}>{option.label}</button>)}
    </nav>}
    {group !== 'all' && group !== 'enlisted' && group !== 'cadre' && <nav className="training-assignment-values" aria-label="분류 값">
      {groupValues.length === 0 ? <span>해당 분류의 인원이 없습니다.</span> : groupValues.map(value => <button key={value} type="button" className={groupValue === value ? 'is-active' : ''} aria-pressed={groupValue === value} onClick={() => setGroupValue(value)}>{value}<small>{searchFiltered.filter(person => assignmentGroupKey(person, group) === value).length}</small></button>)}
    </nav>}
    {rosterLoading && <p className="training-note" role="status">훈련종류별 대상자를 확인하는 중입니다.</p>}
    <div className="training-person-list">{visiblePeople.map(person => {
      const reason = unavailableReason(person)
      const target = assignmentTargets.get(person.military_number)
      return <label key={person.military_number} title={reason ?? undefined}>
        <input type="checkbox" checked={selected.has(person.military_number)} disabled={!canWrite || busy || rosterLoading || !activeScheduleId} onChange={() => togglePerson(person.military_number)} />
        <span className="training-military">{person.military_number}</span><strong>{person.name}</strong><small>{person.branch} · {person.rank ?? '-'} · {person.service_year ?? '-'}년차{isTypeIISchedule(activeSchedule?.training_type) && ` · ${target?.training_round ?? 1}차`}{reason && ` · ${reason}`}</small>
      </label>
    })}</div>
    {visiblePeople.length === 0 && !rosterLoading && <p className="training-note">{cohort.length === 0 ? '선택한 일정의 훈련종류와 연차에 해당하는 대상자가 없습니다.' : '검색 또는 분류 결과가 없습니다.'}</p>}
    {error && <p className="training-message is-error" role="alert">{error}</p>}
    {review && <div className="training-review-box"><strong>{selected.size}명을 일정에 부과합니다.</strong><span>확정하면 선택한 일정 차수로 훈련 기록을 생성합니다.</span></div>}
    <footer className="training-actions">{review && <button type="button" onClick={() => setReview(false)} disabled={busy}>수정</button>}{review
      ? <button className="training-primary" type="button" disabled={busy || selected.size === 0} onClick={() => void confirmAssignments()}>{busy ? '저장 중…' : '부과 확정'}</button>
      : <button className="training-primary" type="button" disabled={!canWrite || !activeScheduleId || selected.size === 0} onClick={() => setReview(true)}>부과 검토 ({selected.size})</button>}</footer>
  </section>
}

function ResultsWorkspace({ schedules, people, canWrite, onSaved }: { schedules: Schedule[]; people: Person[]; canWrite: boolean; onSaved: () => void }) {
  const [view, setView] = useState<'session' | 'person'>('session')
  const [scheduleId, setScheduleId] = useState('')
  const [resultsGroup, setResultsGroup] = useState<ResultsGroup>('all')
  const [resultsBranch, setResultsBranch] = useState<string | null>(null)
  const [roster, setRoster] = useState<DraftRow[]>([])
  const [worklists, setWorklists] = useState<Worklists>(emptyWorklists)
  const [bulkState, setBulkState] = useState('이수')
  const [customBulkHours, setCustomBulkHours] = useState(8)
  const [customBulkHoursSelected, setCustomBulkHoursSelected] = useState(false)
  const [bulkPresetDay, setBulkPresetDay] = useState<number | null>(null)
  const [reviewing, setReviewing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [batchKey, setBatchKey] = useState<string | null>(null)
  const [rosterRevision, setRosterRevision] = useState(0)
  const [historyPersonId, setHistoryPersonId] = useState('')
  const [history, setHistory] = useState<PersonHistory | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [historyRoster, setHistoryRoster] = useState<HistoryRosterPerson[]>([])
  const [historyRosterLoading, setHistoryRosterLoading] = useState(false)
  const [historyRosterError, setHistoryRosterError] = useState('')
  const selectedScheduleId = scheduleId || (schedules[0] ? String(schedules[0].id) : '')
  const selectedSchedule = schedules.find(item => String(item.id) === selectedScheduleId)
  const selectedHistoryPersonId = historyRoster.some(person => person.military_number === historyPersonId)
    ? historyPersonId
    : historyRoster[0]?.military_number ?? ''
  const hourPresets = buildTrainingHourPresets(selectedSchedule?.sessions ?? [])
  const eventHours = selectedSchedule?.sessions.reduce((total, session) => total + session.credited_hours, 0) ?? 0
  const selectedHourPreset = hourPresets.find(preset => preset.day_number === bulkPresetDay) ?? hourPresets.at(-1)
  const bulkHours = customBulkHoursSelected ? customBulkHours : selectedHourPreset?.hours ?? 0
  const bulkHoursLocked = ZERO_HOUR_STATES.has(bulkState)
    || (isTypeIISchedule(selectedSchedule?.training_type) && ['이수', '참석'].includes(bulkState))
  const bulkHoursChoice = bulkHoursLocked
    ? ZERO_HOUR_STATES.has(bulkState) ? 'zero' : 'automatic'
    : customBulkHoursSelected ? 'custom' : String(selectedHourPreset?.day_number ?? 'custom')
  const peopleByMilitaryNumber = new Map(people.map(person => [person.military_number, person]))
  const resultBranches = [...new Set(roster.map(row => peopleByMilitaryNumber.get(row.military_number)?.branch || '미등록'))]
    .sort((a, b) => a.localeCompare(b, 'ko'))
  const visibleRoster = roster.filter(row => {
    const person = peopleByMilitaryNumber.get(row.military_number)
    if ((resultsGroup === 'enlisted' || resultsGroup === 'cadre')
      && (!person || !matchesPersonnelGroup(person, resultsGroup))) return false
    if (resultsGroup === 'branch' && resultsBranch !== null
      && (person?.branch || '미등록') !== resultsBranch) return false
    return true
  })
  const changedRows = roster.filter(row => row.selected && row.result)

  useEffect(() => {
    if (view !== 'session') return
    if (!selectedSchedule) {
      setRoster([])
      return
    }
    const controller = new AbortController()
    Promise.all([
      authenticatedFetch(`${API}/reservists/training-schedules/${selectedSchedule.id}/roster`, { signal: controller.signal }),
      authenticatedFetch(`${API}/reservists/training-results/worklists`, { signal: controller.signal }),
    ]).then(async ([rosterResponse, worklistResponse]) => {
      if (!rosterResponse.ok) throw new Error(await apiError(rosterResponse, '훈련 결과 명단을 불러오지 못했습니다.'))
      if (!worklistResponse.ok) throw new Error(await apiError(worklistResponse, '결과 worklist를 불러오지 못했습니다.'))
      const rosterData = await rosterResponse.json() as { roster: RosterRow[] }
      setRoster(rosterData.roster.map(row => ({
        ...row,
        selected: row.attendance_status === 'scheduled' || row.result_status === '결과 미입력',
        result: row.attendance_status === 'scheduled' || row.result_status === '결과 미입력' ? '' : row.attendance_status,
        hours: row.training_hours,
        override: false,
        override_reason: '',
        reversal_reason: '',
      })))
      setWorklists(await worklistResponse.json() as Worklists)
      setReviewing(false)
      setBatchKey(null)
      setError('')
    }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '훈련 결과를 불러오지 못했습니다.') })
    return () => controller.abort()
  }, [view, selectedScheduleId, schedules.length, rosterRevision])

  useEffect(() => {
    if (view !== 'person') return
    if (!selectedSchedule) {
      setHistoryRoster([])
      setHistory(null)
      setHistoryRosterError('')
      setHistoryRosterLoading(false)
      return
    }
    const controller = new AbortController()
    setHistoryRoster([])
    setHistory(null)
    setHistoryPersonId('')
    setHistoryRosterLoading(true)
    setHistoryRosterError('')
    authenticatedFetch(`${API}/reservists/training-schedules/${selectedSchedule.id}/roster`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(await apiError(response, '훈련 명단을 불러오지 못했습니다.'))
        return response.json() as Promise<{ roster: RosterRow[] }>
      })
      .then(data => {
        if (!controller.signal.aborted) {
          setHistoryRoster(data.roster.map(row => ({ military_number: row.military_number, name: row.name })))
        }
      })
      .catch(cause => {
        if (!controller.signal.aborted) setHistoryRosterError(cause instanceof Error ? cause.message : '훈련 명단을 불러오지 못했습니다.')
      })
      .finally(() => { if (!controller.signal.aborted) setHistoryRosterLoading(false) })
    return () => controller.abort()
  }, [view, selectedScheduleId, rosterRevision])

  useEffect(() => {
    if (view !== 'person') return
    const personId = selectedHistoryPersonId
    if (!personId) {
      setHistory(null)
      setHistoryLoading(false)
      setHistoryError('')
      return
    }
    const controller = new AbortController()
    setHistoryLoading(true)
    setHistory(null)
    setHistoryError('')
    authenticatedFetch(`${API}/reservists/training-results/people/${encodeURIComponent(personId)}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(await apiError(response, '개인별 훈련 이력을 불러오지 못했습니다.'))
        return response.json() as Promise<PersonHistory>
      })
      .then(data => { if (!controller.signal.aborted) { setHistory(data); setHistoryError('') } })
      .catch(cause => { if (!controller.signal.aborted) setHistoryError(cause instanceof Error ? cause.message : '개인별 훈련 이력을 불러오지 못했습니다.') })
      .finally(() => { if (!controller.signal.aborted) setHistoryLoading(false) })
    return () => controller.abort()
  }, [view, selectedHistoryPersonId])

  const updateRow = (id: number, patch: Partial<DraftRow>) => {
    setRoster(current => current.map(row => row.education_id === id ? { ...row, ...patch, selected: true } : row))
    setReviewing(false)
    setBatchKey(null)
  }
  const hoursForResult = (row: DraftRow, result: string, fallbackHours: number) => {
    return resolveTrainingHours({
      isTypeII: isTypeIISchedule(selectedSchedule?.training_type),
      result,
      eventHours,
      requiredHours: row.required_hours,
      remainingHours: row.remaining_hours,
      enteredHours: fallbackHours,
    }).hours
  }
  const applyBulk = () => {
    const skipped: { name: string; reason: string }[] = []
    setRoster(current => current.map(row => {
      if (!row.selected) return row
      const resolved = resolveTrainingHours({
        isTypeII: isTypeIISchedule(selectedSchedule?.training_type),
        result: bulkState,
        eventHours,
        requiredHours: row.required_hours,
        remainingHours: row.remaining_hours,
        enteredHours: bulkHours,
      })
      const exclusion = COUNTED_RESULT_STATES.has(bulkState)
        ? bulkHourExclusionReason(resolved.hours, eventHours, row.remaining_hours)
        : null
      const belowRoundRequirement = bulkState === '이수'
        && row.required_hours !== null
        && resolved.hours < row.required_hours
      if (resolved.limitUnknown || exclusion || (COUNTED_RESULT_STATES.has(bulkState) && resolved.hours <= 0) || belowRoundRequirement) {
        const reason = resolved.limitUnknown || exclusion === 'unknown_remaining'
          ? '개인별 필요/잔여시간 확인 불가'
          : exclusion === 'event_capacity'
            ? `일정 상한 ${eventHours}시간 초과`
            : exclusion === 'annual_allowance'
              ? `연간 잔여 ${row.remaining_hours}시간 초과`
              : belowRoundRequirement
                ? `이수 필요시간 ${row.required_hours}시간 미달`
                : '인정 결과에 양수 시간이 필요'
        skipped.push({ name: row.name, reason })
        return row
      }
      return { ...row, result: bulkState, hours: resolved.hours }
    }))
    setError(skipped.length
      ? `일괄 적용에서 ${skipped.length}명을 제외했습니다: ${skipped.slice(0, 4).map(row => `${row.name}(${row.reason})`).join(', ')}${skipped.length > 4 ? ' 외' : ''}. 제외 대상은 개인별 인정시간·결과를 확인해 주세요.`
      : '')
    setReviewing(false)
    setBatchKey(null)
  }
  const toggleAll = (checked: boolean) => {
    const visibleIds = new Set(visibleRoster.map(row => row.education_id))
    setRoster(current => current.map(row => visibleIds.has(row.education_id) ? { ...row, selected: checked } : row))
  }

  const saveResults = async () => {
    setBusy(true)
    setError('')
    const idempotencyKey = batchKey ?? crypto.randomUUID()
    setBatchKey(idempotencyKey)
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-results/bulk-confirm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idempotency_key: idempotencyKey,
          source_kind: 'manual',
          entries: changedRows.map(row => ({
            education_id: row.education_id,
            expected_version: row.version,
            attendance_status: row.result,
            training_hours: row.hours,
            notes: row.notes,
                        reversal_reason: row.reversal_reason.trim() || null,
            override_allowance: row.override,
            override_reason: row.override_reason,
          })),
        }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련 결과를 저장하지 못했습니다.'))
      const responseData = await response.json() as { updated: unknown[]; warnings: { education_id: number }[] }
      setMessage(`${responseData.updated.length}건을 저장했습니다.${responseData.warnings.length ? ` 초과 허용 ${responseData.warnings.length}건을 감사 기록에 남겼습니다.` : ''}`)
      setReviewing(false)
      setBatchKey(null)
      onSaved()
      setRoster([])
      setRosterRevision(value => value + 1)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '결과 묶음 저장에 실패했습니다.') }
    finally { setBusy(false) }
  }

  const downloadCsv = async () => {
    setError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-results/export.csv`)
      if (!response.ok) throw new Error(await apiError(response, 'CSV 내보내기에 실패했습니다.'))
      const blob = await response.blob()
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = 'training-results.csv'
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'CSV 내보내기에 실패했습니다.') }
  }

  const confirmReview = () => {
    if (changedRows.length === 0) {
      setError('저장할 결과를 선택하고 상태를 지정해 주세요.')
      return
    }
    const invalid = changedRows.find(row => !states.includes(row.result)
      || (COUNTED_RESULT_STATES.has(row.result) && row.hours < 1)
      || (ZERO_HOUR_STATES.has(row.result) && row.hours !== 0)
      || (COUNTED_RESULT_STATES.has(row.result) && row.remaining_hours === null)
      || (isTypeIISchedule(selectedSchedule?.training_type)
        && COUNTED_RESULT_STATES.has(row.result) && row.required_hours === null)
      || (COUNTED_RESULT_STATES.has(row.result) && row.hours > eventHours)
      || (COUNTED_RESULT_STATES.has(row.result) && row.hours > (row.remaining_hours ?? 0)
        && (!row.override || !row.override_reason.trim()))
      || (row.result === '이수' && row.required_hours !== null && row.hours < row.required_hours)
      || (row.override && !row.override_reason.trim())
      || (row.attendance_status === '무단불참' && row.result !== '무단불참' && !row.reversal_reason.trim()))
    if (invalid) {
      if (invalid.result === '이수' && invalid.required_hours !== null && invalid.hours < invalid.required_hours) {
        setError(`이수는 개인별 필요시간 ${invalid.required_hours}시간 이상이어야 합니다. 부분 인정은 참석 또는 조기퇴소로 기록해 주세요.`)
      } else if (COUNTED_RESULT_STATES.has(invalid.result)
        && (invalid.remaining_hours === null
          || (isTypeIISchedule(selectedSchedule?.training_type) && invalid.required_hours === null))) {
        setError(`${invalid.name}의 개인별 필요시간 또는 연간 잔여시간을 확인할 수 없어 저장할 수 없습니다.`)
      } else if (COUNTED_RESULT_STATES.has(invalid.result) && invalid.hours > eventHours) {
        setError(`인정시간은 일정 상한 ${eventHours}시간을 초과할 수 없습니다.`)
      } else if (COUNTED_RESULT_STATES.has(invalid.result) && invalid.hours > (invalid.remaining_hours ?? 0)
        && (!invalid.override || !invalid.override_reason.trim())) {
        setError(`${invalid.name}의 연간 잔여 허용시간은 ${invalid.remaining_hours}시간입니다. 초과 시 허용 사유와 approver 확인이 필요합니다.`)
      } else {
        setError('결과 상태별 인정시간과 초과 허용 사유를 확인해 주세요.')
      }
      return
    }
    setError('')
    setReviewing(true)
  }

  return <div className="training-results-layout">
    <section className="training-section">
      <nav className="training-result-views" aria-label="결과 보기">
        <button type="button" className={view === 'session' ? 'is-active' : ''} onClick={() => setView('session')}>세션별</button>
        <button type="button" className={view === 'person' ? 'is-active' : ''} onClick={() => setView('person')}>개인별</button>
      </nav>
      {view === 'person' ? <>
        <div className="training-toolbar">
          <label className="training-field">훈련일정<select value={selectedScheduleId} onChange={event => {
            setScheduleId(event.target.value)
            setHistoryPersonId('')
            setError('')
            setMessage('')
          }}><option value="">일정 선택</option>{schedules.map(schedule => <option key={schedule.id} value={schedule.id}>{schedule.title} · {schedule.training_type} · {schedule.service_year}년차{isTypeIISchedule(schedule.training_type) ? ` · ${schedule.training_round}차` : ''}</option>)}</select></label>
          <label className="training-field training-history-person">대상자<select value={selectedHistoryPersonId} disabled={historyRosterLoading || historyRoster.length === 0} onChange={event => setHistoryPersonId(event.target.value)}>{historyRoster.map(person => <option key={person.military_number} value={person.military_number}>{person.military_number} · {person.name}</option>)}</select></label>
        </div>
        {!selectedSchedule && <p className="training-note">등록된 훈련일정이 없습니다.</p>}
        {historyRosterLoading && <p className="training-note">훈련 명단을 불러오는 중…</p>}
        {historyRosterError && <p className="training-message is-error" role="alert">{historyRosterError}</p>}
        {!historyRosterLoading && selectedSchedule && !historyRosterError && historyRoster.length === 0 && <p className="training-note">선택한 일정에 배정된 인원이 없습니다.</p>}
        {historyLoading && <p className="training-note">훈련 이력을 불러오는 중…</p>}
        {historyError && <p className="training-message is-error" role="alert">{historyError}</p>}
        {history && <PersonHistoryPanel key={history.military_number} history={history} />}
      </> : <>
      <header><h2>행사 결과 roster</h2><button type="button" onClick={() => void downloadCsv()}>CSV 내보내기</button></header>
      <div className="training-toolbar">
        <label className="training-field">훈련일정<select value={selectedScheduleId} onChange={event => { setScheduleId(event.target.value); setRoster([]); setResultsGroup('all'); setResultsBranch(null); setCustomBulkHoursSelected(false); setBulkPresetDay(null); setError(''); setMessage('') }}><option value="">일정 선택</option>{schedules.map(schedule => <option key={schedule.id} value={schedule.id}>{schedule.title} · {schedule.training_type} · {schedule.service_year}년차{isTypeIISchedule(schedule.training_type) ? ` · ${schedule.training_round}차` : ''}</option>)}</select></label>
      </div>
      {!canWrite && <p className="training-note">결과 입력과 확인에는 scheduler 권한이 필요합니다.</p>}
      {selectedSchedule && <div className="training-session-summary"><strong>{selectedSchedule.title}</strong><span>{selectedSchedule.service_year}년차{isTypeIISchedule(selectedSchedule.training_type) ? ' · 개인별 차수 자동' : ''} · {roster.length}명</span><span>완료 {roster.filter(row => row.result_status !== '결과 미입력' && row.attendance_status !== 'scheduled').length} · 결과 미입력 {worklists.missing_results.filter(row => row.schedule_title === selectedSchedule.title).length}</span>{selectedSchedule.demo_early_save_enabled && <span className="training-demo-save-state">DEMO 조기 저장 1회 가능</span>}{selectedSchedule.demo_early_save_used && <span className="training-demo-save-state is-used">DEMO 조기 저장 사용 완료</span>}</div>}
      {roster.length > 0 && <>
        <nav className="training-assignment-groups" aria-label="결과 명단 분류">
          {([
            { key: 'all', label: '전체' },
            { key: 'enlisted', label: '용사' },
            { key: 'cadre', label: '간부' },
            { key: 'branch', label: '군별' },
          ] as { key: ResultsGroup; label: string }[]).map(option => <button key={option.key} type="button" className={resultsGroup === option.key ? 'is-active' : ''} aria-pressed={resultsGroup === option.key} onClick={() => { setResultsGroup(option.key); setResultsBranch(null) }}>{option.label}</button>)}
        </nav>
        {resultsGroup === 'branch' && <nav className="training-assignment-values" aria-label="군별 결과 명단">
          {resultBranches.map(branch => <button key={branch} type="button" className={resultsBranch === branch ? 'is-active' : ''} aria-pressed={resultsBranch === branch} onClick={() => setResultsBranch(current => current === branch ? null : branch)}>{branch}<small>{roster.filter(row => (peopleByMilitaryNumber.get(row.military_number)?.branch || '미등록') === branch).length}</small></button>)}
        </nav>}
        <div className="training-toolbar training-bulk-toolbar">
          <label><input type="checkbox" checked={visibleRoster.length > 0 && visibleRoster.every(row => row.selected)} onChange={event => toggleAll(event.target.checked)} /> 표시된 명단 전체 선택</label>
          <label className="training-field">선택 결과<select value={bulkState} onChange={event => { setBulkState(event.target.value); setError('') }}>{states.map(state => <option key={state}>{state}</option>)}</select></label>
          <label className="training-field training-bulk-hours-field">일괄 시간
            <select aria-label="일괄 인정시간 preset" value={bulkHoursChoice} disabled={!canWrite || busy || reviewing || bulkHoursLocked} onChange={event => {
              if (event.target.value === 'custom') {
                setCustomBulkHoursSelected(true)
                return
              }
              const preset = hourPresets.find(item => String(item.day_number) === event.target.value)
              if (preset) {
                setBulkPresetDay(preset.day_number)
                setCustomBulkHoursSelected(false)
              }
            }}>
              {bulkHoursLocked && <option value={bulkHoursChoice}>{bulkHoursChoice === 'zero' ? '0시간 · 결과 상태상 시간 없음' : '대상자별 자동 적용'}</option>}
              {!bulkHoursLocked && hourPresets.map(preset => <option key={preset.day_number} value={preset.day_number}>{preset.label}</option>)}
              {!bulkHoursLocked && <option value="custom">직접 입력</option>}
            </select>
            {!bulkHoursLocked && customBulkHoursSelected && <input aria-label="직접 입력 인정시간" type="number" min={COUNTED_RESULT_STATES.has(bulkState) ? 1 : 0} max={eventHours} value={customBulkHours} onChange={event => setCustomBulkHours(Number(event.target.value))} />}
            {!bulkHoursLocked && <small className="training-hours-note">{customBulkHoursSelected ? `일정 상한 ${eventHours}시간 · 개인 잔여 허용시간 초과 행은 일괄 적용에서 제외` : selectedHourPreset?.label ?? `일정 총 인정시간 ${eventHours}시간`}</small>}
            {bulkHoursLocked && <small className="training-hours-note">{bulkHoursChoice === 'zero' ? '무단불참·연기·보류는 0시간으로 고정' : '대상자별 연간 잔여시간과 일정 상한 중 작은 값 적용'}</small>}
          </label>
          <button type="button" onClick={applyBulk} disabled={!canWrite || !roster.some(row => row.selected)}>선택 행에 적용</button>
        </div>
        {visibleRoster.length === 0 ? <p className="training-note">선택한 분류에 해당하는 명단이 없습니다.</p> : <div className="training-table-wrap"><table className="training-result-table"><thead><tr><th></th><th>군번</th><th>성명</th>{isTypeIISchedule(selectedSchedule?.training_type) && <th>차수</th>}<th>현재 결과</th><th>결과 입력</th><th>인정시간</th><th>시간 초과 허용</th><th>메모</th><th>불참 정정 사유</th></tr></thead><tbody>{visibleRoster.map(row => {
          const typeIIAuto = isTypeIISchedule(selectedSchedule?.training_type) && ['이수', '참석'].includes(row.result)
          const typeIIAutoHours = typeIIAuto ? resolveTrainingHours({
            isTypeII: true,
            result: row.result,
            eventHours,
            requiredHours: row.required_hours,
            remainingHours: row.remaining_hours,
            enteredHours: row.hours,
          }).hours : null
          const typeIIHoursWereEdited = typeIIAutoHours !== null && row.hours !== typeIIAutoHours
          const belowRoundRequirement = row.result === '이수'
            && row.required_hours !== null
            && row.hours < row.required_hours
          const overAllowance = row.remaining_hours !== null && row.hours > row.remaining_hours
          const autoLimitUnknown = typeIIAuto && (row.remaining_hours === null || row.required_hours === null)
          const hoursHint = autoLimitUnknown
            ? '개인별 Type II 필요시간 또는 연간 잔여시간 확인 불가'
            : row.remaining_hours === null
              ? '연간 잔여시간 확인 불가'
            : typeIIAuto && row.hours < eventHours
              ? `${typeIIHoursWereEdited ? `직접 입력 ${row.hours}시간 · 자동 기본값 ${typeIIAutoHours}시간` : `자동 기본값 ${row.hours}시간`} · 일정 ${eventHours}시간 · 개인별 필요 ${row.required_hours}시간 · 연간 잔여 ${row.remaining_hours}시간 · 직접 수정 가능`
              : typeIIAuto
                ? `${typeIIHoursWereEdited ? `직접 입력 ${row.hours}시간 · 자동 기본값 ${typeIIAutoHours}시간` : `자동 기본값 ${row.hours}시간`} · 필요 ${row.required_hours}시간 · 연간 잔여 ${row.remaining_hours}시간 · 직접 수정 가능`
                : belowRoundRequirement
                  ? `부분 인정 ${row.hours}/${row.required_hours}시간 · 참석 또는 조기퇴소로 기록`
                  : overAllowance
                    ? `연간 잔여 ${row.remaining_hours}시간 초과 · 사유와 approver 확인 필요`
                    : `개인별 필요 ${row.required_hours ?? '-'}시간 · 연간 잔여 ${row.remaining_hours}시간`
          const hoursHintWarning = row.remaining_hours === null || belowRoundRequirement || overAllowance
            || autoLimitUnknown
            || (typeIIAuto && row.hours < eventHours)
          return <tr key={row.education_id}>
          <td><input aria-label={`${row.name} 선택`} type="checkbox" checked={row.selected} disabled={!canWrite || reviewing || busy} onChange={event => setRoster(current => current.map(item => item.education_id === row.education_id ? { ...item, selected: event.target.checked } : item))} /></td>
          <td className="training-military">{row.military_number}</td><td>{row.name}</td>{isTypeIISchedule(selectedSchedule?.training_type) && <td>{row.training_round}차</td>}<td>{row.result_status}</td>
          <td><select aria-label={`${row.name} 결과`} value={row.result} disabled={!canWrite || reviewing || busy} onChange={event => { const result = event.target.value; updateRow(row.education_id, { result, hours: hoursForResult(row, result, row.hours) }) }}><option value="">결과 선택</option>{states.map(state => <option key={state}>{state}</option>)}</select></td>
          <td><input aria-label={`${row.name} 인정시간`} type="number" min={COUNTED_RESULT_STATES.has(row.result) ? 1 : 0} max={eventHours} value={row.hours} disabled={!canWrite || reviewing || busy || ZERO_HOUR_STATES.has(row.result)} onChange={event => updateRow(row.education_id, { hours: Number(event.target.value) })} /><small className={`training-row-hours-note${hoursHintWarning ? ' is-warning' : ''}`}>{hoursHint}</small></td>
          <td><label className="training-override"><input type="checkbox" checked={row.override} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { override: event.target.checked })} />허용</label>{row.override && <input aria-label={`${row.name} 초과 사유`} value={row.override_reason} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { override_reason: event.target.value })} />}</td>
          <td><input aria-label={`${row.name} 결과 메모`} value={row.notes ?? ''} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { notes: event.target.value })} /></td>
          <td>{row.attendance_status === '무단불참' && row.result !== '무단불참' && <input aria-label={`${row.name} 불참 정정 사유`} required value={row.reversal_reason} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { reversal_reason: event.target.value })} />}</td>
        </tr>
        })}</tbody></table></div>}
        {reviewing && <section className="training-review-box" aria-live="polite"><strong>저장 전 검토 · {changedRows.length}건</strong><span>{changedRows.map(row => `${row.name}: ${row.result} ${row.hours}시간`).join(' / ')}</span><div className="training-actions"><button type="button" disabled={busy} onClick={() => setReviewing(false)}>수정</button><button className="training-primary" type="button" disabled={!canWrite || busy} onClick={() => void saveResults()}>{busy ? '저장 중…' : '전체 결과 저장'}</button></div></section>}
        {!reviewing && <footer className="training-actions"><button className="training-primary" type="button" disabled={!canWrite || changedRows.length === 0} onClick={confirmReview}>저장 내용 검토 ({changedRows.length})</button></footer>}
      </>}
      {roster.length === 0 && selectedScheduleId && <p className="training-note">배정된 대상자가 없습니다.</p>}
      {error && <p className="training-message is-error" role="alert">{error}</p>}
      {message && <p className="training-message" role="status">{message}</p>}
      </>}
    </section>
    <WorklistPanel worklists={worklists} />
  </div>
}

function PersonHistoryPanel({ history }: { history: PersonHistory }) {
  const [roundFilter, setRoundFilter] = useState<'all' | '1' | '2' | '3'>('all')
  const hasTypeIIRoundRecords = history.records.some(record => isTypeIISchedule(record.training_type))
  const visibleRecords = roundFilter === 'all'
    ? history.records
    : history.records.filter(record => isTypeIISchedule(record.training_type) && String(record.training_round) === roundFilter)

  return <div className="training-history-panel">
    <header><h2>{history.name}</h2><span className="training-military">{history.military_number}</span></header>
    <div className="training-table-wrap"><table><thead><tr><th>연차</th><th>필요</th><th>인정</th><th>잔여</th><th>고발</th></tr></thead><tbody>{history.years.map(year => <tr key={year.service_year}><td>{year.service_year}년차</td><td>{year.required_hours}시간</td><td>{year.counted_hours}시간</td><td>{year.remaining_hours}시간</td><td>{year.prosecution_status ?? '-'}</td></tr>)}</tbody></table></div>
    <div className="training-toolbar">
      <h3>차수별 결과와 감사 이력</h3>
      {hasTypeIIRoundRecords && <label className="training-field">동원훈련Ⅱ형 차수<select value={roundFilter} onChange={event => setRoundFilter(event.target.value as typeof roundFilter)}><option value="all">전체 차수</option><option value="1">1차</option><option value="2">2차</option><option value="3">3차</option></select></label>}
    </div>
    {visibleRecords.length === 0 ? <p className="training-note">선택한 차수의 훈련 이력이 없습니다.</p> : <div className="training-table-wrap"><table><thead><tr><th>연차</th><th>종류</th><th>차수</th><th>결과</th><th>인정시간</th><th>감사</th></tr></thead><tbody>{visibleRecords.map(record => <tr key={record.education_id}>
      <td>{record.service_year}년차</td><td>{record.training_type}</td><td>{isTypeIISchedule(record.training_type) ? `${record.training_round}차` : '—'}</td><td>{record.attendance_status}</td><td>{record.counted_hours}/{record.training_hours}시간</td>
      <td><details><summary>{record.audit.length}건</summary>{record.audit.map((audit, index) => <p key={`${audit.created_at}-${index}`}>{audit.created_at} · {audit.actor} · {audit.action}</p>)}</details></td>
    </tr>)}</tbody></table></div>}
  </div>
}

function WorklistPanel({ worklists }: { worklists: Worklists }) {
  return <aside className="training-section training-worklists">
    <header><h2>결과 worklists</h2><span>{worklists.missing_results.length + worklists.absences_scheduler_can_confirm.length + worklists.absences_needing_approver.length + worklists.small_remainder_reviews.length}건</span></header>
    <h3>결과 미입력 · grace 기간 경과</h3>
    {worklists.missing_results.length ? <ul>{worklists.missing_results.map(row => <li key={row.education_id}><strong>{row.name}</strong><span>{row.military_number} · {row.schedule_title}</span></li>)}</ul> : <p>현재 대기 항목이 없습니다.</p>}
    <h3>무단불참 확인 · scheduler</h3>
    {worklists.absences_scheduler_can_confirm.length ? <ul>{worklists.absences_scheduler_can_confirm.map(row => <li key={row.education_id}><strong>{row.name}</strong><span>{row.military_number} · {row.schedule_title}</span></li>)}</ul> : <p>현재 대기 항목이 없습니다.</p>}
    <h3>무단불참 확인 · approver</h3>
    {worklists.absences_needing_approver.length ? <ul>{worklists.absences_needing_approver.map(row => <li key={row.education_id}><strong>{row.name}</strong><span>{row.military_number} · {row.schedule_title}</span></li>)}</ul> : <p>현재 대기 항목이 없습니다.</p>}
    <h3>가져오기 검토</h3>
    <p>부대 export 형식과 익명 샘플 확인 후 연결합니다.</p>
    <h3>승인된 연기/보류 검토</h3>
    {worklists.late_deferral_review.length ? <ul>{worklists.late_deferral_review.map(row => <li key={row.education_id}><strong>{row.name}</strong><span>{row.military_number} · {row.schedule_title}</span></li>)}</ul> : <p>현재 대기 항목이 없습니다.</p>}
    <h3>소액 잔여시간 · approver 검토</h3>
    {worklists.small_remainder_reviews.length ? <ul>{worklists.small_remainder_reviews.map(row => <li key={row.education_id}><strong>{row.name} · {row.next_round}차 부과 대기</strong><span>{row.military_number} · {row.schedule_title} · {row.reason}</span></li>)}</ul> : <p>현재 대기 항목이 없습니다.</p>}
  </aside>
}
