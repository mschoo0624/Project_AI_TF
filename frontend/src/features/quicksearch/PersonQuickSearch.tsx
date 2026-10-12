import { useEffect, useMemo, useState } from 'react'
import './personQuickSearch.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const RECENT_KEY = 'project-ai-tf.recent-people'
const RECENT_LIMIT = 8
const SHOWN_LIMIT = 6

type Person = { military_number: string; name: string; branch: string; rank: string | null; specialty: string | null; service_year: number | null }
type TrainingProgress = { service_year: number; training_plan: { name: string; hours: number }[]; required_hours: number; completed_hours: number; remaining_hours: number; training_status: string; prosecution_risk: boolean }
type TrainingRecord = { id: number; education_year: number; training_year: number | null; training_type: string; training_round: number; attendance_status: string; training_hours: number }

// 최근 조회는 군번만 이 브라우저에 저장하고, 이름·소속은 서버 목록에서 다시 찾아 씁니다.
function readRecentIds(): string[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string').slice(0, RECENT_LIMIT) : []
  } catch {
    return []
  }
}

function writeRecentIds(ids: string[]) {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(ids))
  } catch {
    // 저장소를 쓸 수 없으면 이번 화면에서만 유지됩니다.
  }
}

const subtitle = (person: Person) => [person.rank, person.service_year ? `${person.service_year}년차` : null, person.branch].filter(Boolean).join(' · ')

export default function PersonQuickSearch() {
  const [people, setPeople] = useState<Person[] | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [recentIds, setRecentIds] = useState<string[]>(readRecentIds)
  const [selected, setSelected] = useState<Person | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/persons`, { signal: controller.signal, cache: 'no-store' })
      .then(async response => {
        if (!response.ok) throw new Error('대상자 목록을 불러오지 못했습니다.')
        return response.json() as Promise<Person[]>
      })
      .then(data => { if (!controller.signal.aborted) { setPeople(data); setError('') } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '대상자 목록을 불러오지 못했습니다.') })
    return () => controller.abort()
  }, [])

  const byNumber = useMemo(() => new Map((people ?? []).map(person => [person.military_number, person] as const)), [people])
  const typed = query.trim()
  const keyword = typed.toLowerCase()
  const matches = useMemo(() => {
    if (!keyword || !people) return []
    const rank = (person: Person) => {
      const number = person.military_number.toLowerCase()
      const name = person.name.toLowerCase()
      if (number === keyword || name === keyword) return 0
      return number.startsWith(keyword) || name.startsWith(keyword) ? 1 : 2
    }
    return people
      .filter(person => person.name.toLowerCase().includes(keyword) || person.military_number.toLowerCase().includes(keyword))
      .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, 'ko'))
  }, [people, keyword])
  const recent = recentIds.map(id => byNumber.get(id)).filter((person): person is Person => !!person)

  const openPerson = (person: Person) => {
    setSelected(person)
    const next = [person.military_number, ...recentIds.filter(id => id !== person.military_number)].slice(0, RECENT_LIMIT)
    setRecentIds(next)
    writeRecentIds(next)
  }
  const clearRecent = () => { setRecentIds([]); writeRecentIds([]) }

  const row = (person: Person) => <li key={person.military_number}>
    <button type="button" className="qs-item" onClick={() => openPerson(person)}>
      <span className="qs-avatar" aria-hidden="true">{person.name.slice(0, 1)}</span>
      <span className="qs-main"><strong>{person.name}</strong><small>{subtitle(person) || '소속 정보 없음'}</small></span>
      <span className="qs-number">{person.military_number}</span>
    </button>
  </li>

  let body
  if (error) body = <p className="qs-empty" role="alert">{error}</p>
  else if (!people) body = <p className="qs-empty" role="status">대상자 목록을 불러오는 중…</p>
  else if (keyword) {
    body = matches.length === 0
      ? <p className="qs-empty">일치하는 대상자가 없습니다.</p>
      : <>
        <ul className="qs-list">{matches.slice(0, SHOWN_LIMIT).map(row)}</ul>
        {matches.length > SHOWN_LIMIT && <p className="qs-hint">총 {matches.length}명 중 {SHOWN_LIMIT}명만 표시합니다. 더 입력해서 좁혀보세요.</p>}
      </>
  } else {
    body = <>
      <div className="qs-section-head">
        <span>최근 조회</span>
        {recent.length > 0 && <button type="button" onClick={clearRecent}>지우기</button>}
      </div>
      {recent.length === 0
        ? <p className="qs-empty">최근 조회한 대상자가 없습니다.<br />군번이나 이름으로 검색해 보세요.</p>
        : <ul className="qs-list">{recent.slice(0, 5).map(row)}</ul>}
    </>
  }

  return <section className="quick-search-card" aria-label="대상자 빠른 검색">
    <span className="home-panel-chip">대상자 조회</span>
    <label className="qs-input">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <input value={query} onChange={event => setQuery(event.target.value)} placeholder="군번 또는 이름 검색" aria-label="대상자 검색"
        onKeyDown={event => { if (event.key === 'Enter' && matches[0]) openPerson(matches[0]) }} />
      {query && <button type="button" className="qs-clear" aria-label="검색어 지우기" onClick={() => setQuery('')}>✕</button>}
    </label>
    {body}
    {selected && <QuickPersonProfile key={selected.military_number} person={selected} onClose={() => setSelected(null)} />}
  </section>
}

function QuickPersonProfile({ person, onClose }: { person: Person; onClose: () => void }) {
  const [progress, setProgress] = useState<TrainingProgress[]>([])
  const [records, setRecords] = useState<TrainingRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/reservists/${encodeURIComponent(person.military_number)}/training-hours`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('훈련 이력을 불러오지 못했습니다.')
        return response.json() as Promise<{ progress?: TrainingProgress[]; records?: TrainingRecord[] }>
      })
      .then(data => { if (!controller.signal.aborted) { setProgress(data.progress ?? []); setRecords(data.records ?? []) } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '훈련 이력을 불러오지 못했습니다.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [person.military_number])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return <div className="qs-backdrop" onClick={onClose}>
    <div className="qs-profile" role="dialog" aria-modal="true" aria-label={`${person.name} 프로필`} onClick={event => event.stopPropagation()}>
      <header className="qs-profile-head">
        <span className="qs-avatar" aria-hidden="true">{person.name.slice(0, 1)}</span>
        <div>
          <h2>{person.name}</h2>
          <p>{person.military_number}{subtitle(person) ? ` · ${subtitle(person)}` : ''}</p>
        </div>
        <button type="button" aria-label="프로필 닫기" onClick={onClose}>✕</button>
      </header>
      <div className="qs-profile-body">
        <dl className="qs-fields">
          <div><dt>소속</dt><dd>{person.branch || '-'}</dd></div>
          <div><dt>계급</dt><dd>{person.rank ?? '-'}</dd></div>
          <div><dt>특기</dt><dd>{person.specialty ?? '-'}</dd></div>
          <div><dt>복무연차</dt><dd>{person.service_year ? `${person.service_year}년차` : '-'}</dd></div>
        </dl>
        {loading && <p className="qs-empty" role="status">훈련 이력을 불러오는 중…</p>}
        {error && <p className="qs-empty" role="alert">{error}</p>}
        {!loading && !error && <>
          <h3>연차별 훈련 현황</h3>
          <ul className="qs-progress">
            {progress.filter(item => item.service_year > 0).map(item => <li key={item.service_year} className={item.prosecution_risk ? 'is-risk' : ''}>
              <span>{item.service_year}년차</span>
              <small>{item.training_plan.map(plan => plan.name).join(', ') || '훈련 대상 아님'}</small>
              <b>{item.completed_hours}/{item.required_hours}시간 · {item.training_status}</b>
            </li>)}
          </ul>
          <h3>훈련 기록</h3>
          {records.length === 0
            ? <p className="qs-empty">등록된 훈련 기록이 없습니다.</p>
            : <div className="qs-table-wrap"><table className="qs-table">
              <thead><tr><th>연차</th><th>훈련연도</th><th>종류</th><th>차수</th><th>출결</th><th>시간</th></tr></thead>
              <tbody>{records.map(record => <tr key={record.id}>
                <td>{record.education_year}년차</td><td>{record.training_year ?? '-'}</td><td>{record.training_type}</td>
                <td>{record.training_round}차</td><td>{record.attendance_status}</td><td>{record.training_hours}시간</td>
              </tr>)}</tbody>
            </table></div>}
        </>}
      </div>
    </div>
  </div>
}
