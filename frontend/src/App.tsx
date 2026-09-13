import { useEffect, useState } from 'react'
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

type TrainingProgress = {
  service_year: number
  target_hours: number
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

type Tab = 'profile' | 'progress' | 'records'
type Squad = { id: number; name: string; description: string | null; person_count: number }
type AssignmentResult = {
  squad_id: number
  positions: Record<string, { requested: number; assigned: { military_number: string; name: string }[]; shortfall: number }>
  total_requested: number
  total_assigned: number
  total_shortfall: number
}
type AssignmentQuotas = Record<string, Record<string, number>>
type AssignmentCandidates = Record<string, Record<string, { military_number: string; name: string; position: string; specialty: string | null; service_year: number | null; tier: string }[]>>
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const branches = ['육군', '해군', '공군', '해병대']
const statuses = ['active', 'on_leave']
const mobilizationStatuses = ['동원지정', '동원미지정', '학생예비군', '해당없음']
const trainingTypes = ['기본훈련', '동원훈련', '동미참훈련', '동원훈련Ⅱ형', '작계훈련(전·후반기)']
const assignmentPositions = ['행정병', '통신병', '의무병', '운전병', '보급병']
const personnelCategories = ['병사', '부사관', '장교']
const assignmentBranches = ['육군', '해군', '해병대', '공군']

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
  const [quotas, setQuotas] = useState<AssignmentQuotas>(Object.fromEntries(assignmentPositions.map((position) => [position, { 병사: 1, 부사관: 0, 장교: 0 }])))
  const [candidates, setCandidates] = useState<AssignmentCandidates>({})
  const [allowBranchMerge, setAllowBranchMerge] = useState(true)
  const [assignmentResult, setAssignmentResult] = useState<AssignmentResult | null>(null)
  const [assignmentLoading, setAssignmentLoading] = useState(false)
  const [assignmentError, setAssignmentError] = useState('')

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
      if (!response.ok) throw new Error('훈련 기록 수정에 실패했습니다.')
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

  const fillPositions = async () => {
    setAssignmentLoading(true)
    setAssignmentError('')
    try {
      const response = await fetch(`${API_BASE}/squads/${assignmentSquad}/fill-positions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ position_quotas: quotas, branch_order: assignmentBranches, allow_branch_merge: allowBranchMerge }) })
      if (!response.ok) throw new Error(await responseError(response, '전투편성에 실패했습니다.'))
      setAssignmentResult(await response.json() as AssignmentResult)
      const [squadsResponse, candidatesResponse] = await Promise.all([fetch(`${API_BASE}/squads`), fetch(`${API_BASE}/squads/assignment-candidates`)]);
      if (squadsResponse.ok) setSquads(await squadsResponse.json() as Squad[])
      if (candidatesResponse.ok) setCandidates(await candidatesResponse.json() as AssignmentCandidates)
    } catch (error) { setAssignmentError(error instanceof Error ? error.message : '전투편성에 실패했습니다.') }
    finally { setAssignmentLoading(false) }
  }

  return <main className="app-shell"><Header /><section className="content">
    <div className="page-switcher"><button className={page === 'lookup' ? 'selected' : ''} onClick={() => setPage('lookup')}>예비군 조회</button><button className={page === 'assignment' ? 'selected' : ''} onClick={() => setPage('assignment')}>전투편성</button></div>
    {page === 'assignment' ? <AssignmentView squads={squads} candidates={candidates} squadId={assignmentSquad} setSquadId={setAssignmentSquad} quotas={quotas} setQuotas={setQuotas} allowBranchMerge={allowBranchMerge} setAllowBranchMerge={setAllowBranchMerge} result={assignmentResult} loading={assignmentLoading} error={assignmentError} onSubmit={fillPositions} /> : <>
    <div className="page-intro"><div><p className="eyebrow">PERSONNEL DIRECTORY</p><h2>예비군 조회</h2><p>인원 정보를 검색하고 훈련 기록을 관리하세요.</p></div><div className="result-count"><strong>{people.length}</strong><span>조회 인원</span></div></div>
    <section className="search-panel"><label className="search-field"><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="이름 또는 군번으로 검색" /></label><Select label="군종" value={branch} options={branches} onChange={setBranch} /><Select label="상태" value={status} options={statuses} labels={{ active: '복무 중', on_leave: '휴가 중' }} onChange={setStatus} /><Select label="동원 상태" value={mobilizationStatus} options={mobilizationStatuses} onChange={setMobilizationStatus} /></section>
    <section className="list-card"><div className="list-caption"><h3>인원 목록</h3><span>{search || branch || status || mobilizationStatus ? '필터 적용 중' : '전체 인원'}</span></div>{listLoading && <div className="state-panel">인원 목록을 불러오는 중입니다...</div>}{listError && <div className="state-panel error-state">{listError}</div>}{!listLoading && !listError && people.length === 0 && <div className="state-panel empty-state"><strong>검색 결과가 없습니다</strong><span>검색어나 필터를 바꿔 다시 시도해 보세요.</span></div>}{!listLoading && !listError && people.length > 0 && <div className="table-wrap"><table className="people-table"><thead><tr><th>군번</th><th>이름</th><th>군종</th><th>계급</th><th>소속부대</th><th>분대</th><th>상태</th></tr></thead><tbody>{people.map((person) => <tr key={person.military_number} onClick={() => openDetail(person)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') openDetail(person) }}><td className="mono">{person.military_number}</td><td className="person-name">{person.name}</td><td>{person.branch}</td><td>{person.rank ?? '-'}</td><td>{person.unit ?? '-'}</td><td>{person.squad_id ? `${person.squad_id}분대` : '-'}</td><td><StatusBadge status={person.status} /></td></tr>)}</tbody></table></div>}</section>
  </>}</section>{selectedId && <DetailModal person={selectedPerson} progress={progress} records={records} loading={detailLoading} error={detailError} tab={tab} setTab={setTab} onClose={closeModal} onEdit={startPersonEdit} onDelete={deletePerson} editingPerson={editingPerson} personForm={personForm} setPersonForm={setPersonForm} onSavePerson={savePerson} onCancelPerson={() => setEditingPerson(false)} editingRecord={editingRecord} recordForm={recordForm} setRecordForm={setRecordForm} addingRecord={addingRecord} onStartAdd={() => { setAddingRecord(true); setEditingRecord(null); setRecordForm({ service_year: selectedPerson?.service_year && selectedPerson.service_year <= 6 ? selectedPerson.service_year : 1, training_year: selectedPerson?.service_year ?? 1, training_type: '기본훈련', training_round: 1, attendance_status: 'completed', training_hours: 0, notes: '' }) }} onCancelRecord={() => { setEditingRecord(null); setAddingRecord(false); setRecordForm(null) }} onEditRecord={startRecordEdit} onSaveRecord={saveRecord} onAddRecord={addRecord} onDeleteRecord={deleteRecord} actionError={actionError} />}</main>
}

function AssignmentView({ squads, candidates, squadId, setSquadId, quotas, setQuotas, allowBranchMerge, setAllowBranchMerge, result, loading, error, onSubmit }: { squads: Squad[]; candidates: AssignmentCandidates; squadId: string; setSquadId: (value: string) => void; quotas: AssignmentQuotas; setQuotas: (value: AssignmentQuotas) => void; allowBranchMerge: boolean; setAllowBranchMerge: (value: boolean) => void; result: AssignmentResult | null; loading: boolean; error: string; onSubmit: () => void }) {
  const available = (position: string, category: string) => assignmentBranches.reduce((total, branch) => total + (candidates[branch]?.[category]?.filter((person) => person.position === position).length ?? 0), 0)
  return <div className="assignment-page"><div className="page-intro"><div><p className="eyebrow">COMBAT FORMATION</p><h2>전투편성</h2><p>미배정 5~6년차를 직책과 인원 유형별로 분대에 편성합니다.</p></div></div><section className="assignment-panel"><label className="assignment-select">대상 분대<select value={squadId} onChange={(event) => setSquadId(event.target.value)}>{squads.map((squad) => <option key={squad.id} value={squad.id}>{squad.name} · 현재 {squad.person_count}명</option>)}</select></label><label className="merge-toggle"><input type="checkbox" checked={allowBranchMerge} onChange={(event) => setAllowBranchMerge(event.target.checked)} /> 해군·해병대 등 부족한 군은 같은 분대에 통합</label><div className="quota-table"><div className="quota-row quota-head"><span>직책</span>{personnelCategories.map((category) => <span key={category}>{category}</span>)}</div>{assignmentPositions.map((position) => <div className="quota-row" key={position}><strong>{position}</strong>{personnelCategories.map((category) => <label key={category}><input type="number" min="0" value={quotas[position][category]} onChange={(event) => setQuotas({ ...quotas, [position]: { ...quotas[position], [category]: Number(event.target.value) } })} /><small>가용 {available(position, category)}</small></label>)}</div>)}</div><div className="branch-order">군별 우선순위: {assignmentBranches.join(' → ')}</div><button className="button primary assignment-submit" type="button" disabled={loading} onClick={onSubmit}>{loading ? '편성 중...' : '편성 실행'}</button>{error && <div className="inline-error">{error}</div>}</section>{result && <section className="assignment-result"><div className="result-summary"><div><span>요청 인원</span><strong>{result.total_requested}</strong></div><div><span>배정 인원</span><strong>{result.total_assigned}</strong></div><div className={result.total_shortfall ? 'has-shortfall' : ''}><span>부족 인원</span><strong>{result.total_shortfall}</strong></div></div><div className="assignment-cards">{Object.entries(result.positions).map(([position, detail]) => <article key={position} className={detail.shortfall ? 'shortfall-card' : ''}><div><h3>{position}</h3><span>{detail.assigned.length}/{detail.requested}명</span></div>{detail.assigned.length ? <ul>{detail.assigned.map((person) => <li key={person.military_number}><span>{person.name}</span><small>{person.military_number}</small></li>)}</ul> : <p className="empty-assignment">배정된 인원이 없습니다.</p>}{detail.shortfall > 0 && <strong className="shortfall-text">{detail.shortfall}명 부족</strong>}</article>)}</div></section>}</div>
}

function DetailModal(props: { person: Person | null; progress: TrainingProgress[]; records: TrainingRecord[]; loading: boolean; error: string; tab: Tab; setTab: (tab: Tab) => void; onClose: () => void; onEdit: () => void; onDelete: () => void; editingPerson: boolean; personForm: Partial<Person>; setPersonForm: (form: Partial<Person>) => void; onSavePerson: () => void; onCancelPerson: () => void; editingRecord: number | null; recordForm: TrainingRecordForm | null; setRecordForm: (form: TrainingRecordForm | null) => void; addingRecord: boolean; onStartAdd: () => void; onEditRecord: (record: TrainingRecord) => void; onCancelRecord: () => void; onSaveRecord: (id: number) => void; onAddRecord: () => void; onDeleteRecord: (id: number) => void; actionError: string }) {
  const { person, progress, records, loading, error, tab, setTab, onClose, onEdit, onDelete, editingPerson, personForm, setPersonForm, onSavePerson, onCancelPerson, editingRecord, recordForm, setRecordForm, addingRecord, onStartAdd, onEditRecord, onCancelRecord, onSaveRecord, onAddRecord, onDeleteRecord, actionError } = props
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}><section className="detail-modal" role="dialog" aria-modal="true" aria-label="예비군 상세 정보"><div className="modal-head"><div>{person && <><p className="eyebrow">RESERVIST PROFILE</p><h2>{person.name}</h2><p className="military-number">{person.military_number}</p></>}</div><div className="modal-actions"><button className="button secondary" type="button" onClick={onEdit}>수정</button><button className="button danger-outline" type="button" onClick={onDelete}>삭제</button><button className="icon-button" type="button" onClick={onClose} aria-label="닫기">×</button></div></div>{loading && <div className="state-panel">상세 정보를 불러오는 중입니다...</div>}{error && <div className="state-panel error-state">{error}</div>}{!loading && !error && person && <><nav className="modal-tabs" aria-label="상세 탭"><button className={tab === 'profile' ? 'selected' : ''} onClick={() => setTab('profile')}>프로필</button><button className={tab === 'progress' ? 'selected' : ''} onClick={() => setTab('progress')}>훈련 현황</button><button className={tab === 'records' ? 'selected' : ''} onClick={() => setTab('records')}>훈련 기록 <b>{records.length}</b></button></nav>{actionError && <div className="inline-error">{actionError}</div>}{editingPerson ? <PersonEditor form={personForm} setForm={setPersonForm} onSave={onSavePerson} onCancel={onCancelPerson} /> : tab === 'profile' ? <ProfileTab person={person} /> : tab === 'progress' ? <ProgressTab progress={progress} /> : <RecordsTab records={records} editingRecord={editingRecord} recordForm={recordForm} setRecordForm={setRecordForm} addingRecord={addingRecord} onStartAdd={onStartAdd} onEdit={onEditRecord} onCancel={onCancelRecord} onSave={onSaveRecord} onAdd={onAddRecord} onDelete={onDeleteRecord} />}</>}</section></div>
}

function ProfileTab({ person }: { person: Person }) { return <div className="modal-body"><div className="profile-status"><StatusBadge status={person.status} /><span>{person.service_year}년차 · {person.mobilization_status ?? '상태 미지정'}</span></div><section className="info-grid"><InfoItem label="계급" value={person.rank} /><InfoItem label="군종" value={person.branch} /><InfoItem label="소속부대" value={person.unit} /><InfoItem label="특기" value={person.specialty} /><InfoItem label="직책" value={person.position} /><InfoItem label="등록구분" value={person.registration_type} /><InfoItem label="분대" value={person.squad_id ? `${person.squad_id}분대` : '-'} /></section></div> }
function ProgressTab({ progress }: { progress: TrainingProgress[] }) { return <div className="modal-body"><div className="section-heading"><div><p className="eyebrow">ANNUAL TRAINING</p><h3>훈련 이수 현황</h3></div>{progress.some((item) => item.prosecution_risk) && <span className="risk-summary">고발 위험 연차 있음</span>}</div><TrainingTable progress={progress} /></div> }
function RecordsTab({ records, editingRecord, recordForm, setRecordForm, addingRecord, onStartAdd, onEdit, onCancel, onSave, onAdd, onDelete }: { records: TrainingRecord[]; editingRecord: number | null; recordForm: TrainingRecordForm | null; setRecordForm: (form: TrainingRecordForm | null) => void; addingRecord: boolean; onStartAdd: () => void; onEdit: (record: TrainingRecord) => void; onCancel: () => void; onSave: (id: number) => void; onAdd: () => void; onDelete: (id: number) => void }) {
  const update = (key: keyof TrainingRecordForm, value: string | number) => { if (recordForm) setRecordForm({ ...recordForm, [key]: value }) }
  return <div className="modal-body"><div className="records-toolbar"><div className="records-note">훈련시간, 훈련연도, 종류, 차수, 출결을 관리합니다.</div><button className="button primary" type="button" onClick={onStartAdd}>+ 훈련 기록 추가</button></div>{(addingRecord || editingRecord !== null) && recordForm && <div className="record-editor"><label>의무연차<input type="number" min="1" max="6" value={recordForm.service_year} onChange={(event) => update('service_year', Number(event.target.value))} /></label><label>훈련연도<input type="number" min="1" max="8" value={recordForm.training_year} onChange={(event) => update('training_year', Number(event.target.value))} /></label><label>훈련 종류<select value={recordForm.training_type} onChange={(event) => update('training_type', event.target.value)}>{trainingTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label>차수<select value={recordForm.training_round} onChange={(event) => update('training_round', Number(event.target.value))}><option value="1">1차</option><option value="2">2차</option><option value="3">3차</option></select></label><label>출결<select value={recordForm.attendance_status} onChange={(event) => update('attendance_status', event.target.value)}><option value="completed">이수</option><option value="무단불참">무단불참</option><option value="postponed">연기</option></select></label><label>훈련시간<input type="number" min="0" value={recordForm.training_hours} onChange={(event) => update('training_hours', Number(event.target.value))} /></label><label className="record-notes">메모<input value={recordForm.notes} onChange={(event) => update('notes', event.target.value)} /></label><div className="form-actions"><button className="button secondary" type="button" onClick={onCancel}>취소</button><button className="button primary" type="button" onClick={addingRecord ? onAdd : () => onSave(editingRecord as number)}>저장</button></div></div>}{records.length === 0 ? <div className="state-panel empty-state"><strong>훈련 기록이 없습니다</strong><span>위의 추가 버튼으로 기록을 등록하세요.</span></div> : <div className="table-wrap"><table><thead><tr><th>의무연차</th><th>훈련연도</th><th>훈련 종류</th><th>차수</th><th>출결</th><th>시간</th><th>관리</th></tr></thead><tbody>{records.map((record) => <tr key={record.id}><td>{record.education_year}년차</td><td>{record.training_year ?? '-' }년</td><td>{record.training_type}</td><td>{record.training_round}차</td><td>{record.attendance_status}</td><td>{record.training_hours}시간</td><td className="row-actions"><button className="text-button" onClick={() => onEdit(record)}>수정</button><button className="text-button danger" onClick={() => onDelete(record.id)}>삭제</button></td></tr>)}</tbody></table></div>}</div>
}
function PersonEditor({ form, setForm, onSave, onCancel }: { form: Partial<Person>; setForm: (form: Partial<Person>) => void; onSave: () => void; onCancel: () => void }) { const update = (key: keyof Person, value: string | number | null) => setForm({ ...form, [key]: value }); return <div className="modal-body"><div className="edit-grid"><label>이름<input value={form.name ?? ''} onChange={(event) => update('name', event.target.value)} /></label><label>계급<input value={form.rank ?? ''} onChange={(event) => update('rank', event.target.value)} /></label><label>군종<input value={form.branch ?? ''} onChange={(event) => update('branch', event.target.value)} /></label><label>소속부대<input value={form.unit ?? ''} onChange={(event) => update('unit', event.target.value)} /></label><label>특기<input value={form.specialty ?? ''} onChange={(event) => update('specialty', event.target.value)} /></label><label>직책<input value={form.position ?? ''} onChange={(event) => update('position', event.target.value)} /></label><label>복무연도<input type="number" min="0" max="8" value={form.service_year ?? ''} onChange={(event) => update('service_year', Number(event.target.value))} /></label><label>출신 유형<input value={form.origin_type ?? ''} placeholder="예: 공중보건의출신" onChange={(event) => update('origin_type', event.target.value || null)} /></label><label>상태<select value={form.status ?? 'active'} onChange={(event) => update('status', event.target.value)}><option value="active">복무 중</option><option value="on_leave">휴가 중</option></select></label></div><div className="form-actions"><button className="button secondary" onClick={onCancel}>취소</button><button className="button primary" onClick={onSave}>저장</button></div></div> }
function Header() { return <header className="topbar"><div className="brand-lockup"><span className="brand-mark">31</span><div><p className="eyebrow">31사단 AI TF</p><h1>예비군 관리 대시보드</h1></div></div><span className="system-status"><i /> 운영 중</span></header> }
function StatusBadge({ status }: { status: string }) { return <span className={`status-badge ${status === 'active' ? 'active' : 'leave'}`}>{status === 'active' ? '복무 중' : '휴가 중'}</span> }
function InfoItem({ label, value }: { label: string; value: string | number | null | undefined }) { return <div className="info-item"><span>{label}</span><strong>{value || '-'}</strong></div> }
function Select({ label, value, options, labels, onChange }: { label: string; value: string; options: string[]; labels?: Record<string, string>; onChange: (value: string) => void }) { return <label className="filter-field"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">전체</option>{options.map((option) => <option key={option} value={option}>{labels?.[option] ?? option}</option>)}</select></label> }
function TrainingTable({ progress }: { progress: TrainingProgress[] }) { return <div className="table-wrap"><table><thead><tr><th>연차</th><th>목표시간</th><th>이수시간</th><th>잔여시간</th><th>고발위험</th></tr></thead><tbody>{progress.map((item) => <tr className={item.prosecution_risk ? 'risk-row' : ''} key={item.service_year}><td>{item.service_year}년차</td><td>{item.target_hours}시간</td><td>{item.completed_hours}시간</td><td className={item.remaining_hours > 0 ? 'remaining' : ''}>{item.remaining_hours}시간</td><td>{item.prosecution_risk ? <span className="risk-badge">주의</span> : <span className="clear-mark">-</span>}</td></tr>)}</tbody></table></div> }

export default App
