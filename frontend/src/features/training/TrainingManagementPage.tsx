import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { apiBase, authenticatedFetch } from './auth'
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
  sessions: Session[]
}
type Person = { military_number: string; name: string; branch: string; rank: string | null; service_year: number | null }
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
}
type PersonHistory = {
  military_number: string
  name: string
  years: { service_year: number; required_hours: number; counted_hours: number; remaining_hours: number; prosecution_status: string | null }[]
  records: { education_id: number; service_year: number; training_year: number | null; training_type: string; training_round: number; attendance_status: string; training_hours: number; counted_hours: number; source_kind: string; version: number; audit: { action: string; actor: string; created_at: string; before: unknown; after: unknown }[] }[]
}

type TrainingTab = 'schedule' | 'assignment' | 'results'
type DayInput = { session_date: string; credited_hours: number }
const API = apiBase()
const states = ['이수', '참석', '무단불참', '연기', '보류', '조기퇴소']

function localDateAfter(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
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
    absences_needing_approver: [], late_deferral_review: [],
  }
}

export default function TrainingManagementPage({ onDataChanged }: { onDataChanged?: () => void } = {}) {
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

  return <main className="training-workspace">
    <header className="training-workspace-heading">
      <div><p>TRAINING OPERATIONS</p><h1>교육훈련</h1></div>
      <span>인증 사용 안 함</span>
    </header>
      <nav className="training-workspace-tabs" aria-label="교육훈련 구분">
        {([['schedule', '훈련일정'], ['assignment', '훈련부과'], ['results', '훈련결과']] as const).map(([id, label]) =>
          <button type="button" key={id} className={tab === id ? 'is-active' : ''} aria-current={tab === id ? 'page' : undefined} onClick={() => { setTab(id); setError(''); setMessage('') }}>{label}</button>)}
      </nav>
      {error && <p className="training-message is-error" role="alert">{error}</p>}
      {message && <p className="training-message" role="status">{message}</p>}
      {loading && <p className="training-message" role="status">불러오는 중…</p>}
      {tab === 'schedule' && <ScheduleWorkspace schedules={schedules} canWrite={!!canWrite} onCreated={refresh} />}
      {tab === 'assignment' && <AssignmentWorkspace schedules={schedules} people={people} canWrite={!!canWrite} onAssigned={refresh} />}
      {tab === 'results' && <ResultsWorkspace schedules={schedules} people={people} canWrite={!!canWrite} onSaved={() => { refresh(); onDataChanged?.() }} />}
  </main>
}

function ScheduleWorkspace({ schedules, canWrite, onCreated }: { schedules: Schedule[]; canWrite: boolean; onCreated: () => void }) {
  const [title, setTitle] = useState('')
  const [trainingType, setTrainingType] = useState('동원훈련Ⅱ형')
  const [serviceYear, setServiceYear] = useState(1)
  const [round, setRound] = useState(1)
  const [days, setDays] = useState<DayInput[]>(() => Array.from({ length: 4 }, (_, index) => ({ session_date: localDateAfter(7 + index), credited_hours: 8 })))
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [editingScheduleId, setEditingScheduleId] = useState<number | null>(null)
  const [editingDays, setEditingDays] = useState<DayInput[]>([])
  const [lifecycleError, setLifecycleError] = useState('')
  const [lifecycleMessage, setLifecycleMessage] = useState('')
  const [lifecycleBusy, setLifecycleBusy] = useState(false)

  const updateDay = (index: number, key: keyof DayInput, value: string | number) => {
    setDays(current => current.map((day, dayIndex) => dayIndex === index ? { ...day, [key]: value } : day))
  }
  const addDay = () => setDays(current => {
    const last = current[current.length - 1]
    const nextDate = last ? new Date(`${last.session_date}T12:00:00`) : new Date()
    nextDate.setDate(nextDate.getDate() + 1)
    const session_date = `${nextDate.getFullYear()}-${String(nextDate.getMonth() + 1).padStart(2, '0')}-${String(nextDate.getDate()).padStart(2, '0')}`
    return [...current, { session_date, credited_hours: 8 }]
  })
  const editSchedule = (schedule: Schedule) => {
    setEditingScheduleId(schedule.id)
    setEditingDays(schedule.sessions.map(({ session_date, credited_hours }) => ({ session_date, credited_hours })))
    setLifecycleError('')
    setLifecycleMessage('')
  }
  const addEditingDay = () => setEditingDays(current => {
    const last = current[current.length - 1]
    const nextDate = last ? new Date(`${last.session_date}T12:00:00`) : new Date()
    nextDate.setDate(nextDate.getDate() + 1)
    const session_date = `${nextDate.getFullYear()}-${String(nextDate.getMonth() + 1).padStart(2, '0')}-${String(nextDate.getDate()).padStart(2, '0')}`
    return [...current, { session_date, credited_hours: 8 }]
  })
  const moveSchedule = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (editingScheduleId === null) return
    setLifecycleBusy(true)
    setLifecycleError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules/${editingScheduleId}/move`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_version: schedules.find(schedule => schedule.id === editingScheduleId)?.version,
          sessions: editingDays.map((day, index) => ({ ...day, day_number: index + 1 })),
        }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련일정을 변경하지 못했습니다.'))
      setLifecycleMessage('훈련일정과 미확정 roster 날짜를 변경했습니다.')
      setEditingScheduleId(null)
      onCreated()
    } catch (cause) { setLifecycleError(cause instanceof Error ? cause.message : '훈련일정을 변경하지 못했습니다.') }
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

  const saveSchedule = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title, training_type: trainingType, service_year: serviceYear, training_round: round,
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
        <label className="training-field">훈련종류<select value={trainingType} onChange={event => setTrainingType(event.target.value)} disabled={!canWrite || saving}><option>동원훈련Ⅱ형</option><option>동원훈련Ⅰ형</option><option>기본훈련</option><option>작계훈련(전·후반기)</option><option>학생예비군</option></select></label>
        <label className="training-field">복무연차<input type="number" min="1" max="99" value={serviceYear} onChange={event => setServiceYear(Number(event.target.value))} disabled={!canWrite || saving} /></label>
        <label className="training-field">차수<select value={round} onChange={event => setRound(Number(event.target.value))} disabled={!canWrite || saving}><option value={1}>1차</option><option value={2}>2차</option><option value={3}>3차</option></select></label>
        <div className="training-days training-field-wide"><div className="training-inline-heading"><strong>세션 날짜와 인정 상한</strong><button type="button" onClick={addDay} disabled={!canWrite || days.length >= 30}>날짜 추가</button></div>
          {days.map((day, index) => <div className="training-day-row" key={index}><span>{index + 1}일차</span><input aria-label={`${index + 1}일차 날짜`} type="date" value={day.session_date} onChange={event => updateDay(index, 'session_date', event.target.value)} disabled={!canWrite || saving} /><input aria-label={`${index + 1}일차 시간 상한`} type="number" min="0" max="24" value={day.credited_hours} onChange={event => updateDay(index, 'credited_hours', Number(event.target.value))} disabled={!canWrite || saving} /><span>시간</span><button type="button" aria-label={`${index + 1}일차 제거`} onClick={() => setDays(current => current.filter((_, dayIndex) => dayIndex !== index))} disabled={!canWrite || days.length <= 1}>제거</button></div>)}
        </div>
        {formError && <p className="training-message is-error training-field-wide" role="alert">{formError}</p>}
        <button className="training-primary training-field-wide" type="submit" disabled={!canWrite || saving}>{saving ? '저장 중…' : '일정 저장'}</button>
      </form>
    </section>
    <section className="training-section">
      <header><h2>등록된 일정</h2><strong>{schedules.length}건</strong></header>
      {lifecycleError && <p className="training-message is-error" role="alert">{lifecycleError}</p>}
      {lifecycleMessage && <p className="training-message" role="status">{lifecycleMessage}</p>}
      {schedules.length === 0 ? <p className="training-note">등록된 일정이 없습니다.</p> : <div className="training-table-wrap"><table><thead><tr><th>행사</th><th>훈련</th><th>연차·차수</th><th>기간</th><th>세션</th><th>상태</th><th>관리</th></tr></thead><tbody>{schedules.map(schedule => <tr key={schedule.id}><td>{schedule.title}</td><td>{schedule.training_type}</td><td>{schedule.service_year}년차 · {schedule.training_round}차</td><td>{schedule.sessions[0]?.session_date} - {schedule.sessions.at(-1)?.session_date}</td><td>{schedule.sessions.length}일</td><td>{schedule.status === 'scheduled' ? '예정' : '취소'}</td><td className="training-schedule-actions">{schedule.status === 'scheduled' && <><button type="button" disabled={!canWrite || lifecycleBusy} onClick={() => editSchedule(schedule)}>일정 변경</button><button type="button" disabled={!canWrite || lifecycleBusy} onClick={() => void cancelSchedule(schedule)}>취소</button></>}</td></tr>)}</tbody></table></div>}
      {editingScheduleId !== null && <form className="training-schedule-editor" onSubmit={event => void moveSchedule(event)}>
        <header><h3>일정 변경</h3><button type="button" onClick={addEditingDay} disabled={!canWrite || lifecycleBusy || editingDays.length >= 30}>날짜 추가</button></header>
        {editingDays.map((day, index) => <div className="training-day-row" key={index}><span>{index + 1}일차</span><input aria-label={`변경 ${index + 1}일차 날짜`} type="date" value={day.session_date} onChange={event => setEditingDays(current => current.map((item, itemIndex) => itemIndex === index ? { ...item, session_date: event.target.value } : item))} disabled={!canWrite || lifecycleBusy} /><input aria-label={`변경 ${index + 1}일차 시간 상한`} type="number" min="0" max="24" value={day.credited_hours} onChange={event => setEditingDays(current => current.map((item, itemIndex) => itemIndex === index ? { ...item, credited_hours: Number(event.target.value) } : item))} disabled={!canWrite || lifecycleBusy} /><span>시간</span><button type="button" onClick={() => setEditingDays(current => current.filter((_, itemIndex) => itemIndex !== index))} disabled={!canWrite || lifecycleBusy || editingDays.length <= 1}>제거</button></div>)}
        <footer className="training-actions"><button type="button" onClick={() => setEditingScheduleId(null)} disabled={lifecycleBusy}>닫기</button><button className="training-primary" type="submit" disabled={!canWrite || lifecycleBusy}>{lifecycleBusy ? '저장 중…' : '변경 저장'}</button></footer>
      </form>}
    </section>
  </div>
}

function AssignmentWorkspace({ schedules, people, canWrite, onAssigned }: { schedules: Schedule[]; people: Person[]; canWrite: boolean; onAssigned: () => void }) {
  const [scheduleId, setScheduleId] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [review, setReview] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const activeScheduleId = scheduleId || (schedules[0] ? String(schedules[0].id) : '')
  const visiblePeople = people.filter(person => {
    const needle = query.trim().toLocaleLowerCase()
    return !needle || person.military_number.toLocaleLowerCase().includes(needle) || person.name.toLocaleLowerCase().includes(needle)
  }).slice(0, 100)

  const togglePerson = (militaryNumber: string) => setSelected(current => {
    const next = new Set(current)
    if (next.has(militaryNumber)) next.delete(militaryNumber)
    else next.add(militaryNumber)
    setReview(false)
    return next
  })

  const confirmAssignments = async () => {
    setBusy(true)
    setError('')
    try {
      const response = await authenticatedFetch(`${API}/reservists/training-schedules/${activeScheduleId}/roster`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_ids: [...selected] }),
      })
      if (!response.ok) throw new Error(await apiError(response, '훈련부과를 저장하지 못했습니다.'))
      setSelected(new Set())
      setReview(false)
      onAssigned()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '훈련부과를 저장하지 못했습니다.') }
    finally { setBusy(false) }
  }

  return <section className="training-section">
    <header><h2>훈련부과 대상 편성</h2><span>대상자를 지정해 훈련일정에 배정합니다.</span></header>
    <div className="training-toolbar">
      <label className="training-field">일정<select value={activeScheduleId} onChange={event => { setScheduleId(event.target.value); setSelected(new Set()); setReview(false) }}><option value="">일정 선택</option>{schedules.map(schedule => <option key={schedule.id} value={schedule.id}>{schedule.title} · {schedule.service_year}년차 {schedule.training_round}차</option>)}</select></label>
      <label className="training-field training-search">군번 또는 이름 검색<input value={query} onChange={event => setQuery(event.target.value)} /></label>
    </div>
    {activeScheduleId && <p className="training-note">군번 기준으로 대상자를 선택합니다. 일정에 이미 배정된 군번은 서버에서 중복 거절됩니다.</p>}
    <div className="training-person-list">{visiblePeople.map(person => <label key={person.military_number}>
      <input type="checkbox" checked={selected.has(person.military_number)} disabled={!canWrite || busy || !activeScheduleId} onChange={() => togglePerson(person.military_number)} />
      <span className="training-military">{person.military_number}</span><strong>{person.name}</strong><small>{person.branch} · {person.rank ?? '-'} · {person.service_year ?? '-'}년차</small>
    </label>)}</div>
    {visiblePeople.length === 0 && <p className="training-note">검색 결과가 없습니다.</p>}
    {error && <p className="training-message is-error" role="alert">{error}</p>}
    {review && <div className="training-review-box"><strong>{selected.size}명을 일정에 부과합니다.</strong><span>확정하면 각 사람의 기존 round-level Education 행을 새로 생성합니다.</span></div>}
    <footer className="training-actions">{review && <button type="button" onClick={() => setReview(false)} disabled={busy}>수정</button>}{review
      ? <button className="training-primary" type="button" disabled={busy || selected.size === 0} onClick={() => void confirmAssignments()}>{busy ? '저장 중…' : '부과 확정'}</button>
      : <button className="training-primary" type="button" disabled={!canWrite || !activeScheduleId || selected.size === 0} onClick={() => setReview(true)}>부과 검토 ({selected.size})</button>}</footer>
  </section>
}

function ResultsWorkspace({ schedules, people, canWrite, onSaved }: { schedules: Schedule[]; people: Person[]; canWrite: boolean; onSaved: () => void }) {
  const [view, setView] = useState<'session' | 'person'>('session')
  const [scheduleId, setScheduleId] = useState('')
  const [roster, setRoster] = useState<DraftRow[]>([])
  const [worklists, setWorklists] = useState<Worklists>(emptyWorklists)
  const [bulkState, setBulkState] = useState('이수')
  const [bulkHours, setBulkHours] = useState(8)
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
  const selectedScheduleId = scheduleId || (schedules[0] ? String(schedules[0].id) : '')
  const selectedSchedule = schedules.find(item => String(item.id) === selectedScheduleId)
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
    const personId = historyPersonId || people[0]?.military_number || ''
    if (!historyPersonId && personId) setHistoryPersonId(personId)
    if (!personId) {
      setHistory(null)
      return
    }
    const controller = new AbortController()
    setHistoryLoading(true)
    authenticatedFetch(`${API}/reservists/training-results/people/${encodeURIComponent(personId)}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(await apiError(response, '개인별 훈련 이력을 불러오지 못했습니다.'))
        return response.json() as Promise<PersonHistory>
      })
      .then(data => { if (!controller.signal.aborted) { setHistory(data); setHistoryError('') } })
      .catch(cause => { if (!controller.signal.aborted) setHistoryError(cause instanceof Error ? cause.message : '개인별 훈련 이력을 불러오지 못했습니다.') })
      .finally(() => { if (!controller.signal.aborted) setHistoryLoading(false) })
    return () => controller.abort()
  }, [view, historyPersonId, people.length])

  const updateRow = (id: number, patch: Partial<DraftRow>) => {
    setRoster(current => current.map(row => row.education_id === id ? { ...row, ...patch, selected: true } : row))
    setReviewing(false)
    setBatchKey(null)
  }
  const applyBulk = () => {
    setRoster(current => current.map(row => row.selected ? { ...row, result: bulkState, hours: bulkHours } : row))
    setReviewing(false)
    setBatchKey(null)
  }
  const toggleAll = (checked: boolean) => setRoster(current => current.map(row => ({ ...row, selected: checked })))

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
      || ((row.result === '이수' || row.result === '참석') && row.hours < 1)
      || (['무단불참', '연기', '보류'].includes(row.result) && row.hours !== 0)
      || (row.override && !row.override_reason.trim())
      || (row.attendance_status === '무단불참' && row.result !== '무단불참' && !row.reversal_reason.trim()))
    if (invalid) {
      setError('결과 상태별 인정시간과 초과 허용 사유를 확인해 주세요.')
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
        <label className="training-field training-history-person">대상자<select value={historyPersonId || people[0]?.military_number || ''} onChange={event => setHistoryPersonId(event.target.value)}>{people.map(person => <option key={person.military_number} value={person.military_number}>{person.military_number} · {person.name}</option>)}</select></label>
        {historyLoading && <p className="training-note">훈련 이력을 불러오는 중…</p>}
        {historyError && <p className="training-message is-error" role="alert">{historyError}</p>}
        {history && <PersonHistoryPanel history={history} />}
      </> : <>
      <header><h2>행사 결과 roster</h2><button type="button" onClick={() => void downloadCsv()}>CSV 내보내기</button></header>
      <div className="training-toolbar">
        <label className="training-field">훈련일정<select value={selectedScheduleId} onChange={event => { setScheduleId(event.target.value); setRoster([]); setMessage('') }}><option value="">일정 선택</option>{schedules.map(schedule => <option key={schedule.id} value={schedule.id}>{schedule.title} · {schedule.training_type}</option>)}</select></label>
      </div>
      {!canWrite && <p className="training-note">결과 입력과 확인에는 scheduler 권한이 필요합니다.</p>}
      {selectedSchedule && <div className="training-session-summary"><strong>{selectedSchedule.title}</strong><span>{selectedSchedule.service_year}년차 · {selectedSchedule.training_round}차 · {roster.length}명</span><span>완료 {roster.filter(row => row.result_status !== '결과 미입력' && row.attendance_status !== 'scheduled').length} · 결과 미입력 {worklists.missing_results.filter(row => row.schedule_title === selectedSchedule.title).length}</span></div>}
      {roster.length > 0 && <>
        <div className="training-toolbar training-bulk-toolbar">
          <label><input type="checkbox" checked={roster.every(row => row.selected)} onChange={event => toggleAll(event.target.checked)} /> 전체 선택</label>
          <label className="training-field">선택 결과<select value={bulkState} onChange={event => setBulkState(event.target.value)}>{states.map(state => <option key={state}>{state}</option>)}</select></label>
          <label className="training-field">일괄 시간<input type="number" min="0" max="720" value={bulkHours} onChange={event => setBulkHours(Number(event.target.value))} /></label>
          <button type="button" onClick={applyBulk} disabled={!canWrite || !roster.some(row => row.selected)}>선택 행에 적용</button>
        </div>
        <div className="training-table-wrap"><table className="training-result-table"><thead><tr><th></th><th>군번</th><th>성명</th><th>차수</th><th>현재 결과</th><th>결과 입력</th><th>인정시간</th><th>시간 초과 허용</th><th>메모</th><th>불참 정정 사유</th></tr></thead><tbody>{roster.map(row => <tr key={row.education_id}>
          <td><input aria-label={`${row.name} 선택`} type="checkbox" checked={row.selected} disabled={!canWrite || reviewing || busy} onChange={event => setRoster(current => current.map(item => item.education_id === row.education_id ? { ...item, selected: event.target.checked } : item))} /></td>
          <td className="training-military">{row.military_number}</td><td>{row.name}</td><td>{row.training_round}차</td><td>{row.result_status}</td>
          <td><select aria-label={`${row.name} 결과`} value={row.result} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { result: event.target.value })}><option value="">결과 선택</option>{states.map(state => <option key={state}>{state}</option>)}</select></td>
          <td><input aria-label={`${row.name} 인정시간`} type="number" min="0" max="720" value={row.hours} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { hours: Number(event.target.value) })} /></td>
          <td><label className="training-override"><input type="checkbox" checked={row.override} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { override: event.target.checked })} />허용</label>{row.override && <input aria-label={`${row.name} 초과 사유`} value={row.override_reason} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { override_reason: event.target.value })} />}</td>
          <td><input aria-label={`${row.name} 결과 메모`} value={row.notes ?? ''} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { notes: event.target.value })} /></td>
          <td>{row.attendance_status === '무단불참' && row.result !== '무단불참' && <input aria-label={`${row.name} 불참 정정 사유`} required value={row.reversal_reason} disabled={!canWrite || reviewing || busy} onChange={event => updateRow(row.education_id, { reversal_reason: event.target.value })} />}</td>
        </tr>)}</tbody></table></div>
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
  return <div className="training-history-panel">
    <header><h2>{history.name}</h2><span className="training-military">{history.military_number}</span></header>
    <div className="training-table-wrap"><table><thead><tr><th>연차</th><th>필요</th><th>인정</th><th>잔여</th><th>고발</th></tr></thead><tbody>{history.years.map(year => <tr key={year.service_year}><td>{year.service_year}년차</td><td>{year.required_hours}시간</td><td>{year.counted_hours}시간</td><td>{year.remaining_hours}시간</td><td>{year.prosecution_status ?? '-'}</td></tr>)}</tbody></table></div>
    <h3>차수별 결과와 감사 이력</h3>
    <div className="training-table-wrap"><table><thead><tr><th>연차</th><th>종류</th><th>차수</th><th>결과</th><th>인정시간</th><th>감사</th></tr></thead><tbody>{history.records.map(record => <tr key={record.education_id}>
      <td>{record.service_year}년차</td><td>{record.training_type}</td><td>{record.training_round}차</td><td>{record.attendance_status}</td><td>{record.counted_hours}/{record.training_hours}시간</td>
      <td><details><summary>{record.audit.length}건</summary>{record.audit.map((audit, index) => <p key={`${audit.created_at}-${index}`}>{audit.created_at} · {audit.actor} · {audit.action}</p>)}</details></td>
    </tr>)}</tbody></table></div>
  </div>
}

function WorklistPanel({ worklists }: { worklists: Worklists }) {
  return <aside className="training-section training-worklists">
    <header><h2>결과 worklists</h2><span>{worklists.missing_results.length + worklists.absences_scheduler_can_confirm.length + worklists.absences_needing_approver.length}건</span></header>
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
  </aside>
}
