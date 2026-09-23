import { useEffect, useMemo, useState } from 'react'

type Squad = {
  id: number
  name: string
  description: string | null
  person_count: number
}

type ResourcePerson = {
  military_number: string
  name: string
  branch: string
  rank: string | null
  unit: string | null
  specialty: string | null
  origin_type: string | null
  registration_type: string | null
  service_year: number | null
  position: string | null
  mobilization_status: string | null
  status: string
  squad_id: number | null
}

type TrainingRecord = {
  id: number
  education_year: number
  training_year: number | null
  training_type: string
  training_round: number
  attendance_status: string
  training_hours: number
  required_hours: number | null
}

type TrainingProgress = {
  service_year: number
  training_plan: { name: string; hours: number }[]
}

function trainingHistory(records: TrainingRecord[], progress: TrainingProgress[]) {
  const rows = new Map<string, { name: string; serviceYear: number; completed: number; required: number | null }>()
  for (const record of records) {
    const plan = progress.find(item => item.service_year === record.education_year)?.training_plan ?? []
    const rawName = record.training_type.trim()
    const generic = !rawName || rawName === '훈련'
    const component = plan.find(item => item.name === rawName)
      ?? (generic && plan.length === 1 ? plan[0] : undefined)
    const name = component?.name ?? (generic ? '훈련 종류 미상' : rawName)
    const key = `${record.education_year}:${name}`
    const row = rows.get(key) ?? { name, serviceYear: record.education_year, completed: 0, required: record.required_hours ?? component?.hours ?? null }
    if (record.attendance_status === 'completed' || record.attendance_status === '이수') {
      row.completed += record.training_hours
    }
    rows.set(key, row)
  }
  return [...rows.values()].sort((a, b) => b.serviceYear - a.serviceYear || a.name.localeCompare(b.name, 'ko'))
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
type SortKey = 'checked' | 'number' | 'name' | 'military_number' | 'unit' | 'squad_id' | 'status' | 'position' | 'service_year'
const rosterColumns: { key: SortKey; label: string }[] = [
  { key: 'checked', label: '선택' }, { key: 'number', label: 'No.' },
  { key: 'name', label: '이름' }, { key: 'military_number', label: '군번' },
  { key: 'unit', label: '소속' }, { key: 'squad_id', label: '편성 부대' },
  { key: 'status', label: '상태' }, { key: 'position', label: '직책' },
  { key: 'service_year', label: '연차' },
]
const rosterCollator = new Intl.Collator('ko', { numeric: true })
const statusLabel = (status: string) => status === 'active' ? '복무 중' : status === 'on_leave' ? '휴가 중' : status

async function responseError(response: Response, fallback: string) {
  try {
    const data = await response.json() as { detail?: string }
    return data.detail ?? fallback
  } catch {
    return fallback
  }
}

export default function ResourceRosterPage({ revision }: { revision: number }) {
  const [squads, setSquads] = useState<Squad[]>([])
  const [people, setPeople] = useState<ResourcePerson[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [input, setInput] = useState('')
  const [unit, setUnit] = useState('')
  const [status, setStatus] = useState('')
  const [position, setPosition] = useState('')
  const [year, setYear] = useState('')
  // 입력 중인 검색 조건과 실제 목록에 적용된 조건을 분리합니다.
  // 검색 버튼 또는 Enter를 누르기 전에는 어떤 드롭다운도 목록을 변경하지 않습니다.
  const [appliedFilters, setAppliedFilters] = useState({
    query: '', unit: '', status: '', position: '', year: '',
  })
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<{ key: SortKey; direction: 'ascending' | 'descending' }>({ key: 'squad_id', direction: 'ascending' })
  const [checked, setChecked] = useState<Set<string>>(() => new Set())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [records, setRecords] = useState<TrainingRecord[]>([])
  const [trainingProgress, setTrainingProgress] = useState<TrainingProgress[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/squads`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(await responseError(response, '분대 목록을 불러오지 못했습니다.'))
        return response.json() as Promise<Squad[]>
      })
      .then(result => { if (!controller.signal.aborted) setSquads(result) })
      .catch(() => { if (!controller.signal.aborted) setSquads([]) })
    return () => controller.abort()
  }, [revision])

  useEffect(() => {
    const controller = new AbortController()
    // 이름·군번 검색 및 나머지 필터는 로컬에 보관하여 탭 전환 중에도 유지합니다.
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const response = await fetch(`${API_BASE}/persons`, { signal: controller.signal })
        if (!response.ok) throw new Error(await responseError(response, '인원 목록을 불러오지 못했습니다.'))
        const result = await response.json() as ResourcePerson[]
        if (!controller.signal.aborted) setPeople(result)
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '인원 목록을 불러오지 못했습니다.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [revision])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    const load = async () => {
      setDetailLoading(true)
      setDetailError('')
      try {
        const response = await fetch(`${API_BASE}/reservists/${encodeURIComponent(selectedId)}/training-hours`,
          { signal: controller.signal })
        if (!response.ok) throw new Error(await responseError(response, '훈련 기록을 불러오지 못했습니다.'))
        const result = await response.json() as { records: TrainingRecord[]; progress: TrainingProgress[] }
        if (!controller.signal.aborted) {
          setRecords(result.records ?? [])
          setTrainingProgress(result.progress ?? [])
        }
      } catch (cause) {
        if (!controller.signal.aborted) setDetailError(cause instanceof Error ? cause.message : '훈련 기록을 불러오지 못했습니다.')
      } finally {
        if (!controller.signal.aborted) setDetailLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [selectedId, revision])

  const squadNames = useMemo(() => new Map(squads.map(squad => [squad.id, squad.name])), [squads])
  const units = useMemo(() => [...new Set(people.map(person => person.unit).filter((name): name is string => !!name))].sort(), [people])
  const positions = useMemo(() => [...new Set(people.map(person => person.position).filter((name): name is string => !!name))].sort(), [people])
  const years = useMemo(() => [...new Set(people.map(person => person.service_year)
    .filter((number): number is number => number !== null))].sort((a, b) => a - b), [people])
  const filtered = useMemo(() => people.filter(person => {
    const term = appliedFilters.query.toLocaleLowerCase()
    return (!term || person.name.toLocaleLowerCase().includes(term) || person.military_number.toLocaleLowerCase().includes(term))
      && (!appliedFilters.unit || (appliedFilters.unit === '__unassigned__'
        ? person.squad_id === null : person.unit === appliedFilters.unit))
      && (!appliedFilters.status || person.status === appliedFilters.status)
      && (!appliedFilters.position || person.position === appliedFilters.position)
      && (!appliedFilters.year || String(person.service_year) === appliedFilters.year)
  }), [people, appliedFilters])
  const personNumbers = useMemo(() => new Map(people.map((person, index) => [person.military_number, index + 1])), [people])
  const sorted = useMemo(() => {
    const value = (person: ResourcePerson): string | number | null => {
      switch (sort.key) {
        case 'checked': return Number(checked.has(person.military_number))
        case 'number': return personNumbers.get(person.military_number) ?? 0
        case 'squad_id': return person.squad_id === null ? null : (squadNames.get(person.squad_id) ?? `${person.squad_id}번 분대`)
        case 'status': return statusLabel(person.status)
        default: return person[sort.key]
      }
    }
    return [...filtered].sort((a, b) => {
      const left = value(a)
      const right = value(b)
      // 미편성 인원은 편성 부대 내림차순에서 맨 앞에 표시합니다.
      if (left === null || right === null) {
        const comparison = left === right ? 0 : left === null ? 1 : -1
        return sort.key === 'squad_id' && sort.direction === 'descending' ? -comparison : comparison
      }
      const comparison = typeof left === 'number' && typeof right === 'number'
        ? left - right : rosterCollator.compare(String(left), String(right))
      return sort.direction === 'ascending' ? comparison : -comparison
    })
  }, [filtered, sort, checked, personNumbers, squadNames])
  const changeSort = (key: SortKey) => {
    setSort(previous => ({ key, direction: previous.key === key && previous.direction === 'ascending' ? 'descending' : 'ascending' }))
    setPage(1)
  }
  const pageSize = 20
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const actualPage = Math.min(page, pageCount)
  const pageRows = sorted.slice((actualPage - 1) * pageSize, actualPage * pageSize)
  const selected = people.find(person => person.military_number === selectedId) ?? null
  const checkedOnPage = pageRows.length > 0 && pageRows.every(person => checked.has(person.military_number))
  const squadLabel = (person: ResourcePerson) => person.squad_id === null
    ? '-' : (squadNames.get(person.squad_id) ?? `${person.squad_id}번 분대`)

  const openPerson = (id: string) => { setRecords([]); setDetailError(''); setDetailLoading(true); setSelectedId(id) }
  const closePerson = () => { setSelectedId(null); setRecords([]); setDetailError('') }
  const toggleChecked = (id: string, value: boolean) => setChecked(previous => {
    const next = new Set(previous)
    if (value) next.add(id)
    else next.delete(id)
    return next
  })
  const submitSearch = () => {
    setAppliedFilters({ query: input.trim(), unit, status, position, year })
    setPage(1)
  }
  const reset = () => {
    setInput(''); setUnit(''); setStatus(''); setPosition(''); setYear('')
    setAppliedFilters({ query: '', unit: '', status: '', position: '', year: '' })
    setPage(1)
    setChecked(new Set())
  }
  const metrics = [
    { label: '전체 대상자', number: people.length, description: '전체 예비군 등록 인원', color: 'blue' },
    { label: '분대 편성', number: people.filter(person => person.squad_id !== null).length, description: '소속 분대가 있는 인원', color: 'blue' },
    { label: '미편성', number: people.filter(person => person.squad_id === null).length, description: '소속 분대가 없는 인원', color: 'orange' },
    { label: '복무 중', number: people.filter(person => person.status === 'active').length, description: '현재 등록 상태 기준', color: 'green' },
  ]

  return <div className={`rm-roster-layout ${selected ? 'has-detail' : ''}`}>
    <div className="rm-roster-main">
      <h1 className="rm-roster-title"><svg aria-hidden="true" viewBox="0 0 32 26" width="33" height="27" fill="currentColor"><circle cx="16" cy="6" r="4"/><circle cx="5" cy="11" r="3"/><circle cx="27" cy="11" r="3"/><path d="M7 25v-5c0-5 4-8 9-8s9 3 9 8v5H7ZM0 25v-5c0-3 2-5 5-5 1 0 2 .2 3 .8C6 18 5 21 5 25H0ZM27 25v-4c0-2-.8-4-2-5.2a6 6 0 0 1 3-.8c3 0 4 2 4 5v5h-5Z"/></svg> 예비군 대상자 관리</h1>
      <div className="rm-summary-grid">
        {metrics.map(metric => <section key={metric.label} className="rm-summary-card">
          <h2><span className={`rm-summary-icon ${metric.color}`} aria-hidden="true">●</span>{metric.label}</h2>
          <strong>{loading ? '—' : `${metric.number.toLocaleString('ko-KR')}명`}</strong>
          <p>{metric.description}</p>
        </section>)}
      </div>
      <form className="rm-search-controls" onSubmit={event => { event.preventDefault(); submitSearch() }}>
        <label className="rm-query-input"><span aria-hidden="true">⌕</span><input aria-label="성명 또는 군번 검색"
          value={input} onChange={event => setInput(event.target.value)} placeholder="이름, 군번을 입력하세요." /></label>
        <select aria-label="소속 선택" value={unit} onChange={event => setUnit(event.target.value)}>
          <option value="">소속 선택</option><option value="__unassigned__">소속 분대 없음</option>
          {units.map(value => <option key={value} value={value}>{value}</option>)}
        </select>
        <select aria-label="상태 선택" value={status} onChange={event => setStatus(event.target.value)}>
          <option value="">상태 선택</option><option value="active">복무 중</option><option value="on_leave">휴가 중</option>
        </select>
        <select aria-label="직책 선택" value={position} onChange={event => setPosition(event.target.value)}>
          <option value="">직책 선택</option>{positions.map(value => <option key={value} value={value}>{value}</option>)}
        </select>
        <select aria-label="연차 선택" value={year} onChange={event => setYear(event.target.value)}>
          <option value="">연차 선택</option>{years.map(value => <option key={value} value={value}>{value}년차</option>)}
        </select>
        <button type="submit" className="rm-btn rm-btn-primary">검색</button>
        <button type="button" className="rm-btn" onClick={reset}>초기화</button>
      </form>
      <section className="rm-person-list" aria-label="편성인원 목록">
        <div className="rm-person-list-toolbar">
          <label><input type="checkbox" checked={checkedOnPage} disabled={pageRows.length === 0}
            onChange={event => {
              const isChecked = event.target.checked
              setChecked(previous => {
                const next = new Set(previous)
                pageRows.forEach(person => isChecked ? next.add(person.military_number) : next.delete(person.military_number))
                return next
              })
            }} />현재 페이지 전체선택</label>
          <span>선택 {checked.size}명</span>
          <span className="rm-list-total">총 {filtered.length.toLocaleString('ko-KR')}명</span>
        </div>
        {loading ? <p className="rm-list-message">인원 목록을 불러오는 중입니다.</p>
          : error ? <p className="rm-list-message rm-error">{error}</p>
          : <div className="rm-list-scroll"><table className="rm-person-table">
            <thead><tr>{rosterColumns.map(column => <th key={column.key} scope="col"
              aria-sort={sort.key === column.key ? sort.direction : 'none'}>
              <button type="button" className="rm-sort-button" onClick={() => changeSort(column.key)}
                aria-label={`${column.label}, ${sort.key === column.key && sort.direction === 'ascending' ? '내림차순' : '오름차순'} 정렬`}>
                <span>{column.label}</span>
                <span className="rm-sort-indicator" aria-hidden="true">{sort.key === column.key ? (sort.direction === 'ascending' ? '▼' : '▲') : ''}</span>
              </button>
            </th>)}</tr></thead>
            <tbody>{pageRows.map(person => <tr key={person.military_number}
              className={selectedId === person.military_number ? 'is-selected' : ''}
              tabIndex={0} aria-selected={selectedId === person.military_number}
              onClick={() => openPerson(person.military_number)}
              onKeyDown={event => {
                if (event.target !== event.currentTarget) return
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  openPerson(person.military_number)
                }
              }}>
              <td><input type="checkbox" aria-label={`${person.name} 선택`} checked={checked.has(person.military_number)}
                onClick={event => event.stopPropagation()}
                onChange={event => toggleChecked(person.military_number, event.target.checked)} /></td>
              <td>{personNumbers.get(person.military_number)}</td><td className="rm-table-name">{person.name}</td>
              <td className="rm-num">{person.military_number}</td>
              <td><span className="rm-unit">{person.unit ?? '소속 정보 없음'}</span></td>
              <td>{squadLabel(person)}</td>
              <td><span className={`rm-status ${person.status === 'active' ? 'active' : 'other'}`}>
                {person.status === 'active' ? '복무 중' : person.status === 'on_leave' ? '휴가 중' : person.status}
              </span></td>
              <td>{person.position ?? '—'}</td><td>{person.service_year === null ? '—' : `${person.service_year}년차`}</td>
            </tr>)}</tbody>
          </table>{filtered.length === 0 && <p className="rm-list-message">검색 결과가 없습니다.</p>}</div>}
        <footer className="rm-person-footer"><span>총 {filtered.length.toLocaleString('ko-KR')}명 중 {filtered.length ? (actualPage - 1) * pageSize + 1 : 0}–{Math.min(actualPage * pageSize, filtered.length)}명 표시</span>
          <nav aria-label="인원 목록 페이지">
            <button type="button" disabled={actualPage === 1} onClick={() => setPage(actualPage - 1)} aria-label="이전 페이지">‹</button>
            {Array.from({ length: Math.min(5, pageCount) }, (_, index) => {
              const start = Math.max(1, Math.min(actualPage - 2, pageCount - 4))
              const pageNumber = start + index
              return <button key={pageNumber} type="button" className={actualPage === pageNumber ? 'is-current' : ''}
                aria-current={actualPage === pageNumber ? 'page' : undefined} onClick={() => setPage(pageNumber)}>{pageNumber}</button>
            })}
            <button type="button" disabled={actualPage === pageCount} onClick={() => setPage(actualPage + 1)} aria-label="다음 페이지">›</button>
          </nav>
        </footer>
      </section>
    </div>
    {selected && <aside className="rm-person-detail" aria-label="대상자 상세 정보">
      <header className="rm-detail-heading"><h2>대상자 상세 정보</h2><button type="button"
        onClick={closePerson}>닫기</button></header>
      <div className="rm-detail-body">
        <div className="rm-detail-person"><span className="rm-detail-avatar" aria-hidden="true">♙</span><div>
          <h3>{selected.name}</h3><p>군번: {selected.military_number}</p>
          <span className="rm-detail-tag">{squadLabel(selected)}</span>
        </div></div>
        <dl className="rm-detail-fields">
          {[
            ['성명', selected.name], ['군번', selected.military_number], ['소속 부대', selected.unit ?? '미등록'],
            ['편성 분대', squadLabel(selected)], ['군종', selected.branch], ['계급', selected.rank ?? '미등록'],
            ['상태', selected.status === 'active' ? '복무 중' : selected.status === 'on_leave' ? '휴가 중' : selected.status],
            ['동원 상태', selected.mobilization_status ?? '미등록'], ['직책', selected.position ?? '미등록'],
            ['주특기', selected.specialty ?? '미등록'],
            ['연차', selected.service_year === null ? '미등록' : `${selected.service_year}년차`],
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl>
        <h4>훈련 이력</h4>
        {detailLoading ? <p className="rm-detail-note">훈련 이력을 불러오는 중입니다.</p>
          : detailError ? <p className="rm-detail-note rm-error">{detailError}</p>
          : records.length === 0 ? <p className="rm-detail-note">등록된 훈련 기록이 없습니다.</p>
          : <div className="rm-training-records">{trainingHistory(records, trainingProgress)
              .map(record => <div key={`${record.serviceYear}:${record.name}`}>
                <span>{record.serviceYear}년차 · {record.name}</span>
                <b aria-label={`이수 ${record.completed}시간, 필요 ${record.required === null ? '확인 필요' : `${record.required}시간`}`}>
                  {record.completed}/{record.required ?? '—'}시간
                </b>
              </div>)}</div>}
        <p className="rm-detail-note">전화번호·주소·이메일은 현재 인원 API에서 제공하지 않습니다.</p>
      </div>
    </aside>}
  </div>
}

