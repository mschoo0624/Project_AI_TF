type AssignmentRecommendation = { squad_id: number; squad_name: string; current_count: number; same_position_count: number; same_tier_count: number; reason: string }
import { useEffect, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import './App.css'

type Person = {
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

type TrainingPlanItem = { name: string; hours: number }

type TrainingProgress = {
  service_year: number
  mobilization_status: string | null
  personnel_category: string
  training_plan: TrainingPlanItem[]
  target_hours: number
  carryover_hours?: number
  required_hours?: number
  completed_hours: number
  remaining_hours: number
  prosecution_risk: boolean
  completed: boolean
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
  origin_type: string
  service_year: number
  position: string
  mobilization_status: string
  status: string
  previous_training_hours: string
}

const initialCreatePersonForm: CreatePersonForm = {
  military_number: '',
  name: '',
  branch: '육군',
  rank: '병장',
  unit: '',
  specialty: '',
  origin_type: '병사',
  service_year: 1,
  position: '소총수',
  mobilization_status: '동원지정',
  status: 'active',
  previous_training_hours: '',
}

function suggestPositionForSpecialty(specialty: string): string | null {
  const normalized = specialty.trim()
  if (!normalized) return null

  const compact = normalized.replace(/\s+/g, '').toLowerCase()
  const code = normalized.replace(/\D/g, '')
  const candidates = [normalized, compact, code, normalized.toLowerCase(), compact.toLowerCase()]

  const mapping: Record<string, string> = {
    행정: '행정병',
    행정병: '행정병',
    '3111101': '행정병',
    '311102': '행정병',
    병기: '병기취급병',
    병기취급: '병기취급병',
    병기취급병: '병기취급병',
    '222101': '병기취급병',
    '222102': '병기취급병',
    통신: '통신병',
    통신병: '통신병',
    '171101': '통신병',
    '171102': '통신병',
    '171104': '통신병',
    '171106': '통신병',
    의무: '의무병',
    의무병: '의무병',
    '411101': '의무병',
    '411102': '의무병',
    '411103': '의무병',
    '411104': '의무병',
    '411105': '의무병',
    '411106': '의무병',
    운전: '운전병',
    운전병: '운전병',
    '241102': '운전병',
    '241103': '운전병',
    '241104': '운전병',
    '231101': '운전병',
    보급: '보급병',
    보급병: '보급병',
    '231103': '보급병',
    '231104': '보급병',
    '231105': '보급병',
  }

  for (const candidate of candidates) {
    if (mapping[candidate]) return mapping[candidate]
    if (mapping[candidate.toLowerCase()]) return mapping[candidate.toLowerCase()]
  }

  return null
}

type Tab = 'profile' | 'progress' | 'records'
type Squad = { id: number; name: string; description: string | null; person_count: number; breakdown?: Record<string, number> }
type AssignmentResult = {
  squad_id: number
  positions: Record<string, { requested: number; assigned: { military_number: string; name: string }[]; shortfall: number }>
  total_requested: number
  total_assigned: number
  total_shortfall: number
}
type AssignmentQuotas = Record<string, Record<string, Record<string, number>>>
type AssignmentCandidate = { military_number: string; name: string; position: string; specialty: string | null; service_year: number | null; origin_type?: string | null; personnel_category?: string; tier: string; branch: string; category: string }
type AssignmentCandidates = Record<string, Record<string, AssignmentCandidate[]>>
type ProposedAssignment = AssignmentCandidate & { squad_id: number }
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const branches = ['육군', '해군', '공군', '해병대']
const statuses = ['active', 'on_leave']
const mobilizationStatuses = ['동원지정', '동원미지정', '학생예비군', '일부보류', '해당없음']
const trainingTypes = ['기본훈련', '동원훈련Ⅰ형', '동원훈련Ⅱ형', '작계훈련(전·후반기)']
const assignmentPositions = ['행정병', '통신병', '의무병', '운전병', '보급병']
const personnelCategories = ['병사', '부사관', '장교']
const assignmentBranches = ['육군', '해군', '해병대', '공군']
const rankCategoryMap: Record<string, string[]> = {
  병사: ['이병', '일병', '상병', '병장'],
  부사관: ['하사', '중사', '상사'],
  장교: ['소위', '중위', '대위'],
}
const originTypeOptions = ['병사', '부사관', '장교']

async function responseError(response: Response, fallback: string) {
  const body = await response.text()
  if (!body) return fallback
  try {
    const parsed = JSON.parse(body) as { detail?: string }
    return parsed.detail ?? fallback
  } catch {
    return body === 'Internal Server Error' ? fallback : body
  }
}

function getRequiredTrainingHoursForYear(progress: TrainingProgress[], serviceYear: number) {
  return progress.find((item) => item.service_year === serviceYear)?.target_hours ?? 0
}

function App() {
  const [search, setSearch] = useState('')
  const [branch, setBranch] = useState('')
  const [status, setStatus] = useState('')
  const [mobilizationStatus, setMobilizationStatus] = useState('')
  const [people, setPeople] = useState<Person[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null)
  const [progress, setProgress] = useState<TrainingProgress[]>([])
  const [records, setRecords] = useState<TrainingRecord[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [tab, setTab] = useState<Tab>('profile')
  const [editingPerson, setEditingPerson] = useState(false)
  const [personForm, setPersonForm] = useState<Partial<Person>>({})
  const [editingRecord, setEditingRecord] = useState<number | null>(null)
  const [recordForm, setRecordForm] = useState<TrainingRecordForm | null>(null)
  const [addingRecord, setAddingRecord] = useState(false)
  const [actionError, setActionError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [page, setPage] = useState<'lookup' | 'assignment'>('lookup')
  const [squads, setSquads] = useState<Squad[]>([])
  const [assignmentSquad, setAssignmentSquad] = useState('1')
  const [quotas, setQuotas] = useState<AssignmentQuotas>(Object.fromEntries(assignmentBranches.map((branch) => [branch, Object.fromEntries(assignmentPositions.map((position) => [position, { 병사: 1, 부사관: 0, 장교: 0 }]))])) as AssignmentQuotas)
  const [candidates, setCandidates] = useState<AssignmentCandidates>({})
  const [assignmentResult, setAssignmentResult] = useState<AssignmentResult | null>(null)
  const [assignmentLoading, setAssignmentLoading] = useState(false)
  const [assignmentError, setAssignmentError] = useState('')
  const [assignmentTab, setAssignmentTab] = useState('육군-병사')
  const [proposal, setProposal] = useState<ProposedAssignment[]>([])

  const [addingPerson, setAddingPerson] = useState(false)
  const [createPersonForm, setCreatePersonForm] = useState<CreatePersonForm>(initialCreatePersonForm)
  const [createPersonLoading, setCreatePersonLoading] = useState(false)
  const [createPersonError, setCreatePersonError] = useState('')
  const [newArrival, setNewArrival] = useState<{ person: Person; recommendations: AssignmentRecommendation[] } | null>(null)

  useEffect(() => {
    if (page !== 'assignment') return
    Promise.all([fetch(`${API_BASE}/squads`), fetch(`${API_BASE}/squads/assignment-candidates`)
    ])
      .then(async ([squadsResponse, candidatesResponse]) => {
        if (!squadsResponse.ok) throw new Error(await responseError(squadsResponse, '분대 목록을 불러오지 못했습니다.'))
        if (!candidatesResponse.ok) throw new Error(await responseError(candidatesResponse, '가용 인원을 불러오지 못했습니다.'))
        return [await squadsResponse.json() as Squad[], await candidatesResponse.json() as AssignmentCandidates] as const
      })
      .then(([squadData, candidateData]) => { setSquads(squadData); setCandidates(candidateData) })
      .catch((error: unknown) => setAssignmentError(error instanceof Error ? error.message : '분대 목록을 불러오지 못했습니다.'))
  }, [page])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setListLoading(true)
      setListError('')
      const params = new URLSearchParams()
      if (search.trim()) params.set('query', search.trim())
      if (branch) params.set('branch', branch)
      if (status) params.set('status', status)
      if (mobilizationStatus) params.set('mobilization_status', mobilizationStatus)
      try {
        const response = await fetch(`${API_BASE}/persons?${params}`, { signal: controller.signal })
        if (!response.ok) throw new Error('인원 목록을 불러오지 못했습니다.')
        setPeople(await response.json() as Person[])
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setListError(error instanceof Error ? error.message : '인원 목록을 불러오지 못했습니다.')
      } finally {
        if (!controller.signal.aborted) setListLoading(false)
      }
    }, 300)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [search, branch, status, mobilizationStatus, refreshKey])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    const loadDetail = async () => {
      setDetailLoading(true)
      setDetailError('')
      try {
        const [personResponse, trainingResponse] = await Promise.all([
          fetch(`${API_BASE}/persons/${selectedId}`, { signal: controller.signal }),
          fetch(`${API_BASE}/reservists/${selectedId}/training-hours`, { signal: controller.signal }),
        ])
        if (personResponse.status === 404 || trainingResponse.status === 404) throw new Error('해당 예비군을 찾을 수 없습니다.')
        if (!personResponse.ok || !trainingResponse.ok) throw new Error('상세 정보를 불러오지 못했습니다.')
        const training = await trainingResponse.json() as { progress: TrainingProgress[]; records: TrainingRecord[] }
        setSelectedPerson(await personResponse.json() as Person)
        setProgress(training.progress)
        setRecords(training.records)
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setDetailError(error instanceof Error ? error.message : '상세 정보를 불러오지 못했습니다.')
      } finally {
        if (!controller.signal.aborted) setDetailLoading(false)
      }
    }
    void loadDetail()
    return () => controller.abort()
  }, [selectedId, refreshKey])

  const closeModal = () => { setSelectedId(null); setSelectedPerson(null); setProgress([]); setRecords([]); setEditingPerson(false); setEditingRecord(null); setRecordForm(null); setAddingRecord(false); setActionError('') }
  const openDetail = (person: Person) => { setSelectedId(person.military_number); setTab('profile'); setActionError('') }
  const startPersonEdit = () => { if (!selectedPerson) return; setPersonForm(selectedPerson); setEditingPerson(true); setActionError('') }
  const savePerson = async () => {
    if (!selectedId) return
    try {
      const response = await fetch(`${API_BASE}/persons/${selectedId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(personForm) })
      if (!response.ok) throw new Error('인원 정보 수정에 실패했습니다.')
      setSelectedPerson(await response.json() as Person); setEditingPerson(false); setRefreshKey((value) => value + 1)
    } catch (error) { setActionError(error instanceof Error ? error.message : '인원 정보 수정에 실패했습니다.') }
  }
  const deletePerson = async () => {
    if (!selectedId || !window.confirm('이 예비군을 삭제하시겠습니까?')) return
    try {
      const response = await fetch(`${API_BASE}/persons/${selectedId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('인원 삭제에 실패했습니다.')
      closeModal(); setRefreshKey((value) => value + 1)
    } catch (error) { setActionError(error instanceof Error ? error.message : '인원 삭제에 실패했습니다.') }
  }
  const startRecordEdit = (record: TrainingRecord) => {
    setEditingRecord(record.id)
    setAddingRecord(false)
    setRecordForm({ service_year: record.education_year, training_year: record.training_year ?? record.education_year, training_type: record.training_type, training_round: record.training_round, attendance_status: record.attendance_status, training_hours: record.training_hours, notes: record.notes ?? '' })
  }
  const saveRecord = async (recordId: number) => {
    if (!selectedId) return
    if (!recordForm) return
    try {
      const response = await fetch(`${API_BASE}/reservists/${selectedId}/training-hours/${recordId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ service_year: recordForm.service_year, training_year: recordForm.training_year, training_type: recordForm.training_type, training_round: recordForm.training_round, attendance_status: recordForm.attendance_status, training_hours: recordForm.training_hours, notes: recordForm.notes || null }) })
      if (!response.ok) throw new Error(await responseError(response, '훈련 기록 수정에 실패했습니다.'))
      setEditingRecord(null); setRecordForm(null); setRefreshKey((value) => value + 1)
    } catch (error) { setActionError(error instanceof Error ? error.message : '훈련 기록 수정에 실패했습니다.') }
  }
  const addRecord = async () => {
    if (!selectedId || !recordForm) return
    try {
      const response = await fetch(`${API_BASE}/reservists/${selectedId}/training-hours`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(recordForm) })
      if (!response.ok) throw new Error(await responseError(response, '훈련 기록 추가에 실패했습니다.'))
      setAddingRecord(false); setRecordForm(null); setRefreshKey((value) => value + 1)
    } catch (error) { setActionError(error instanceof Error ? error.message : '훈련 기록 추가에 실패했습니다.') }
  }
  const deleteRecord = async (recordId: number) => {
    if (!selectedId || !window.confirm('이 훈련 기록을 삭제하시겠습니까?')) return
    try {
      const response = await fetch(`${API_BASE}/reservists/${selectedId}/training-hours/${recordId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('훈련 기록 삭제에 실패했습니다.')
      setRefreshKey((value) => value + 1)
    } catch (error) { setActionError(error instanceof Error ? error.message : '훈련 기록 삭제에 실패했습니다.') }
  }

  const submitCreatePerson = async () => {
    setCreatePersonError('')
    if (!createPersonForm.military_number.trim() || !createPersonForm.name.trim()) {
      setCreatePersonError('군번과 이름은 필수 입력 항목입니다.')
      return
    }
    setCreatePersonLoading(true)
    try {
      const hoursInput = createPersonForm.previous_training_hours.trim()
      const payload = {
        military_number: createPersonForm.military_number.trim(),
        name: createPersonForm.name.trim(),
        branch: createPersonForm.branch,
        rank: createPersonForm.rank.trim() || null,
        unit: createPersonForm.unit.trim() || null,
        specialty: createPersonForm.specialty.trim() || null,
        origin_type: createPersonForm.origin_type.trim() || null,
        service_year: Number(createPersonForm.service_year),
        position: createPersonForm.position,
        mobilization_status: createPersonForm.mobilization_status,
        status: createPersonForm.status,
        previous_training_hours: hoursInput === '' ? null : Number(hoursInput),
      }
      const response = await fetch(`${API_BASE}/persons`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(await responseError(response, '인원 등록에 실패했습니다.'))
      const person = await response.json() as Person
      const recommendationResponse = await fetch(`${API_BASE}/squads/assignments/recommendations/${encodeURIComponent(person.military_number)}`)
      if (!recommendationResponse.ok) throw new Error(await responseError(recommendationResponse, '분대 추천을 불러오지 못했습니다.'))
      setAddingPerson(false)
      setCreatePersonForm(initialCreatePersonForm)
      setNewArrival({ person, recommendations: await recommendationResponse.json() as AssignmentRecommendation[] })
      setRefreshKey((value) => value + 1)
    } catch (error) {
      setCreatePersonError(error instanceof Error ? error.message : '인원 등록에 실패했습니다.')
    } finally {
      setCreatePersonLoading(false)
    }
  }

  const prepareAssignment = () => {
    const nextProposal: ProposedAssignment[] = []
    const used = new Set<string>()
    assignmentBranches.forEach((branch) => assignmentPositions.forEach((position) => personnelCategories.forEach((category) => {
      const requested = quotas[branch]?.[position]?.[category] ?? 0
        const branchCandidates = candidates[branch]?.[category] ?? []
        branchCandidates.filter((candidate) => candidate.position === position).slice(0, requested).forEach((candidate) => {
          if (nextProposal.filter((item) => item.branch === branch && item.position === position && item.category === category).length >= requested || used.has(candidate.military_number)) return
          used.add(candidate.military_number)
          nextProposal.push({ ...candidate, branch, category, squad_id: Number(assignmentSquad) })
        })
    })))
    setProposal(nextProposal)
    setAssignmentError('')
    setAssignmentResult(null)
  }

  const confirmAssignments = async () => {
    setAssignmentLoading(true)
    setAssignmentError('')
    try {
      const response = await fetch(`${API_BASE}/squads/assignments/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assignments: proposal.map((item) => ({ person_id: item.military_number, squad_id: item.squad_id })) }) })
      if (!response.ok) throw new Error(await responseError(response, '전투편성에 실패했습니다.'))
      setAssignmentResult({ squad_id: Number(assignmentSquad), positions: {}, total_requested: proposal.length, total_assigned: proposal.length, total_shortfall: 0 })
      setProposal([])
      const [squadsResponse, candidatesResponse] = await Promise.all([fetch(`${API_BASE}/squads`), fetch(`${API_BASE}/squads/assignment-candidates`)]);
      if (squadsResponse.ok) setSquads(await squadsResponse.json() as Squad[])
      if (candidatesResponse.ok) setCandidates(await candidatesResponse.json() as AssignmentCandidates)
    } catch (error) { setAssignmentError(error instanceof Error ? error.message : '전투편성에 실패했습니다.') }
    finally { setAssignmentLoading(false) }
  }
  const confirmNewArrival = async (squadId: number) => {
    if (!newArrival) return
    const response = await fetch(`${API_BASE}/squads/assignments/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assignments: [{ person_id: newArrival.person.military_number, squad_id: squadId }] }) })
    if (!response.ok) { setCreatePersonError(await responseError(response, '분대 배정에 실패했습니다.')); return }
    setNewArrival(null)
    setRefreshKey((value) => value + 1)
  }

  return <main className="app-shell"><Header /><section className="content">
    <div className="page-switcher"><button className={page === 'lookup' ? 'selected' : ''} onClick={() => setPage('lookup')}>예비군 조회</button><button className={page === 'assignment' ? 'selected' : ''} onClick={() => setPage('assignment')}>전투편성</button></div>
    {page === 'assignment' ? <AssignmentReviewView squads={squads} candidates={candidates} squadId={assignmentSquad} setSquadId={(value) => { setAssignmentSquad(value); setProposal((items) => items.map((item) => ({ ...item, squad_id: Number(value) }))) }} quotas={quotas} setQuotas={setQuotas} result={assignmentResult} proposal={proposal} setProposal={setProposal} tab={assignmentTab} setTab={setAssignmentTab} loading={assignmentLoading} error={assignmentError} onPrepare={prepareAssignment} onConfirm={confirmAssignments} /> : <>
    <div className="page-intro"><div><h2>예비군 조회</h2><p>인원 정보를 검색하고 훈련 기록을 관리하세요.</p></div><div className="page-intro-actions"><button className="button primary" type="button" onClick={() => { setAddingPerson(true); setCreatePersonError(''); setCreatePersonForm(initialCreatePersonForm) }}>+ 신규 예비군 등록</button><div className="result-count"><strong>{people.length}</strong><span>조회 인원</span></div></div></div>
    <section className="search-panel"><label className="search-field"><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="이름 또는 군번으로 검색" /></label><Select label="군종" value={branch} options={branches} onChange={setBranch} /><Select label="상태" value={status} options={statuses} labels={{ active: '복무 중', on_leave: '휴가 중' }} onChange={setStatus} /><Select label="동원 상태" value={mobilizationStatus} options={mobilizationStatuses} onChange={setMobilizationStatus} /></section>
    <section className="list-card"><div className="list-caption"><h3>인원 목록</h3><span>{search || branch || status || mobilizationStatus ? '필터 적용 중' : '전체 인원'}</span></div>{listLoading && <div className="state-panel">인원 목록을 불러오는 중입니다...</div>}{listError && <div className="state-panel error-state">{listError}</div>}{!listLoading && !listError && people.length === 0 && <div className="state-panel empty-state"><strong>검색 결과가 없습니다</strong><span>검색어나 필터를 바꿔 다시 시도해 보세요.</span></div>}{!listLoading && !listError && people.length > 0 && <div className="table-wrap"><table className="people-table"><thead><tr><th>군번</th><th>이름</th><th>군종</th><th>계급</th><th>소속부대</th><th>분대</th><th>상태</th></tr></thead><tbody>{people.map((person) => <tr key={person.military_number} onClick={() => openDetail(person)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') openDetail(person) }}><td className="mono">{person.military_number}</td><td className="person-name">{person.name}</td><td>{person.branch}</td><td>{person.rank ?? '-'}</td><td>{person.unit ?? '-'}</td><td>{person.squad_id ? `${person.squad_id}분대` : '-'}</td><td><StatusBadge status={person.status} /></td></tr>)}</tbody></table></div>}</section>
  </>}</section>{selectedId && <DetailModal person={selectedPerson} progress={progress} records={records} loading={detailLoading} error={detailError} tab={tab} setTab={setTab} onClose={closeModal} onEdit={startPersonEdit} onDelete={deletePerson} editingPerson={editingPerson} personForm={personForm} setPersonForm={setPersonForm} onSavePerson={savePerson} onCancelPerson={() => setEditingPerson(false)} editingRecord={editingRecord} recordForm={recordForm} setRecordForm={setRecordForm} addingRecord={addingRecord} onStartAdd={() => { setAddingRecord(true); setEditingRecord(null); setRecordForm({ service_year: selectedPerson?.service_year && selectedPerson.service_year <= 6 ? selectedPerson.service_year : 1, training_year: selectedPerson?.service_year ?? 1, training_type: '기본훈련', training_round: 1, attendance_status: 'postponed', training_hours: 0, notes: '' }) }} onCancelRecord={() => { setEditingRecord(null); setAddingRecord(false); setRecordForm(null) }} onEditRecord={startRecordEdit} onSaveRecord={saveRecord} onAddRecord={addRecord} onDeleteRecord={deleteRecord} actionError={actionError} />}<CreatePersonModal open={addingPerson} form={createPersonForm} setForm={setCreatePersonForm} loading={createPersonLoading} error={createPersonError} onClose={() => setAddingPerson(false)} onSubmit={submitCreatePerson} /><TransferAssignmentModal arrival={newArrival} error={createPersonError} onClose={() => setNewArrival(null)} onConfirm={confirmNewArrival} /></main>
}

function AssignmentReviewView({ squads, candidates, squadId, setSquadId, quotas, setQuotas, result, proposal, setProposal, tab, setTab, loading, error, onPrepare, onConfirm }: { squads: Squad[]; candidates: AssignmentCandidates; squadId: string; setSquadId: (value: string) => void; quotas: AssignmentQuotas; setQuotas: (value: AssignmentQuotas) => void; result: AssignmentResult | null; proposal: ProposedAssignment[]; setProposal: Dispatch<SetStateAction<ProposedAssignment[]>>; tab: string; setTab: (value: string) => void; loading: boolean; error: string; onPrepare: () => void; onConfirm: () => void }) {
  const tabs = assignmentBranches.flatMap((branch) => personnelCategories.map((category) => `${branch}-${category}`))
  const [selectedBranch, selectedCategory] = tab.split('-')
  const tabCandidates = candidates[selectedBranch]?.[selectedCategory] ?? []
  const tabProposal = proposal.filter((person) => person.branch === selectedBranch && person.category === selectedCategory)
  const groupKey = `${selectedBranch}-${selectedCategory}`
  const compatibleSquads = squads.filter((squad) => {
    const groups = Object.keys(squad.breakdown ?? {})
    return groups.length === 0 || groups.includes(groupKey)
  })
  const selectedSquad = compatibleSquads.find((squad) => String(squad.id) === squadId) ?? null
  const required = assignmentPositions.reduce((sum, position) => sum + (quotas[selectedBranch]?.[position]?.[selectedCategory] ?? 0), 0)
  const totalRequested = assignmentBranches.reduce((sum, branch) => sum + assignmentPositions.reduce((branchSum, position) => branchSum + personnelCategories.reduce((categorySum, category) => categorySum + (quotas[branch]?.[position]?.[category] ?? 0), 0), 0), 0)
    return <div className="assignment-page"><div className="page-intro"><div><h2>전투편성 검토</h2><p>군별·인원유형별·직책별로 후보를 분리해 확인한 뒤 확정합니다.</p></div></div><div className="squad-profile-layout"><section className="assignment-panel squad-selector-panel"><label className="assignment-select">대상 분대<select value={squadId} onChange={(event) => setSquadId(event.target.value)}>{squads.map((squad) => <option key={squad.id} value={squad.id}>{squad.name} · 현재 {squad.person_count}명</option>)}</select></label>{selectedSquad && <SquadProfile squad={selectedSquad} />}</section><section className="assignment-panel requirement-panel"><div className="section-heading"><h3>{selectedBranch} 필요 인원</h3><span>{totalRequested}명 전체 요청</span></div><div className="quota-table compact-quota"><div className="quota-row quota-head"><span>직책</span>{personnelCategories.map((category) => <span key={category}>{category}</span>)}</div>{assignmentPositions.map((position) => <div className="quota-row" key={position}><strong>{position}</strong>{personnelCategories.map((category) => <label key={category}><input type="number" min="0" value={quotas[selectedBranch][position][category]} onChange={(event) => setQuotas({ ...quotas, [selectedBranch]: { ...quotas[selectedBranch], [position]: { ...quotas[selectedBranch][position], [category]: Number(event.target.value) } } })} /></label>)}</div>)}</div><p className="assignment-note">현재 탭: {selectedBranch} · {selectedCategory} / 우선순위: 5~6년차 병사 → 적소 → 유사 → 기타 → 보충</p></section></div><section className="assignment-panel review-panel"><div className="assignment-tabs" role="tablist">{tabs.map((tabName) => <button key={tabName} className={tab === tabName ? 'selected' : ''} onClick={() => setTab(tabName)}>{tabName.replace('-', ' · ')}</button>)}</div><div className="review-heading"><div><h3>{selectedBranch} · {selectedCategory}</h3><p>가용 {tabCandidates.filter((person) => assignmentPositions.includes(person.position)).length}명 · 필요 {required}명 · 검토안 {tabProposal.length}명</p></div><span className={tabProposal.length < required ? 'shortfall-label' : 'ready-label'}>{Math.max(required - tabProposal.length, 0)}명 부족</span></div><div className="candidate-list">{tabCandidates.length === 0 && <div className="state-panel">현재 조건에 맞는 후보가 없습니다.</div>}{tabCandidates.map((candidate) => { const proposed = proposal.find((person) => person.military_number === candidate.military_number); return <article className={proposed ? 'candidate-row proposed' : 'candidate-row'} key={candidate.military_number}><div><strong>{candidate.name}</strong><span>{candidate.military_number} · {candidate.position} · {candidate.specialty ?? '특기 없음'} · {candidate.service_year ?? '-'}년차</span></div><span className="tier-badge">{candidate.tier}</span>{proposed ? <select value={String(proposed.squad_id)} onChange={(event) => setProposal((items) => items.map((person) => person.military_number === proposed.military_number ? { ...person, squad_id: Number(event.target.value) } : person))}><option value={proposed.squad_id}>{squads.find((squad) => squad.id === proposed.squad_id)?.name ?? '대상 분대'}</option>{squads.filter((squad) => squad.id !== proposed.squad_id).map((squad) => <option key={squad.id} value={squad.id}>{squad.name}</option>)}</select> : <span className="candidate-status">후보</span>}</article> })}</div><div className="review-actions"><button className="button secondary" type="button" onClick={onPrepare}>편성안 만들기</button><button className="button primary" type="button" disabled={loading || proposal.length === 0} onClick={onConfirm}>{loading ? '확정 중...' : '검토안 확정 배정'}</button></div>{error && <div className="inline-error">{error}</div>}{result && <div className="confirmation-note">{result.total_assigned}명이 확정 배정되었습니다.</div>}</section></div>
}

function SquadProfile({ squad }: { squad: Squad }) {
  const entries = Object.entries(squad.breakdown ?? {})
  const total = entries.reduce((sum, [, count]) => sum + count, 0)
  let offset = 0
  const colors = ['#176b4d', '#d68b32', '#b43c35', '#477aa8', '#7256a3', '#8b9b42']
  const gradient = total ? entries.map(([, count], index) => { const start = offset; offset += (count / total) * 360; return `${colors[index % colors.length]} ${start}deg ${offset}deg` }).join(', ') : '#e5ebe6 0 360deg'
  return <div className="squad-profile"><div className="circle-chart" style={{ background: `conic-gradient(${gradient})` }}><div><strong>{squad.person_count}</strong><span>현재 인원</span></div></div><div className="profile-breakdown">{entries.length ? entries.map(([label, count], index) => <span key={label}><i style={{ background: colors[index % colors.length] }} />{label.replace('-', ' · ')} {count}명</span>) : <span>구성 데이터 없음</span>}</div></div>
}

export function AssignmentView({ squads, candidates, squadId, setSquadId, quotas, setQuotas, allowBranchMerge, setAllowBranchMerge, result, loading, error, onSubmit }: { squads: Squad[]; candidates: AssignmentCandidates; squadId: string; setSquadId: (value: string) => void; quotas: Record<string, Record<string, number>>; setQuotas: (value: Record<string, Record<string, number>>) => void; allowBranchMerge: boolean; setAllowBranchMerge: (value: boolean) => void; result: AssignmentResult | null; loading: boolean; error: string; onSubmit: () => void }) {
  const available = (position: string, category: string) => assignmentBranches.reduce((total, branch) => total + (candidates[branch]?.[category]?.filter((person) => person.position === position).length ?? 0), 0)
  return <div className="assignment-page"><div className="page-intro"><div><h2>전투편성</h2><p>미배정 5~6년차를 직책과 인원 유형별로 분대에 편성합니다.</p></div></div><section className="assignment-panel"><label className="assignment-select">대상 분대<select value={squadId} onChange={(event) => setSquadId(event.target.value)}>{squads.map((squad) => <option key={squad.id} value={squad.id}>{squad.name} · 현재 {squad.person_count}명</option>)}</select></label><label className="merge-toggle"><input type="checkbox" checked={allowBranchMerge} onChange={(event) => setAllowBranchMerge(event.target.checked)} /> 해군·해병대 등 부족한 군은 같은 분대에 통합</label><div className="quota-table"><div className="quota-row quota-head"><span>직책</span>{personnelCategories.map((category) => <span key={category}>{category}</span>)}</div>{assignmentPositions.map((position) => <div className="quota-row" key={position}><strong>{position}</strong>{personnelCategories.map((category) => <label key={category}><input type="number" min="0" value={quotas[position][category]} onChange={(event) => setQuotas({ ...quotas, [position]: { ...quotas[position], [category]: Number(event.target.value) } })} /><small>가용 {available(position, category)}</small></label>)}</div>)}</div><div className="branch-order">군별 우선순위: {assignmentBranches.join(' → ')}</div><button className="button primary assignment-submit" type="button" disabled={loading} onClick={onSubmit}>{loading ? '편성 중...' : '편성 실행'}</button>{error && <div className="inline-error">{error}</div>}</section>{result && <section className="assignment-result"><div className="result-summary"><div><span>요청 인원</span><strong>{result.total_requested}</strong></div><div><span>배정 인원</span><strong>{result.total_assigned}</strong></div><div className={result.total_shortfall ? 'has-shortfall' : ''}><span>부족 인원</span><strong>{result.total_shortfall}</strong></div></div><div className="assignment-cards">{Object.entries(result.positions).map(([position, detail]) => <article key={position} className={detail.shortfall ? 'shortfall-card' : ''}><div><h3>{position}</h3><span>{detail.assigned.length}/{detail.requested}명</span></div>{detail.assigned.length ? <ul>{detail.assigned.map((person) => <li key={person.military_number}><span>{person.name}</span><small>{person.military_number}</small></li>)}</ul> : <p className="empty-assignment">배정된 인원이 없습니다.</p>}{detail.shortfall > 0 && <strong className="shortfall-text">{detail.shortfall}명 부족</strong>}</article>)}</div></section>}</div>
}

function DetailModal(props: { person: Person | null; progress: TrainingProgress[]; records: TrainingRecord[]; loading: boolean; error: string; tab: Tab; setTab: (tab: Tab) => void; onClose: () => void; onEdit: () => void; onDelete: () => void; editingPerson: boolean; personForm: Partial<Person>; setPersonForm: (form: Partial<Person>) => void; onSavePerson: () => void; onCancelPerson: () => void; editingRecord: number | null; recordForm: TrainingRecordForm | null; setRecordForm: (form: TrainingRecordForm | null) => void; addingRecord: boolean; onStartAdd: () => void; onEditRecord: (record: TrainingRecord) => void; onCancelRecord: () => void; onSaveRecord: (id: number) => void; onAddRecord: () => void; onDeleteRecord: (id: number) => void; actionError: string }) {
  const { person, progress, records, loading, error, tab, setTab, onClose, onEdit, onDelete, editingPerson, personForm, setPersonForm, onSavePerson, onCancelPerson, editingRecord, recordForm, setRecordForm, addingRecord, onStartAdd, onEditRecord, onCancelRecord, onSaveRecord, onAddRecord, onDeleteRecord, actionError } = props

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="detail-modal" role="dialog" aria-modal="true" aria-label="예비군 상세 정보">
      <div className="modal-head">
        <div>{person && <><p className="eyebrow">RESERVIST PROFILE</p><h2>{person.name} {person.service_year !== null && <span className="year-badge">{person.service_year}년차</span>}</h2><p className="military-number">{person.military_number}</p></>}</div>
        <div className="modal-actions">
          <button className="button secondary" type="button" onClick={onEdit}>수정</button>
          <button className="button danger-outline" type="button" onClick={onDelete}>삭제</button>
          <button className="icon-button" type="button" onClick={onClose} aria-label="닫기">×</button>
        </div>
      </div>
      {loading && <div className="state-panel">상세 정보를 불러오는 중입니다...</div>}
      {error && <div className="state-panel error-state">{error}</div>}
      {!loading && !error && person && <>
        <nav className="modal-tabs" aria-label="상세 탭">
          <button className={tab === 'profile' ? 'selected' : ''} onClick={() => setTab('profile')}>프로필</button>
          <button className={tab === 'progress' ? 'selected' : ''} onClick={() => setTab('progress')}>훈련 현황</button>
          <button className={tab === 'records' ? 'selected' : ''} onClick={() => setTab('records')}>훈련 기록 <b>{records.length}</b></button>
        </nav>
        {actionError && <div className="inline-error">{actionError}</div>}
        {editingPerson ? <PersonEditor form={personForm} setForm={setPersonForm} records={records} onSave={onSavePerson} onCancel={onCancelPerson} /> : tab === 'profile' ? <ProfileTab person={person} progress={progress} /> : tab === 'progress' ? <ProgressTab progress={progress} /> : <RecordsTab progress={progress} records={records} editingRecord={editingRecord} recordForm={recordForm} setRecordForm={setRecordForm} addingRecord={addingRecord} onStartAdd={onStartAdd} onEdit={onEditRecord} onCancel={onCancelRecord} onSave={onSaveRecord} onAdd={onAddRecord} onDelete={onDeleteRecord} />}
      </>}
    </section>
  </div>
}

function getCurrentTrainingSituation(person: Person, progress: TrainingProgress[]) {
  if (!progress.length) return null

  const serviceYear = person.service_year ?? 1
  const current = progress.find((item) => item.service_year === serviceYear) ?? progress[progress.length - 1]
  if (!current) return null

  const required = Number(current.required_hours ?? current.target_hours ?? 0)
  const completed = Number(current.completed_hours ?? 0)
  const remaining = Number(current.remaining_hours ?? Math.max(required - completed, 0))
  const excess = Math.max(completed - required, 0)

  if (excess > 0) {
    return {
      type: 'excess',
      label: '초과 (초과 이수)',
      summary: `${excess}시간 초과`,
      detail: `${completed}시간 이수 / 기준 ${required}시간`,
      note: '초과된 시간은 다음 연도(또는 다음 차수) 훈련 시간에서 차감 처리됩니다.',
    }
  }

  if (remaining > 0) {
    return {
      type: 'makeup',
      label: '보충 훈련 필요',
      summary: `${remaining}시간 부족`,
      detail: `${completed}시간 이수 / 기준 ${required}시간`,
      note: '이수하지 못한 시간은 다음 훈련 일정에 반드시 보충 훈련으로 이수해야 합니다.',
    }
  }

  return {
    type: 'complete',
    label: '기준 충족',
    summary: '훈련 완료',
    detail: `${completed}시간 이수 / 기준 ${required}시간`,
    note: '현재 연도 기준 훈련 요구량을 모두 충족했습니다.',
  }
}

function ProfileTab({ person, progress }: { person: Person; progress: TrainingProgress[] }) {
  const situation = getCurrentTrainingSituation(person, progress)
  const prosecutionRiskYears = progress.filter((item) => item.prosecution_risk).map((item) => item.service_year)

  return <div className="modal-body">
    <div className="profile-status">
      <StatusBadge status={person.status} />
      <span>{person.service_year}년차 · {person.mobilization_status ?? '상태 미지정'}</span>
    </div>
    {prosecutionRiskYears.length > 0 && <section className="prosecution-warning" aria-label="고발 위험 경고">
      <div className="prosecution-warning-mark">!</div>
      <div>
        <p className="prosecution-warning-kicker">TRAINING ACTION REQUIRED</p>
        <h3>고발 조치 검토가 필요한 예비군입니다</h3>
        <p>{prosecutionRiskYears.map((year) => `${year}년차`).join(', ')} 훈련에서 고발 위험 기록이 확인되었습니다. 훈련 기록과 무단 불참 여부를 즉시 확인하세요.</p>
      </div>
    </section>}
    <section className="info-grid">
      <InfoItem label="현재 복무연차" value={person.service_year !== null ? `${person.service_year}년차` : null} />
      <InfoItem label="계급" value={person.rank} />
      <InfoItem label="군종" value={person.branch} />
      <InfoItem label="소속부대" value={person.unit} />
      <InfoItem label="특기" value={person.specialty} />
      <InfoItem label="직책" value={person.position} />
      <InfoItem label="등록구분" value={person.registration_type} />
      <InfoItem label="분대" value={person.squad_id ? `${person.squad_id}분대` : '-'} />
    </section>
    {situation && <section className={`training-status-card ${situation.type}`} aria-label="현재 훈련 상태">
      <div className="training-status-header">
        <span className="training-status-badge">{situation.label}</span>
        <strong>{situation.summary}</strong>
      </div>
      <p>{situation.detail}</p>
      <small>{situation.note}</small>
    </section>}
    <section className="info-panel" aria-label="훈련 처리 기준">
      <h3>훈련 처리 기준</h3>
      <ol>
        <li>
          <strong>초과 (초과 이수)</strong>
          <p>초과된 시간은 <strong>다음 연도(또는 다음 차수) 훈련 시간에서 차감</strong> 처리됩니다.</p>
        </li>
        <li>
          <strong>보충 (보충 훈련)</strong>
          <p>이수하지 못한 시간은 <strong>다음 훈련 일정에 반드시 보충 훈련</strong>으로 이수해야 합니다. (무단 불참 시 고발 조치될 수 있으므로 주의가 필요합니다.)</p>
        </li>
      </ol>
    </section>
  </div>
}

function TrainingPlanBadges({ plan }: { plan: TrainingPlanItem[] }) {
  if (plan.length === 0) return <span className="clear-mark">미이수</span>
  return <>{plan.map((item) => <span key={item.name} className="plan-badge">{item.name} {item.hours}시간</span>)}</>
}
function ProgressTab({ progress }: { progress: TrainingProgress[] }) { return <div className="modal-body"><div className="section-heading"><div><p className="eyebrow">ANNUAL TRAINING</p><h3>훈련 이수 현황</h3></div>{progress.some((item) => item.prosecution_risk) && <span className="risk-summary">고발 위험 연차 있음</span>}</div><TrainingTable progress={progress} /></div> }
function RecordsTab({ progress, records, editingRecord, recordForm, setRecordForm, addingRecord, onStartAdd, onEdit, onCancel, onSave, onAdd, onDelete }: { progress: TrainingProgress[]; records: TrainingRecord[]; editingRecord: number | null; recordForm: TrainingRecordForm | null; setRecordForm: (form: TrainingRecordForm | null) => void; addingRecord: boolean; onStartAdd: () => void; onEdit: (record: TrainingRecord) => void; onCancel: () => void; onSave: (id: number) => void; onAdd: () => void; onDelete: (id: number) => void }) {
  const update = (key: keyof TrainingRecordForm, value: string | number) => {
    if (!recordForm) return
    setRecordForm({ ...recordForm, [key]: value })
  }

  const getCompletionState = (serviceYear: number, trainingHours: number) => {
    const requiredHours = getRequiredTrainingHoursForYear(progress, serviceYear)
    return requiredHours > 0 && trainingHours >= requiredHours ? 'completed' : 'postponed'
  }

  const updateHours = (value: number) => {
    if (!recordForm) return
    setRecordForm({
      ...recordForm,
      training_hours: value,
      attendance_status: getCompletionState(recordForm.service_year, value),
    })
  }

  const getStatusLabel = (record: TrainingRecord) => {
    const requiredHours = getRequiredTrainingHoursForYear(progress, record.education_year)
    if (requiredHours > 0) {
      const remaining = Math.max(requiredHours - record.training_hours, 0)
      return record.attendance_status === 'completed' && record.training_hours >= requiredHours ? '이수 완료' : `남은 시간 ${remaining}시간`
    }
    return record.attendance_status === 'completed' ? '이수 완료' : '기준 없음'
  }

  return <div className="modal-body"><div className="records-toolbar"><div className="records-note">훈련시간, 훈련연도, 종류, 차수, 출결을 관리합니다.</div><button className="button primary" type="button" onClick={onStartAdd}>+ 훈련 기록 추가</button></div>{(addingRecord || editingRecord !== null) && recordForm && <div className="record-editor"><label>의무연차<input type="number" min="1" max="6" value={recordForm.service_year} onChange={(event) => update('service_year', Number(event.target.value))} /></label><label>훈련연도<input type="number" min="1" max="8" value={recordForm.training_year} onChange={(event) => update('training_year', Number(event.target.value))} /></label><label>훈련 종류<select value={recordForm.training_type} onChange={(event) => update('training_type', event.target.value)}>{trainingTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label>차수<select value={recordForm.training_round} onChange={(event) => update('training_round', Number(event.target.value))}><option value="1">1차</option><option value="2">2차</option><option value="3">3차</option></select></label><label>출결<select value={recordForm.attendance_status} onChange={(event) => update('attendance_status', event.target.value)}><option value="completed">이수</option><option value="무단불참">무단불참</option><option value="postponed">연기</option></select></label><label>훈련시간<input type="number" min="0" value={recordForm.training_hours} onChange={(event) => updateHours(Number(event.target.value))} /><small className="field-hint">{getCompletionState(recordForm.service_year, recordForm.training_hours) === 'completed' ? '이수 완료' : `남은 시간 ${Math.max(getRequiredTrainingHoursForYear(progress, recordForm.service_year) - recordForm.training_hours, 0)}시간`}</small></label><label className="record-notes">메모<input value={recordForm.notes} onChange={(event) => update('notes', event.target.value)} /></label><div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>취소</button><button className="button primary" type="button" onClick={addingRecord ? onAdd : () => onSave(editingRecord as number)}>저장</button></div></div>}{records.length === 0 ? <div className="state-panel empty-state"><strong>훈련 기록이 없습니다</strong><span>위의 추가 버튼으로 새 훈련 기록을 등록할 수 있습니다.</span></div> : <div className="table-wrap"><table><thead><tr><th>연차</th><th>훈련종류</th><th>차수</th><th>출결</th><th>시간</th><th>메모</th><th>관리</th></tr></thead><tbody>{records.map((record) => <tr key={record.id}><td>{record.education_year}년차</td><td>{record.training_type}</td><td>{record.training_round}차</td><td>{getStatusLabel(record)}</td><td>{record.training_hours}시간</td><td>{record.notes ?? '-'}</td><td><div className="inline-actions"><button className="button small secondary" type="button" onClick={() => onEdit(record)}>수정</button><button className="button small danger-outline" type="button" onClick={() => onDelete(record.id)}>삭제</button></div></td></tr>)}</tbody></table></div>}</div>
}
function PersonEditor({ form, setForm, records, onSave, onCancel }: { form: Partial<Person>; setForm: (form: Partial<Person>) => void; records: TrainingRecord[]; onSave: () => void; onCancel: () => void }) {
  const update = (key: keyof Person, value: string | number | null) => setForm({ ...form, [key]: value })
  const updateSpecialty = (value: string) => {
    const suggestedPosition = suggestPositionForSpecialty(value)
    setForm({
      ...form,
      specialty: value,
      position: suggestedPosition && (!form.position || form.position === '소총수' || form.position === '보충') ? suggestedPosition : form.position,
    })
  }

  return <div className="modal-body"><div className="edit-grid"><label>이름<input value={form.name ?? ''} onChange={(event) => update('name', event.target.value)} /></label><label>계급<input value={form.rank ?? ''} onChange={(event) => update('rank', event.target.value)} /></label><label>군종<input value={form.branch ?? ''} onChange={(event) => update('branch', event.target.value)} /></label><label>소속부대<input value={form.unit ?? ''} onChange={(event) => update('unit', event.target.value)} /></label><label>특기<input value={form.specialty ?? ''} placeholder="예: 통신, 의무, 운전 / 또는 171101" onChange={(event) => updateSpecialty(event.target.value)} /></label><label>직책<input value={form.position ?? ''} onChange={(event) => update('position', event.target.value)} /></label><label>복무연도<input type="number" min="0" max="8" value={form.service_year ?? ''} onChange={(event) => update('service_year', Number(event.target.value))} /></label><label>동원 상태<select value={form.mobilization_status ?? '해당없음'} onChange={(event) => update('mobilization_status', event.target.value)}>{mobilizationStatuses.map((option) => <option key={option} value={option}>{option}</option>)}</select></label><label>출신 유형<input value={form.origin_type ?? ''} placeholder="예: 공중보건의출신" onChange={(event) => update('origin_type', event.target.value || null)} /></label><label>상태<select value={form.status ?? 'active'} onChange={(event) => update('status', event.target.value)}><option value="active">복무 중</option><option value="on_leave">휴가 중</option></select></label></div><PersonHistoryPanel records={records} /><div className="form-actions"><button className="button secondary" onClick={onCancel}>취소</button><button className="button primary" onClick={onSave}>저장</button></div></div> }
function PersonHistoryPanel({ records }: { records: TrainingRecord[] }) {
  const sorted = [...records].sort((a, b) => a.education_year - b.education_year || a.id - b.id)
  return <section className="history-panel"><h4>이전 훈련 기록</h4>{sorted.length === 0 ? <div className="state-panel empty-state">등록된 훈련 기록이 없습니다.</div> : <div className="table-wrap"><table><thead><tr><th>연차</th><th>훈련연도</th><th>종류</th><th>차수</th><th>출결</th><th>시간</th></tr></thead><tbody>{sorted.map((record) => <tr key={record.id}><td>{record.education_year}년차</td><td>{record.training_year ?? '-'}</td><td>{record.training_type}</td><td>{record.training_round}차</td><td>{record.attendance_status}</td><td>{record.training_hours}시간</td></tr>)}</tbody></table></div>}</section>
}
function Header() { return <header className="topbar"><div className="brand-lockup"><span className="brand-mark">31</span><div><p className="eyebrow">31사단 AI TF</p><h1>예비군 관리 대시보드</h1></div></div><span className="system-status"><i /> 운영 중</span></header> }
function StatusBadge({ status }: { status: string }) { return <span className={`status-badge ${status === 'active' ? 'active' : 'leave'}`}>{status === 'active' ? '복무 중' : '휴가 중'}</span> }
function InfoItem({ label, value }: { label: string; value: string | number | null | undefined }) { return <div className="info-item"><span>{label}</span><strong>{value || '-'}</strong></div> }
function Select({ label, value, options, labels, onChange }: { label: string; value: string; options: string[]; labels?: Record<string, string>; onChange: (value: string) => void }) { return <label className="filter-field"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">전체</option>{options.map((option) => <option key={option} value={option}>{labels?.[option] ?? option}</option>)}</select></label> }
function TrainingTable({ progress }: { progress: TrainingProgress[] }) { return <div className="table-wrap"><table><thead><tr><th>연차</th><th>동원상태</th><th>훈련종류</th><th>목표시간</th><th>이수시간</th><th>잔여시간</th><th>고발위험</th></tr></thead><tbody>{progress.map((item) => <tr className={item.prosecution_risk ? 'risk-row' : ''} key={item.service_year}><td>{item.service_year}년차</td><td>{item.mobilization_status ?? '-'}</td><td className="plan-cell"><TrainingPlanBadges plan={item.training_plan} /></td><td>{item.target_hours}시간</td><td>{item.completed_hours}시간</td><td className={item.remaining_hours > 0 ? 'remaining' : ''}>{item.remaining_hours}시간</td><td>{item.prosecution_risk ? <span className="risk-badge">주의</span> : <span className="clear-mark">-</span>}</td></tr>)}</tbody></table></div> }

function CreatePersonModal(props: {
  open: boolean
  form: CreatePersonForm
  setForm: React.Dispatch<React.SetStateAction<CreatePersonForm>>
  loading: boolean
  error: string
  onClose: () => void
  onSubmit: () => void
}) {
  const { open, form, setForm, loading, error, onClose, onSubmit } = props
  const [showSpecialtyInput, setShowSpecialtyInput] = useState(false)
  if (!open) return null

  const update = (key: keyof CreatePersonForm, value: string | number) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const updateSpecialty = (value: string) => {
    setForm((prev) => {
      const suggestedPosition = suggestPositionForSpecialty(value)
      return {
        ...prev,
        specialty: value,
        position: suggestedPosition && (!prev.position || prev.position === '소총수' || prev.position === '보충') ? suggestedPosition : prev.position,
      }
    })
  }

  const setRankCategory = (category: string) => {
    const nextRank = rankCategoryMap[category]?.[0] ?? ''
    setForm((prev) => ({
      ...prev,
      origin_type: category,
      rank: nextRank,
    }))
  }

  const selectedRankCategory = originTypeOptions.includes(form.origin_type) ? form.origin_type : '병사'
  const rankOptions = rankCategoryMap[selectedRankCategory] ?? rankCategoryMap.병사

  const hoursValue = form.previous_training_hours.trim()
  const classification = hoursValue === '' || Number(hoursValue) <= 0 ? '신규' : '예비군 전입'

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="detail-modal create-person-modal" role="dialog" aria-modal="true" aria-label="신규 예비군 등록">
        <div className="modal-head">
          <div>
            <p className="eyebrow">NEW RESERVIST</p>
            <h2>신규 예비군 등록</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="닫기">×</button>
        </div>
        {error && <div className="inline-error">{error}</div>}
        <div className="modal-body">
          <div className="edit-grid">
            <label>군번 *
              <input value={form.military_number} placeholder="예: 26-72000501" onChange={(e) => update('military_number', e.target.value)} />
            </label>
            <label>이름 *
              <input value={form.name} placeholder="예: 홍길동" onChange={(e) => update('name', e.target.value)} />
            </label>
            <label>군종
              <select value={form.branch} onChange={(e) => update('branch', e.target.value)}>
                {branches.map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </label>
            <label>소속부대
              <input value={form.unit} placeholder="예: 31사단 100연대" onChange={(e) => update('unit', e.target.value)} />
            </label>
            <label>복무연차
              <input type="number" min="0" max="8" value={form.service_year} onChange={(e) => update('service_year', Number(e.target.value))} />
            </label>
            <label>동원 상태
              <select value={form.mobilization_status} onChange={(e) => update('mobilization_status', e.target.value)}>
                {mobilizationStatuses.map((st) => <option key={st} value={st}>{st}</option>)}
              </select>
            </label>
            <div className="full-width-field">
              <span>출신 유형</span>
              <div className="button-group">
                {originTypeOptions.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={selectedRankCategory === option ? 'button small primary' : 'button small secondary'}
                    onClick={() => setRankCategory(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
              <div className="button-group sub-button-group">
                {rankOptions.map((rank) => (
                  <button
                    key={rank}
                    type="button"
                    className={form.rank === rank ? 'button small primary' : 'button small secondary'}
                    onClick={() => update('rank', rank)}
                  >
                    {rank}
                  </button>
                ))}
              </div>
            </div>
            <div className="full-width-field">
              <div className="inline-row-between">
                <span>특기</span>
                {!showSpecialtyInput && (
                  <button type="button" className="button small secondary" onClick={() => setShowSpecialtyInput(true)}>
                    특기 입력
                  </button>
                )}
              </div>
              {showSpecialtyInput ? (
                <input value={form.specialty} placeholder="예: 통신, 의무, 운전 / 또는 171101" onChange={(e) => updateSpecialty(e.target.value)} />
              ) : (
                <div className="field-hint muted">특기를 입력하면 직책이 자동으로 추천됩니다.</div>
              )}
            </div>
            <label>직책
              <select value={form.position} onChange={(e) => update('position', e.target.value)}>
                {assignmentPositions.map((pos) => <option key={pos} value={pos}>{pos}</option>)}
                <option value="소총수">소총수</option>
                <option value="보충">보충</option>
              </select>
            </label>
            <label className="full-width-field">
              이전 부대 이수 훈련시간 (previous_training_hours)
              <input type="number" min="0" value={form.previous_training_hours} placeholder="0 또는 미입력 시 '신규', 1시간 이상 시 '예비군 전입'" onChange={(e) => update('previous_training_hours', e.target.value)} />
              <small className="field-hint">
                자동 구별: <strong>{classification}</strong> (1시간 이상 입력 시 1년차부터 이수 시간이 순차 자동 생성됩니다)
              </small>
            </label>
          </div>
          <div className="form-actions">
            <button className="button secondary" type="button" onClick={onClose}>취소</button>
            <button className="button primary" type="button" disabled={loading} onClick={onSubmit}>
              {loading ? '등록 중...' : '등록 완료'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}

function TransferAssignmentModal({ arrival, error, onClose, onConfirm }: { arrival: { person: Person; recommendations: AssignmentRecommendation[] } | null; error: string; onClose: () => void; onConfirm: (squadId: number) => void }) {
  if (!arrival) return null
  const { person, recommendations } = arrival
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="detail-modal transfer-assignment-modal" role="dialog" aria-modal="true" aria-label="전입자 분대 추천">
      <div className="modal-head"><div><p className="eyebrow">NEW ARRIVAL / SQUAD REVIEW</p><h2>{person.name} 전입 편성</h2><p className="military-number">{person.military_number} · {person.branch} · {person.rank ?? '계급 미지정'} · {person.position ?? '직책 미지정'}</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="닫기">×</button></div>
      <div className="modal-body"><p className="transfer-note">새 전입자는 아직 분대에 배정되지 않았습니다. 호환 가능한 분대 중 하나를 선택해 확정하세요.</p>{recommendations.length === 0 ? <div className="state-panel empty-state"><strong>추천 가능한 분대가 없습니다</strong><span>같은 군종·인원유형의 빈 분대를 먼저 확인하세요.</span></div> : <div className="recommendation-list">{recommendations.map((recommendation, index) => <article className="recommendation-card" key={recommendation.squad_id}><div className="recommendation-rank">{index + 1}</div><div><h3>{recommendation.squad_name}</h3><p>{recommendation.reason}</p><small>현재 {recommendation.current_count}명 · 같은 직책 {recommendation.same_position_count}명 · 같은 특기등급 {recommendation.same_tier_count}명</small></div><button className="button primary" type="button" onClick={() => onConfirm(recommendation.squad_id)}>이 분대로 확정</button></article>)}</div>}{error && <div className="inline-error">{error}</div>}<div className="form-actions"><button className="button secondary" type="button" onClick={onClose}>나중에 편성</button></div></div>
    </section>
  </div>
}

export default App
