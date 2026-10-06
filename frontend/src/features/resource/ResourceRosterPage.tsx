import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import PersonProfileFields from './PersonProfileFields'

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
  notes: string | null
}

type TrainingProgress = {
  service_year: number
  mobilization_status: string | null
  training_plan: { name: string; hours: number }[]
  target_hours: number
  required_hours: number
  completed_hours: number
  remaining_hours: number
  training_status: string
  prosecution_risk: boolean
}

type TrainingRecordForm = {
  service_year: number
  training_year: number
  training_type: string
  training_round: number
  attendance_status: string
  training_hours: number
  notes: string
}

type CreatePersonForm = {
  military_number: string
  name: string
  branch: string
  rank: string
  unit: string
  specialty: string
  service_year: number
  position: string
  mobilization_status: string
  status: string
  previous_training_hours: string
}

const trainingTypes = ['기본훈련', '동원훈련Ⅰ형', '동원훈련Ⅱ형', '작계훈련(전·후반기)']
const personBranches = ['육군', '해군', '공군', '해병대']
const personRanks = ['이병', '일병', '상병', '병장', '하사', '중사', '상사', '소위', '중위', '대위']
const personMobilizationStatuses = ['동원지정', '동원미지정', '학생예비군', '일부보류', '해당없음']
const initialCreatePersonForm: CreatePersonForm = {
  military_number: '', name: '', branch: '육군', rank: '병장', unit: '', specialty: '',
  service_year: 1, position: '소총수', mobilization_status: '동원미지정', status: 'active',
  previous_training_hours: '',
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
type SortKey = 'checked' | 'number' | 'name' | 'military_number' | 'branch' | 'rank' | 'squad_id' | 'status' | 'position' | 'mobilization_status' | 'service_year'
const rosterColumns: { key: SortKey; label: string }[] = [
  { key: 'checked', label: '선택' }, { key: 'number', label: 'No.' },
  { key: 'name', label: '이름' }, { key: 'military_number', label: '군번' },
  { key: 'branch', label: '군별' }, { key: 'rank', label: '계급' },
  { key: 'position', label: '직책' }, { key: 'squad_id', label: '편성 부대' },
  { key: 'status', label: '상태' }, { key: 'mobilization_status', label: '동원 상태' },
  { key: 'service_year', label: '연차' },
]
const rosterCollator = new Intl.Collator('ko', { numeric: true })
const statusLabel = (status: string) => status === 'active' ? '복무 중' : status === 'on_leave' ? '휴가 중' : status

type GroupTab = 'none' | 'year' | 'rank' | 'rankYear' | 'branch' | 'specialty'
const groupTabs: { key: GroupTab; label: string }[] = [
  { key: 'none', label: '전체' },
  { key: 'year', label: '연차별' },
  { key: 'rank', label: '계급별' },
  { key: 'rankYear', label: '계급/연차별' },
  { key: 'branch', label: '군별' },
  { key: 'specialty', label: '주특기별' },
]
const yearBucketOrder = ['0년차', '1~4년차', '5~6년차', '7~8년차', '연차 미등록']
const yearBucketLabel = (year: number | null) => {
  if (year === 0) return '0년차'
  if (year !== null && year >= 1 && year <= 4) return '1~4년차'
  if (year !== null && year >= 5 && year <= 6) return '5~6년차'
  if (year !== null && year >= 7 && year <= 8) return '7~8년차'
  return '연차 미등록'
}
const rankCategoryOrder = ['부사관', '장교', '병사', '기타']
const soldierRanks = new Set(['이병', '일병', '상병', '병장'])
const ncoRanks = new Set(['하사', '중사', '상사', '원사'])
const officerRanks = new Set(['소위', '중위', '대위', '소령', '중령', '대령'])
const rankCategoryLabel = (rank: string | null) => {
  if (rank !== null && soldierRanks.has(rank)) return '병사'
  if (rank !== null && ncoRanks.has(rank)) return '부사관'
  if (rank !== null && officerRanks.has(rank)) return '장교'
  return '기타'
}
const groupKeyFor = (person: ResourcePerson, tab: GroupTab): string => {
  switch (tab) {
    case 'year': return yearBucketLabel(person.service_year)
    case 'rank': return person.rank ?? '계급 미등록'
    case 'rankYear': return `${rankCategoryLabel(person.rank)} · ${yearBucketLabel(person.service_year)}`
    case 'branch': return person.branch
    case 'specialty': return person.specialty ?? '주특기 미등록'
    default: return ''
  }
}
const sortGroupValues = (values: string[], tab: GroupTab): string[] => [...values].sort((a, b) => {
  if (tab === 'rankYear') {
    const categoryA = rankCategoryOrder.findIndex(label => a.startsWith(label))
    const categoryB = rankCategoryOrder.findIndex(label => b.startsWith(label))
    if (categoryA !== categoryB) return categoryA - categoryB
  }
  if (tab === 'year' || tab === 'rankYear') {
    const orderA = yearBucketOrder.findIndex(label => a.endsWith(label))
    const orderB = yearBucketOrder.findIndex(label => b.endsWith(label))
    if (orderA !== orderB) return orderA - orderB
  }
  return rosterCollator.compare(a, b)
})

async function responseError(response: Response, fallback: string) {
  try {
    const data = await response.json() as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) {
      const messages = data.detail.map((item: unknown) => {
        if (typeof item !== 'object' || item === null || !('msg' in item)) return String(item)
        const message = String(item.msg)
        const location = 'loc' in item && Array.isArray(item.loc)
          ? item.loc.map(String).join('.')
          : ''
        return location ? `${location}: ${message}` : message
      })
      return messages.join('; ') || fallback
    }
    return fallback
  } catch {
    return fallback
  }
}

export default function ResourceRosterPage({ revision, onDataChanged, copilotFilter = null, onClearCopilotFilter }: {
  revision: number
  onDataChanged: () => void
  copilotFilter?: { label: string; ids: string[] } | null
  onClearCopilotFilter?: () => void
}) {
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
  const [groupTab, setGroupTab] = useState<GroupTab>('none')
  const [groupValue, setGroupValue] = useState<string | null>(null)
  const [checked, setChecked] = useState<Set<string>>(() => new Set())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [records, setRecords] = useState<TrainingRecord[]>([])
  const [trainingProgress, setTrainingProgress] = useState<TrainingProgress[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [detailTab, setDetailTab] = useState<'progress' | 'records' | 'results'>('progress')
  const [recordForm, setRecordForm] = useState<TrainingRecordForm | null>(null)
  const [editingRecord, setEditingRecord] = useState<number | null>(null)
  const [actionError, setActionError] = useState('')
  const [assignmentLoading, setAssignmentLoading] = useState(false)
  const [createPersonOpen, setCreatePersonOpen] = useState(false)
  const [createPersonForm, setCreatePersonForm] = useState<CreatePersonForm>(initialCreatePersonForm)
  const [createPersonLoading, setCreatePersonLoading] = useState(false)
  const [createPersonError, setCreatePersonError] = useState('')

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

  // Copilot 검색 결과(군번 목록)는 기존 검색 조건 위에 한 번 더 걸립니다.
  const copilotIds = useMemo(() => copilotFilter ? new Set(copilotFilter.ids) : null, [copilotFilter])
  const [seenCopilotFilter, setSeenCopilotFilter] = useState(copilotFilter)
  if (copilotFilter !== seenCopilotFilter) {
    setSeenCopilotFilter(copilotFilter)
    setPage(1)
  }
  const squadNames = useMemo(() => new Map(squads.map(squad => [squad.id, squad.name])), [squads])
  const units = useMemo(() => [...new Set(people.map(person => person.unit).filter((name): name is string => !!name))].sort(), [people])
  const positions = useMemo(() => [...new Set(people.map(person => person.position).filter((name): name is string => !!name))].sort(), [people])
  const years = useMemo(() => [...new Set(people.map(person => person.service_year)
    .filter((number): number is number => number !== null))].sort((a, b) => a - b), [people])
  const searchFiltered = useMemo(() => people.filter(person => {
    const term = appliedFilters.query.toLocaleLowerCase()
    return (!copilotIds || copilotIds.has(person.military_number))
      && (!term || person.name.toLocaleLowerCase().includes(term) || person.military_number.toLocaleLowerCase().includes(term))
      && (!appliedFilters.unit || (appliedFilters.unit === '__unassigned__'
        ? person.squad_id === null : person.unit === appliedFilters.unit))
      && (!appliedFilters.status || person.status === appliedFilters.status)
      && (!appliedFilters.position || person.position === appliedFilters.position)
      && (!appliedFilters.year || String(person.service_year) === appliedFilters.year)
  }), [people, appliedFilters, copilotIds])
  const groupOptions = useMemo(() => {
    if (groupTab === 'none') return []
    return sortGroupValues([...new Set(searchFiltered.map(person => groupKeyFor(person, groupTab)))], groupTab)
  }, [searchFiltered, groupTab])
  const filtered = useMemo(() => {
    if (groupTab === 'none' || groupValue === null) return searchFiltered
    return searchFiltered.filter(person => groupKeyFor(person, groupTab) === groupValue)
  }, [searchFiltered, groupTab, groupValue])
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
  const selectGroupTab = (tab: GroupTab) => {
    setGroupTab(tab)
    setPage(1)
    if (tab === 'none') { setGroupValue(null); return }
    const values = sortGroupValues([...new Set(searchFiltered.map(person => groupKeyFor(person, tab)))], tab)
    setGroupValue(values[0] ?? null)
  }
  const selectGroupValue = (value: string) => { setGroupValue(value); setPage(1) }
  const renderPersonRow = (person: ResourcePerson) => <tr key={person.military_number}
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
    <td>{person.branch}</td><td>{person.rank ?? '—'}</td>
    <td title={person.position ?? undefined}>{person.position ?? '—'}</td>
    <td title={squadLabel(person)}>{squadLabel(person)}</td>
    <td><span className={`rm-status ${person.status === 'active' ? 'active' : 'other'}`}>
      {person.status === 'active' ? '복무 중' : person.status === 'on_leave' ? '휴가 중' : person.status}
    </span></td>
    <td>{person.mobilization_status ?? '—'}</td><td>{person.service_year === null ? '—' : `${person.service_year}년차`}</td>
  </tr>
  const pageSize = 20
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const actualPage = Math.min(page, pageCount)
  const pageRows = sorted.slice((actualPage - 1) * pageSize, actualPage * pageSize)
  const selected = people.find(person => person.military_number === selectedId) ?? null
  const checkedOnPage = pageRows.length > 0 && pageRows.every(person => checked.has(person.military_number))
  const squadLabel = (person: ResourcePerson) => person.squad_id === null
    ? '-' : (squadNames.get(person.squad_id) ?? `${person.squad_id}번 분대`)

  const openPerson = (id: string) => {
    setRecords([]); setDetailError(''); setActionError(''); setRecordForm(null); setEditingRecord(null)
    setDetailTab('progress'); setDetailLoading(true); setSelectedId(id)
  }
  const closePerson = () => {
    setSelectedId(null); setRecords([]); setDetailError(''); setActionError(''); setRecordForm(null); setEditingRecord(null)
  }
  const autoAssignPerson = async () => {
    if (!selected || selected.squad_id !== null || assignmentLoading) return
    setActionError('')
    setAssignmentLoading(true)
    try {
      const recommendationsResponse = await fetch(`${API_BASE}/squads/assignments/recommendations/${encodeURIComponent(selected.military_number)}`)
      if (!recommendationsResponse.ok) throw new Error(await responseError(recommendationsResponse, '자동편성 추천을 불러오지 못했습니다.'))
      const recommendations = await recommendationsResponse.json() as { squad_id: number }[]
      if (recommendations.length === 0) throw new Error('호환되는 분대가 없습니다. 먼저 편제에 분대를 추가하세요.')

      const response = await fetch(`${API_BASE}/squads/assignments/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assignments: [{ person_id: selected.military_number, squad_id: recommendations[0].squad_id }] }),
      })
      if (!response.ok) throw new Error(await responseError(response, '자동편성에 실패했습니다.'))
      setActionError('')
      onDataChanged()
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : '자동편성에 실패했습니다.')
    } finally {
      setAssignmentLoading(false)
    }
  }
  const refreshDetails = () => {
    if (!selectedId) return
    setDetailError('')
    setDetailLoading(true)
    fetch(`${API_BASE}/reservists/${encodeURIComponent(selectedId)}/training-hours`)
      .then(async response => {
        if (!response.ok) throw new Error(await responseError(response, '훈련 정보를 불러오지 못했습니다.'))
        return response.json() as Promise<{ records: TrainingRecord[]; progress: TrainingProgress[] }>
      })
      .then(result => { setRecords(result.records ?? []); setTrainingProgress(result.progress ?? []) })
      .catch(cause => setActionError(cause instanceof Error ? cause.message : '훈련 정보를 불러오지 못했습니다.'))
      .finally(() => setDetailLoading(false))
  }
  const startAddRecord = () => {
    const serviceYear = selected?.service_year && selected.service_year <= 8 ? selected.service_year : 1
    setActionError(''); setEditingRecord(null); setRecordForm({
      service_year: serviceYear, training_year: new Date().getFullYear(), training_type: '기본훈련',
      training_round: 1, attendance_status: 'postponed', training_hours: 0, notes: '',
    })
    setDetailTab('records')
  }
  const startEditRecord = (record: TrainingRecord) => {
    setActionError(''); setEditingRecord(record.id); setRecordForm({
      service_year: record.education_year, training_year: record.training_year ?? new Date().getFullYear(),
      training_type: record.training_type, training_round: record.training_round,
      attendance_status: record.attendance_status, training_hours: record.training_hours, notes: record.notes ?? '',
    })
    setDetailTab('records')
  }
  const saveRecord = async () => {
    if (!selectedId || !recordForm) return
    const url = editingRecord === null
      ? `${API_BASE}/reservists/${encodeURIComponent(selectedId)}/training-hours`
      : `${API_BASE}/reservists/${encodeURIComponent(selectedId)}/training-hours/${editingRecord}`
    try {
      const response = await fetch(url, {
        method: editingRecord === null ? 'POST' : 'PATCH',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(recordForm),
      })
      if (!response.ok) throw new Error(await responseError(response, '훈련 기록 저장에 실패했습니다.'))
      setRecordForm(null); setEditingRecord(null); refreshDetails()
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : '훈련 기록 저장에 실패했습니다.') }
  }
  const deleteRecord = async (id: number) => {
    if (!selectedId || !window.confirm('이 훈련 기록을 삭제하시겠습니까?')) return
    try {
      const response = await fetch(`${API_BASE}/reservists/${encodeURIComponent(selectedId)}/training-hours/${id}`, { method: 'DELETE' })
      if (!response.ok) throw new Error(await responseError(response, '훈련 기록 삭제에 실패했습니다.'))
      refreshDetails()
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : '훈련 기록 삭제에 실패했습니다.') }
  }
  const submitCreatePerson = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setCreatePersonError('')
    const previousHours = createPersonForm.previous_training_hours.trim()
    if (!createPersonForm.military_number.trim() || !createPersonForm.name.trim()) {
      setCreatePersonError('군번과 이름은 필수 입력 항목입니다.')
      return
    }
    if (previousHours && (!Number.isInteger(Number(previousHours)) || Number(previousHours) < 0)) {
      setCreatePersonError('이전 훈련시간은 0 이상의 정수로 입력하세요.')
      return
    }

    setCreatePersonLoading(true)
    try {
      const payload = {
        ...createPersonForm,
        military_number: createPersonForm.military_number.trim(),
        name: createPersonForm.name.trim(),
        unit: createPersonForm.unit.trim() || null,
        specialty: createPersonForm.specialty.trim() || null,
        previous_training_hours: previousHours ? Number(previousHours) : null,
      }
      const response = await fetch(`${API_BASE}/persons`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(await responseError(response, '인원 등록에 실패했습니다.'))

      setCreatePersonOpen(false)
      setCreatePersonForm(initialCreatePersonForm)
      setInput(''); setUnit(''); setStatus(''); setPosition(''); setYear('')
      setAppliedFilters({ query: '', unit: '', status: '', position: '', year: '' })
      setPage(1); setChecked(new Set())
      onDataChanged()
    } catch (cause) {
      setCreatePersonError(cause instanceof Error ? cause.message : '인원 등록에 실패했습니다.')
    } finally {
      setCreatePersonLoading(false)
    }
  }
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
    setGroupTab('none')
    setGroupValue(null)
  }
  const metrics = [
    { label: '전체 대상자', number: people.length, description: '전체 예비군 등록 인원', color: 'blue' },
    { label: '분대 편성', number: people.filter(person => person.squad_id !== null).length, description: '소속 분대가 있는 인원', color: 'blue' },
    { label: '미편성', number: people.filter(person => person.squad_id === null).length, description: '소속 분대가 없는 인원', color: 'orange' },
    { label: '복무 중', number: people.filter(person => person.status === 'active').length, description: '현재 등록 상태 기준', color: 'green' },
  ]

  return <div className="rm-roster-layout">
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
        <nav className="rm-group-tabs" aria-label="편성인원목록 정렬 기준">
          {groupTabs.map(tab => <button key={tab.key} type="button"
            className={groupTab === tab.key ? 'is-active' : ''}
            aria-current={groupTab === tab.key ? 'page' : undefined}
            onClick={() => selectGroupTab(tab.key)}>{tab.label}</button>)}
        </nav>
        {groupTab !== 'none' && <nav className="rm-group-options" aria-label="세부 목록 선택">
          {groupOptions.length === 0 ? <span className="rm-group-options-empty">해당 조건의 목록이 없습니다.</span>
            : groupOptions.map(value => <button key={value} type="button"
              className={groupValue === value ? 'is-active' : ''}
              aria-current={groupValue === value ? 'page' : undefined}
              onClick={() => selectGroupValue(value)}>{value}</button>)}
        </nav>}
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
          {copilotFilter && <span className="rm-copilot-filter">Copilot: {copilotFilter.label}
            <button type="button" onClick={onClearCopilotFilter} aria-label="Copilot 필터 해제" title="필터 해제">×</button></span>}
          <span className="rm-list-total">총 {filtered.length.toLocaleString('ko-KR')}명</span>
          <button type="button" className="rm-roster-add-button" onClick={() => {
            setCreatePersonForm(initialCreatePersonForm)
            setCreatePersonError('')
            setCreatePersonOpen(true)
          }}>+ 인원 추가</button>
        </div>
        {loading ? <p className="rm-list-message">인원 목록을 불러오는 중입니다.</p>
          : error ? <p className="rm-list-message rm-error">{error}</p>
          : <div className="rm-list-scroll"><table className="rm-person-table">
            <colgroup>{[4, 4, 10, 12, 6, 6, 10, 16, 10, 14, 8].map((width, index) => <col key={rosterColumns[index].key} style={{ width: `${width}%` }} />)}</colgroup>
            <thead><tr>{rosterColumns.map(column => <th key={column.key} scope="col"
              aria-sort={sort.key === column.key ? sort.direction : 'none'}>
              <button type="button" className="rm-sort-button" onClick={() => changeSort(column.key)}
                aria-label={`${column.label}, ${sort.key === column.key && sort.direction === 'ascending' ? '내림차순' : '오름차순'} 정렬`}>
                <span>{column.label}</span>
                <span className="rm-sort-indicator" aria-hidden="true">{sort.key === column.key ? (sort.direction === 'ascending' ? '▼' : '▲') : ''}</span>
              </button>
            </th>)}</tr></thead>
            <tbody>{pageRows.map(renderPersonRow)}</tbody>
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
    {selected && <div className="rm-person-detail-backdrop" onMouseDown={event => {
      if (event.target === event.currentTarget) closePerson()
    }}>
      <section className="rm-person-detail" role="dialog" aria-modal="true" aria-label="대상자 상세 정보">
      <header className="rm-detail-heading"><h2>대상자 상세 정보</h2><div className="rm-detail-heading-actions">
        {selected.squad_id === null && <button type="button" className="rm-detail-auto-assign"
          disabled={assignmentLoading || selected.status !== 'active' || selected.service_year === null}
          title={selected.status !== 'active' ? '복무 중인 인원만 자동편성할 수 있습니다.' : selected.service_year === null ? '복무연차 정보가 필요합니다.' : '호환되는 분대에 자동편성'}
          onClick={() => void autoAssignPerson()}>{assignmentLoading ? '편성 중...' : '자동편성'}</button>}
        <button type="button" onClick={closePerson}>닫기</button>
      </div></header>
      <div className="rm-detail-body">
        <div className="rm-detail-person"><span className="rm-detail-avatar" aria-hidden="true">♙</span><div>
          <h3>{selected.name}</h3><p>군번: {selected.military_number}</p>
          <span className="rm-detail-tag">{squadLabel(selected)}</span>
        </div></div>
        <PersonProfileFields key={selected.military_number} person={selected} squadName={squadLabel(selected)} onSaved={updated => {
          const oldNumber = selected.military_number
          setPeople(current => current.map(person => person.military_number === oldNumber ? { ...person, ...updated } : person))
          setSelectedId(current => current === oldNumber ? updated.military_number : current)
          setChecked(current => { const next = new Set(current); if (next.delete(oldNumber)) next.add(updated.military_number); return next })
          onDataChanged()
        }} />
        <nav className="rm-detail-tabs" aria-label="훈련 상세 메뉴">
          <button type="button" className={detailTab === 'progress' ? 'is-active' : ''} onClick={() => setDetailTab('progress')}>훈련 현황</button>
          <button type="button" className={detailTab === 'results' ? 'is-active' : ''} onClick={() => setDetailTab('results')}>훈련 결과</button>
          <button type="button" className={detailTab === 'records' ? 'is-active' : ''} onClick={() => setDetailTab('records')}>훈련 기록 ({records.length})</button>
        </nav>
        {actionError && <p className="rm-detail-note rm-error">{actionError}</p>}
        {detailLoading ? <p className="rm-detail-note">훈련 정보를 불러오는 중입니다.</p>
          : detailError ? <p className="rm-detail-note rm-error">{detailError}</p>
          : detailTab === 'progress' ? <TrainingProgressPanel currentYear={selected.service_year} progress={trainingProgress} />
          : detailTab === 'results' ? <TrainingResultsPanel currentYear={selected.service_year} records={records} />
          : <TrainingRecordsPanel records={records} form={recordForm} editingId={editingRecord}
              onAdd={startAddRecord} onEdit={startEditRecord} onChange={setRecordForm} onCancel={() => { setRecordForm(null); setEditingRecord(null) }}
              onSave={saveRecord} onDelete={deleteRecord} />}
        <p className="rm-detail-note">전화번호·주소·이메일은 현재 인원 API에서 제공하지 않습니다.</p>
      </div>
      </section>
    </div>}
    {createPersonOpen && <div className="rm-create-person-backdrop" onMouseDown={event => {
      if (event.target === event.currentTarget && !createPersonLoading) setCreatePersonOpen(false)
    }}>
      <section className="rm-create-person-dialog" role="dialog" aria-modal="true" aria-labelledby="rm-create-person-title">
        <header><div><span>NEW RESERVIST</span><h2 id="rm-create-person-title">신규 인원 추가</h2></div>
          <button type="button" aria-label="닫기" disabled={createPersonLoading} onClick={() => setCreatePersonOpen(false)}>×</button>
        </header>
        <form onSubmit={submitCreatePerson}>
          <div className="rm-create-person-grid">
            <label>군번 *<input autoFocus required value={createPersonForm.military_number} onChange={event => setCreatePersonForm(form => ({ ...form, military_number: event.target.value }))} /></label>
            <label>이름 *<input required value={createPersonForm.name} onChange={event => setCreatePersonForm(form => ({ ...form, name: event.target.value }))} /></label>
            <label>군종<select value={createPersonForm.branch} onChange={event => setCreatePersonForm(form => ({ ...form, branch: event.target.value }))}>{personBranches.map(branch => <option key={branch}>{branch}</option>)}</select></label>
            <label>계급<select value={createPersonForm.rank} onChange={event => setCreatePersonForm(form => ({ ...form, rank: event.target.value }))}>{personRanks.map(rank => <option key={rank}>{rank}</option>)}</select></label>
            <label>복무연차<input type="number" min="1" max="8" required value={createPersonForm.service_year} onChange={event => setCreatePersonForm(form => ({ ...form, service_year: Number(event.target.value) }))} /></label>
            <label>동원상태<select value={createPersonForm.mobilization_status} onChange={event => setCreatePersonForm(form => ({ ...form, mobilization_status: event.target.value }))}>{personMobilizationStatuses.filter(status => createPersonForm.service_year > 4 || status !== '해당없음').map(status => <option key={status}>{status}</option>)}</select></label>
            <label>직책 *<input required value={createPersonForm.position} onChange={event => setCreatePersonForm(form => ({ ...form, position: event.target.value }))} /></label>
            <label>소속부대<input value={createPersonForm.unit} onChange={event => setCreatePersonForm(form => ({ ...form, unit: event.target.value }))} /></label>
            <label>주특기<input value={createPersonForm.specialty} onChange={event => setCreatePersonForm(form => ({ ...form, specialty: event.target.value }))} /></label>
            <label>이전 훈련시간<input type="number" min="0" step="1" value={createPersonForm.previous_training_hours} onChange={event => setCreatePersonForm(form => ({ ...form, previous_training_hours: event.target.value }))} /><small>이수시간이 있으면 전입 인원으로 등록됩니다.</small></label>
            <label>상태<select value={createPersonForm.status} onChange={event => setCreatePersonForm(form => ({ ...form, status: event.target.value }))}><option value="active">복무 중</option><option value="on_leave">휴가 중</option></select></label>
          </div>
          <p className="rm-create-person-note">새 인원은 미편성 상태로 등록됩니다. 부대 배정은 전투편성기구도에서 진행할 수 있습니다.</p>
          {createPersonError && <p className="rm-create-person-error" role="alert">{createPersonError}</p>}
          <footer><button type="button" disabled={createPersonLoading} onClick={() => setCreatePersonOpen(false)}>취소</button>
            <button type="submit" disabled={createPersonLoading}>{createPersonLoading ? '등록 중...' : '인원 등록'}</button></footer>
        </form>
      </section>
    </div>}
  </div>
}

function TrainingProgressPanel({ currentYear, progress }: { currentYear: number | null; progress: TrainingProgress[] }) {
  const current = progress.find(item => item.service_year === currentYear)
  return <div className="rm-training-panel">
    <div className="rm-training-panel-heading"><h4>연차별 훈련 현황</h4><span>현재 및 과거 연차</span></div>
    {current && <section className={`rm-current-training ${current.prosecution_risk ? 'is-risk' : ''}`}>
      <div><span>현재 {current.service_year}년차 훈련시간</span><strong>{current.completed_hours} / {current.required_hours}시간</strong></div>
      <b>잔여 {current.remaining_hours}시간</b>
    </section>}
    <div className="rm-training-progress-list">
      {progress.filter(item => item.service_year > 0 && (currentYear === null || item.service_year <= currentYear)).map(item => {
        const isPreviousIncomplete = currentYear !== null && item.service_year < currentYear && item.remaining_hours > 0
        return <div className={`rm-training-progress-row ${item.prosecution_risk ? 'is-risk' : isPreviousIncomplete ? 'is-incomplete' : ''}`} key={item.service_year}>
        <div><strong>{item.service_year}년차</strong><small>{item.training_plan.map(plan => `${plan.name} ${plan.hours}시간`).join(', ') || '훈련 대상 아님'}</small></div>
        <span>{item.completed_hours}/{item.required_hours}시간</span>
        <b className={isPreviousIncomplete ? 'incomplete-label' : ''}>{isPreviousIncomplete ? '훈련 미이수' : item.training_status}</b>
      </div>
      })}
    </div>
  </div>
}

type RoundStatusKind = 'attended' | 'completed' | 'absent' | 'postponed' | 'hold' | 'pending'
const roundStatusLabel: Record<RoundStatusKind, string> = {
  attended: '참석', completed: '이수', absent: '무단불참', postponed: '연기', hold: '보류', pending: '미처리',
}
const attendanceKind = (status: string | undefined): RoundStatusKind => {
  if (!status) return 'pending'
  if (['이수', 'completed'].includes(status)) return 'completed'
  if (['참석', 'attended'].includes(status)) return 'attended'
  if (['무단불참', '무단_불참', 'unexcused_absence'].includes(status)) return 'absent'
  if (['연기', 'postponed'].includes(status)) return 'postponed'
  if (['보류', 'round_hold'].includes(status)) return 'hold'
  return 'pending'
}
type RoundCell = { round: number; kind: RoundStatusKind; label: string }
// 1차/2차/3차 진행 규칙은 동원훈련Ⅱ형에만 적용됩니다.
function buildYearRounds(records: TrainingRecord[], year: number): RoundCell[] {
  // Keep only the latest entry per round; earlier attempts are superseded.
  const byRound = new Map<number, TrainingRecord>()
  for (const record of records) {
    if (record.education_year !== year) continue
    const existing = byRound.get(record.training_round)
    if (!existing || record.id > existing.id) byRound.set(record.training_round, record)
  }
  const cells: RoundCell[] = []
  let carriedFromRound: number | null = null
  for (let round = 1; round <= 3; round++) {
    const record = byRound.get(round)
    const kind = attendanceKind(record?.attendance_status)
    if (kind === 'hold') {
      // 보류: exempt this round's training hour, do not carry it forward.
      cells.push({ round, kind, label: '보류 (면제)' })
      carriedFromRound = null
      continue
    }
    if (kind === 'postponed') {
      // 연기: push this round's obligation onto the next round.
      cells.push({ round, kind, label: round < 3 ? `연기 (${round + 1}차로 이월)` : '연기' })
      carriedFromRound = round < 3 ? round : null
      continue
    }
    if (kind === 'pending' && carriedFromRound !== null) {
      cells.push({ round, kind: 'pending', label: `${carriedFromRound}차 이월분 대기` })
      carriedFromRound = null
      continue
    }
    // 참석/이수/무단불참은 그 차수에서 종결되며, 무단불참은 다음 차수로 계속 이어집니다.
    cells.push({ round, kind, label: roundStatusLabel[kind] })
    carriedFromRound = null
  }
  return cells
}
// 동원훈련Ⅱ형이 아닌 훈련종류는 차수 구분 없이 하나의 결과만 표시합니다.
function buildSingleStatus(records: TrainingRecord[]): RoundCell {
  const latest = records.reduce<TrainingRecord | null>((best, record) => (!best || record.id > best.id ? record : best), null)
  const kind = attendanceKind(latest?.attendance_status)
  return { round: 0, kind, label: roundStatusLabel[kind] }
}
function TrainingResultsPanel({ currentYear, records }: { currentYear: number | null; records: TrainingRecord[] }) {
  const years = currentYear === null ? [] : Array.from({ length: currentYear }, (_, index) => index + 1)
  return <div className="rm-training-panel">
    <div className="rm-training-panel-heading"><h4>차수별 훈련 결과</h4><span>현재 및 과거 연차 · 동원훈련Ⅱ형만 1차~3차</span></div>
    {years.length === 0 ? <p className="rm-detail-note">해당 연차의 훈련 결과가 없습니다.</p> : <div className="rm-round-grid">
      {years.map(year => {
        const yearRecords = records.filter(record => record.education_year === year)
        const typeII = yearRecords.filter(record => record.training_type === '동원훈련Ⅱ형')
        const otherTypes = [...new Set(yearRecords.filter(record => record.training_type !== '동원훈련Ⅱ형').map(record => record.training_type))]
        const hasAnyRecord = typeII.length > 0 || otherTypes.length > 0
        return <div className="rm-round-grid-row" key={year}>
          <span className="rm-round-grid-year">{year}년차</span>
          <div className="rm-round-grid-groups">
            {typeII.length > 0 && <div className="rm-round-grid-type">
              <span className="rm-round-grid-type-label">동원훈련Ⅱ형</span>
              <div className="rm-round-grid-cells">
                {buildYearRounds(typeII, year).map(cell => <div key={cell.round} className={`rm-round-cell rm-round-cell--${cell.kind}`}>
                  <b>{cell.round}차</b><span>{cell.label}</span>
                </div>)}
              </div>
            </div>}
            {otherTypes.map(type => {
              const cell = buildSingleStatus(yearRecords.filter(record => record.training_type === type))
              return <div className="rm-round-grid-type" key={type}>
                <span className="rm-round-grid-type-label">{type}</span>
                <div className="rm-round-grid-cells rm-round-grid-cells--single">
                  <div className={`rm-round-cell rm-round-cell--${cell.kind}`}><b>결과</b><span>{cell.label}</span></div>
                </div>
              </div>
            })}
            {!hasAnyRecord && <div className="rm-round-grid-type">
              <div className="rm-round-grid-cells rm-round-grid-cells--single">
                <div className="rm-round-cell rm-round-cell--pending"><b>결과</b><span>미처리</span></div>
              </div>
            </div>}
          </div>
        </div>
      })}
    </div>}
  </div>
}

function TrainingRecordsPanel({
  records, form, editingId, onAdd, onEdit, onChange, onCancel, onSave, onDelete,
}: {
  records: TrainingRecord[]
  form: TrainingRecordForm | null
  editingId: number | null
  onAdd: () => void
  onEdit: (record: TrainingRecord) => void
  onChange: (form: TrainingRecordForm | null) => void
  onCancel: () => void
  onSave: () => void
  onDelete: (id: number) => void
}) {
  const update = (key: keyof TrainingRecordForm, value: string | number) => {
    if (form) onChange({ ...form, [key]: value })
  }
  return <div className="rm-training-panel">
    <div className="rm-training-panel-heading"><h4>훈련 기록</h4><button type="button" className="rm-btn rm-btn-primary" onClick={onAdd}>+ 기록 추가</button></div>
    {form && <div className="rm-record-editor">
      <label>복무연차<input type="number" min="1" max="8" value={form.service_year} onChange={event => update('service_year', Number(event.target.value))} /></label>
      <label>훈련연도<input type="number" value={form.training_year} onChange={event => update('training_year', Number(event.target.value))} /></label>
      <label>훈련종류<select value={form.training_type} onChange={event => update('training_type', event.target.value)}>{trainingTypes.map(type => <option key={type}>{type}</option>)}</select></label>
      <label>차수<select value={form.training_round} onChange={event => update('training_round', Number(event.target.value))}><option value={1}>1차</option><option value={2}>2차</option><option value={3}>3차</option></select></label>
      <label>출결<select value={form.attendance_status} onChange={event => update('attendance_status', event.target.value)}><option value="completed">이수</option><option value="참석">참석</option><option value="무단불참">무단불참</option><option value="postponed">연기</option><option value="보류">보류</option></select></label>
      <label>훈련시간<input type="number" min="0" value={form.training_hours} onChange={event => update('training_hours', Number(event.target.value))} /></label>
      <label className="wide">메모<input value={form.notes} onChange={event => update('notes', event.target.value)} /></label>
      <div className="rm-record-actions wide"><button type="button" className="rm-btn" onClick={onCancel}>취소</button><button type="button" className="rm-btn rm-btn-primary" onClick={onSave}>{editingId === null ? '추가' : '저장'}</button></div>
    </div>}
    {records.length === 0 ? <p className="rm-detail-note">등록된 훈련 기록이 없습니다.</p> : <div className="rm-record-table-wrap"><table className="rm-record-table"><thead><tr><th>연차</th><th>훈련연도</th><th>종류</th><th>차수</th><th>출결</th><th>시간</th><th>관리</th></tr></thead><tbody>{records.map(record => <tr key={record.id}><td>{record.education_year}년차</td><td>{record.training_year ?? '-'}</td><td>{record.training_type}</td><td>{record.training_round}차</td><td>{record.attendance_status}</td><td>{record.training_hours}시간</td><td><button type="button" className="rm-record-action" onClick={() => onEdit(record)}>수정</button><button type="button" className="rm-record-action danger" onClick={() => onDelete(record.id)}>삭제</button></td></tr>)}</tbody></table></div>}
    <p className="rm-detail-note">훈련시간은 해당 연차의 목표시간을 초과할 수 없습니다.</p>
  </div>
}

