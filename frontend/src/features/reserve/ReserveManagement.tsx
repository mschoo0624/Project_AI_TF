import { useEffect, useState } from 'react'
import type { Dispatch, SetStateAction, ReactNode } from 'react'
import './ReserveManagement.css'

type DetailTab = 'profile' | 'progress' | 'records'

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
type AssignmentRecommendation = {
  squad_id: number
  squad_name: string
  current_count: number
  same_position_count: number
  same_tier_count: number
  reason: string
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
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const branches = ['육군', '해군', '공군', '해병대']
const statuses = ['active', 'on_leave']
const mobilizationStatuses = ['동원지정', '동원미지정', '학생예비군', '일부보류', '해당없음']
const trainingTypes = ['기본훈련', '동원훈련Ⅰ형', '동원훈련Ⅱ형', '작계훈련(전·후반기)']
const originTypeOptions = ['병사', '부사관', '장교']
const rankCategoryMap: Record<string, string[]> = {
  병사: ['이병', '일병', '상병', '병장'],
  부사관: ['하사', '중사', '상사'],
  장교: ['소위', '중위', '대위'],
}
const positionOptions = ['행정병', '병기취급병', '통신병', '의무병', '운전병', '보급병', '소총수', '보충']

const initialCreatePersonForm: CreatePersonForm = {
  military_number: '', name: '', branch: '육군', rank: '병장', unit: '', specialty: '',
  origin_type: '병사', service_year: 1, position: '소총수',
  mobilization_status: '동원지정', status: 'active', previous_training_hours: '',
}

function suggestPositionForSpecialty(specialty: string): string | null {
  const normalized = specialty.trim()
  if (!normalized) return null
  const compact = normalized.replace(/\s+/g, '').toLowerCase()
  const code = normalized.replace(/\D/g, '')
  const mapping: Record<string, string> = {
    행정: '행정병', 행정병: '행정병', '3111101': '행정병', '311102': '행정병',
    병기: '병기취급병', 병기취급: '병기취급병', 병기취급병: '병기취급병', '222101': '병기취급병', '222102': '병기취급병',
    통신: '통신병', 통신병: '통신병', '171101': '통신병', '171102': '통신병', '171104': '통신병', '171106': '통신병',
    의무: '의무병', 의무병: '의무병', '411101': '의무병', '411102': '의무병', '411103': '의무병', '411104': '의무병', '411105': '의무병', '411106': '의무병',
    운전: '운전병', 운전병: '운전병', '241102': '운전병', '241103': '운전병', '241104': '운전병', '231101': '운전병',
    보급: '보급병', 보급병: '보급병', '231103': '보급병', '231104': '보급병', '231105': '보급병',
  }
  return mapping[normalized] ?? mapping[compact] ?? mapping[code] ?? null
}

async function responseError(response: Response, fallback: string) {
  try {
    const data = await response.json() as { detail?: string }
    return data.detail ?? fallback
  } catch { return fallback }
}

function ReserveManagement() {
  const [search, setSearch] = useState('')
  const [branch, setBranch] = useState('')
  const [status, setStatus] = useState('')
  const [mobilizationStatus, setMobilizationStatus] = useState('')
  const [people, setPeople] = useState<Person[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null)
  const [progress, setProgress] = useState<TrainingProgress[]>([])
  const [records, setRecords] = useState<TrainingRecord[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [detailTab, setDetailTab] = useState<DetailTab>('profile')
  const [editingPerson, setEditingPerson] = useState(false)
  const [personForm, setPersonForm] = useState<Partial<Person>>({})
  const [editingRecord, setEditingRecord] = useState<number | null>(null)
  const [recordForm, setRecordForm] = useState<TrainingRecordForm | null>(null)
  const [addingRecord, setAddingRecord] = useState(false)
  const [actionError, setActionError] = useState('')

  const [addingPerson, setAddingPerson] = useState(false)
  const [createPersonForm, setCreatePersonForm] = useState<CreatePersonForm>(initialCreatePersonForm)
  const [createPersonLoading, setCreatePersonLoading] = useState(false)
  const [createPersonError, setCreatePersonError] = useState('')
  const [newArrival, setNewArrival] = useState<{ person: Person; recommendations: AssignmentRecommendation[] } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setListLoading(true); setListError('')
      const params = new URLSearchParams()
      if (search.trim()) params.set('query', search.trim())
      if (branch) params.set('branch', branch)
      if (status) params.set('status', status)
      if (mobilizationStatus) params.set('mobilization_status', mobilizationStatus)
      try {
        const r = await fetch(`${API_BASE}/persons?${params}`, { signal: controller.signal })
        if (!r.ok) throw new Error(await responseError(r, '인원 목록을 불러오지 못했습니다.'))
        setPeople(await r.json() as Person[])
      } catch (e) {
        if (!(e instanceof DOMException && e.name === 'AbortError')) setListError(e instanceof Error ? e.message : '인원 목록을 불러오지 못했습니다.')
      } finally { if (!controller.signal.aborted) setListLoading(false) }
    }, 300)
    return () => { clearTimeout(timer); controller.abort() }
  }, [search, branch, status, mobilizationStatus, refreshKey])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    setDetailLoading(true); setDetailError('')
    Promise.all([
      fetch(`${API_BASE}/persons/${selectedId}`, { signal: controller.signal }),
      fetch(`${API_BASE}/reservists/${selectedId}/training-hours`, { signal: controller.signal }),
    ]).then(async ([p, t]) => {
      if (!p.ok) throw new Error(await responseError(p, '상세 정보를 불러오지 못했습니다.'))
      if (!t.ok) throw new Error(await responseError(t, '훈련 정보를 불러오지 못했습니다.'))
      setSelectedPerson(await p.json() as Person)
      const td = await t.json() as { progress: TrainingProgress[]; records: TrainingRecord[] }
      setProgress(td.progress ?? []); setRecords(td.records ?? [])
    }).catch(e => { if (!controller.signal.aborted) setDetailError(e instanceof Error ? e.message : '상세 정보를 불러오지 못했습니다.') })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false) })
    return () => controller.abort()
  }, [selectedId, refreshKey])



  const openDetail = (p: Person) => { setSelectedId(p.military_number); setDetailTab('profile'); setActionError('') }
  const closeDetail = () => { setSelectedId(null); setSelectedPerson(null); setProgress([]); setRecords([]); setEditingPerson(false); setEditingRecord(null); setAddingRecord(false); setRecordForm(null); setActionError('') }

  const savePerson = async () => {
    if (!selectedId) return
    try {
      const r = await fetch(`${API_BASE}/persons/${selectedId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(personForm) })
      if (!r.ok) throw new Error(await responseError(r, '인원 정보 수정에 실패했습니다.'))
      setSelectedPerson(await r.json() as Person); setEditingPerson(false); setRefreshKey(k => k + 1)
    } catch (e) { setActionError(e instanceof Error ? e.message : '인원 정보 수정에 실패했습니다.') }
  }
  const deletePerson = async () => {
    if (!selectedId || !window.confirm('이 예비군을 삭제하시겠습니까?')) return
    try {
      const r = await fetch(`${API_BASE}/persons/${selectedId}`, { method: 'DELETE' })
      if (!r.ok) throw new Error(await responseError(r, '인원 삭제에 실패했습니다.'))
      closeDetail(); setRefreshKey(k => k + 1)
    } catch (e) { setActionError(e instanceof Error ? e.message : '인원 삭제에 실패했습니다.') }
  }
  const saveRecord = async (id: number) => {
    if (!selectedId || !recordForm) return
    try {
      const r = await fetch(`${API_BASE}/reservists/${selectedId}/training-hours/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(recordForm) })
      if (!r.ok) throw new Error(await responseError(r, '훈련 기록 수정에 실패했습니다.'))
      setEditingRecord(null); setRecordForm(null); setRefreshKey(k => k + 1)
    } catch (e) { setActionError(e instanceof Error ? e.message : '훈련 기록 수정에 실패했습니다.') }
  }
  const addRecord = async () => {
    if (!selectedId || !recordForm) return
    try {
      const r = await fetch(`${API_BASE}/reservists/${selectedId}/training-hours`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(recordForm) })
      if (!r.ok) throw new Error(await responseError(r, '훈련 기록 추가에 실패했습니다.'))
      setAddingRecord(false); setRecordForm(null); setRefreshKey(k => k + 1)
    } catch (e) { setActionError(e instanceof Error ? e.message : '훈련 기록 추가에 실패했습니다.') }
  }
  const deleteRecord = async (id: number) => {
    if (!selectedId || !window.confirm('이 훈련 기록을 삭제하시겠습니까?')) return
    try {
      const r = await fetch(`${API_BASE}/reservists/${selectedId}/training-hours/${id}`, { method: 'DELETE' })
      if (!r.ok) throw new Error(await responseError(r, '훈련 기록 삭제에 실패했습니다.'))
      setRefreshKey(k => k + 1)
    } catch (e) { setActionError(e instanceof Error ? e.message : '훈련 기록 삭제에 실패했습니다.') }
  }

  const submitCreatePerson = async () => {
    setCreatePersonError('')
    if (!createPersonForm.military_number.trim() || !createPersonForm.name.trim()) return setCreatePersonError('군번과 이름은 필수 입력 항목입니다.')
    setCreatePersonLoading(true)
    try {
      const h = createPersonForm.previous_training_hours.trim()
      const payload = { ...createPersonForm, military_number: createPersonForm.military_number.trim(), name: createPersonForm.name.trim(), unit: createPersonForm.unit.trim() || null, specialty: createPersonForm.specialty.trim() || null, previous_training_hours: h === '' ? null : Number(h) }
      const r = await fetch(`${API_BASE}/persons`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      if (!r.ok) throw new Error(await responseError(r, '인원 등록에 실패했습니다.'))
      const person = await r.json() as Person
      const rr = await fetch(`${API_BASE}/squads/assignments/recommendations/${encodeURIComponent(person.military_number)}`)
      if (!rr.ok) throw new Error(await responseError(rr, '분대 추천을 불러오지 못했습니다.'))
      setAddingPerson(false); setCreatePersonForm(initialCreatePersonForm); setNewArrival({ person, recommendations: await rr.json() as AssignmentRecommendation[] }); setRefreshKey(k => k + 1)
    } catch (e) { setCreatePersonError(e instanceof Error ? e.message : '인원 등록에 실패했습니다.') }
    finally { setCreatePersonLoading(false) }
  }

  const confirmNewArrival = async (squadId: number) => {
    if (!newArrival) return
    const r = await fetch(`${API_BASE}/squads/assignments/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assignments: [{ person_id: newArrival.person.military_number, squad_id: squadId }] }) })
    if (!r.ok) return setCreatePersonError(await responseError(r, '분대 배정에 실패했습니다.'))
    setNewArrival(null); setRefreshKey(k => k + 1)
  }

  return <div className="resource-module">
    <>
      <div className="page-intro"><div><h2>예비군 조회</h2><p>인원 정보를 검색하고 훈련 기록을 관리하세요.</p></div><div className="page-intro-actions"><button className="button primary" onClick={() => { setAddingPerson(true); setCreatePersonError(''); setCreatePersonForm(initialCreatePersonForm) }}>+ 신규 예비군 등록</button><div className="result-count"><strong>{people.length}</strong><span>조회 인원</span></div></div></div>
      <section className="search-panel">
        <label className="search-field"><span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="이름 또는 군번으로 검색" /></label>
        <Select label="군종" value={branch} options={branches} onChange={setBranch} />
        <Select label="상태" value={status} options={statuses} labels={{ active: '복무 중', on_leave: '휴가 중' }} onChange={setStatus} />
        <Select label="동원 상태" value={mobilizationStatus} options={mobilizationStatuses} onChange={setMobilizationStatus} />
      </section>
      <section className="list-card"><div className="list-caption"><h3>인원 목록</h3><span>{search || branch || status || mobilizationStatus ? '필터 적용 중' : '전체 인원'}</span></div>
        {listLoading && <State>인원 목록을 불러오는 중입니다...</State>}
        {listError && <State error>{listError}</State>}
        {!listLoading && !listError && people.length === 0 && <State><strong>검색 결과가 없습니다</strong><span>검색어나 필터를 바꿔 다시 시도해 보세요.</span></State>}
        {!listLoading && !listError && people.length > 0 && <div className="table-wrap"><table><thead><tr><th>군번</th><th>이름</th><th>군종</th><th>계급</th><th>소속부대</th><th>분대</th><th>상태</th></tr></thead><tbody>{people.map(p => <tr key={p.military_number} onClick={() => openDetail(p)} tabIndex={0} onKeyDown={e => e.key === 'Enter' && openDetail(p)}><td className="mono">{p.military_number}</td><td className="person-name">{p.name}</td><td>{p.branch}</td><td>{p.rank ?? '-'}</td><td>{p.unit ?? '-'}</td><td>{p.squad_id ? `${p.squad_id}분대` : '-'}</td><td><StatusBadge status={p.status} /></td></tr>)}</tbody></table></div>}
      </section>
    </>
    {selectedId && <DetailModal person={selectedPerson} progress={progress} records={records} loading={detailLoading} error={detailError} tab={detailTab} setTab={setDetailTab} onClose={closeDetail}
      onEdit={() => { if (selectedPerson) { setPersonForm(selectedPerson); setEditingPerson(true) } }} onDelete={deletePerson}
      editingPerson={editingPerson} personForm={personForm} setPersonForm={setPersonForm} onSavePerson={savePerson} onCancelPerson={() => setEditingPerson(false)}
      editingRecord={editingRecord} recordForm={recordForm} setRecordForm={setRecordForm} addingRecord={addingRecord}
      onStartAdd={() => { setAddingRecord(true); setEditingRecord(null); setRecordForm({ service_year: selectedPerson?.service_year && selectedPerson.service_year <= 6 ? selectedPerson.service_year : 1, training_year: new Date().getFullYear(), training_type: '기본훈련', training_round: 1, attendance_status: 'postponed', training_hours: 0, notes: '' }) }}
      onEditRecord={r => { setEditingRecord(r.id); setAddingRecord(false); setRecordForm({ service_year: r.education_year, training_year: r.training_year ?? new Date().getFullYear(), training_type: r.training_type, training_round: r.training_round, attendance_status: r.attendance_status, training_hours: r.training_hours, notes: r.notes ?? '' }) }}
      onCancelRecord={() => { setEditingRecord(null); setAddingRecord(false); setRecordForm(null) }} onSaveRecord={saveRecord} onAddRecord={addRecord} onDeleteRecord={deleteRecord} actionError={actionError} />}
    <CreatePersonModal open={addingPerson} form={createPersonForm} setForm={setCreatePersonForm} loading={createPersonLoading} error={createPersonError} onClose={() => setAddingPerson(false)} onSubmit={submitCreatePerson} />
    <TransferAssignmentModal arrival={newArrival} error={createPersonError} onClose={() => setNewArrival(null)} onConfirm={confirmNewArrival} />
  </div>
}

function DetailModal(props: {
  person: Person | null; progress: TrainingProgress[]; records: TrainingRecord[]; loading: boolean; error: string; tab: DetailTab; setTab: (t: DetailTab) => void; onClose: () => void; onEdit: () => void; onDelete: () => void;
  editingPerson: boolean; personForm: Partial<Person>; setPersonForm: (f: Partial<Person>) => void; onSavePerson: () => void; onCancelPerson: () => void;
  editingRecord: number | null; recordForm: TrainingRecordForm | null; setRecordForm: (f: TrainingRecordForm | null) => void; addingRecord: boolean; onStartAdd: () => void; onEditRecord: (r: TrainingRecord) => void; onCancelRecord: () => void; onSaveRecord: (id: number) => void; onAddRecord: () => void; onDeleteRecord: (id: number) => void; actionError: string
}) {
  const p = props
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && p.onClose()}><section className="detail-modal">
    <div className="modal-head"><div>{p.person && <><p className="eyebrow">RESERVIST PROFILE</p><h2>{p.person.name} {p.person.service_year != null && <span className="year-badge">{p.person.service_year}년차</span>}</h2><p className="military-number">{p.person.military_number}</p></>}</div><div className="modal-actions"><button className="button secondary" onClick={p.onEdit}>수정</button><button className="button danger-outline" onClick={p.onDelete}>삭제</button><button className="icon-button" onClick={p.onClose}>×</button></div></div>
    {p.loading && <State>상세 정보를 불러오는 중입니다...</State>}{p.error && <State error>{p.error}</State>}
    {!p.loading && !p.error && p.person && <>
      <nav className="modal-tabs"><button className={p.tab === 'profile' ? 'selected' : ''} onClick={() => p.setTab('profile')}>프로필</button><button className={p.tab === 'progress' ? 'selected' : ''} onClick={() => p.setTab('progress')}>훈련 현황</button><button className={p.tab === 'records' ? 'selected' : ''} onClick={() => p.setTab('records')}>훈련 기록 <b>{p.records.length}</b></button></nav>
      {p.actionError && <div className="inline-error">{p.actionError}</div>}
      {p.editingPerson ? <PersonEditor form={p.personForm} setForm={p.setPersonForm} records={p.records} onSave={p.onSavePerson} onCancel={p.onCancelPerson} /> :
        p.tab === 'profile' ? <ProfileTab person={p.person} progress={p.progress} /> :
        p.tab === 'progress' ? <ProgressTab progress={p.progress} /> :
        <RecordsTab progress={p.progress} records={p.records} editingRecord={p.editingRecord} recordForm={p.recordForm} setRecordForm={p.setRecordForm} addingRecord={p.addingRecord} onStartAdd={p.onStartAdd} onEdit={p.onEditRecord} onCancel={p.onCancelRecord} onSave={p.onSaveRecord} onAdd={p.onAddRecord} onDelete={p.onDeleteRecord} />}
    </>}
  </section></div>
}

function ProfileTab({ person, progress }: { person: Person; progress: TrainingProgress[] }) {
  const risks = progress.filter(x => x.prosecution_risk).map(x => x.service_year)
  return <div className="modal-body"><div className="profile-status"><StatusBadge status={person.status} /><span>{person.service_year}년차 · {person.mobilization_status ?? '상태 미지정'}</span></div>
    {risks.length > 0 && <section className="prosecution-warning"><b>!</b><div><strong>고발 조치 검토가 필요한 예비군입니다</strong><p>{risks.map(y => `${y}년차`).join(', ')} 훈련에서 고발 위험 기록이 확인되었습니다.</p></div></section>}
    <section className="info-grid"><Info label="현재 복무연차" value={person.service_year != null ? `${person.service_year}년차` : null} /><Info label="계급" value={person.rank} /><Info label="군종" value={person.branch} /><Info label="소속부대" value={person.unit} /><Info label="특기" value={person.specialty} /><Info label="직책" value={person.position} /><Info label="등록구분" value={person.registration_type} /><Info label="분대" value={person.squad_id ? `${person.squad_id}분대` : '-'} /></section>
  </div>
}
function ProgressTab({ progress }: { progress: TrainingProgress[] }) {
  return <div className="modal-body"><div className="section-heading"><h3>훈련 이수 현황</h3>{progress.some(x => x.prosecution_risk) && <span className="risk-summary">고발 위험 연차 있음</span>}</div><TrainingTable progress={progress} /></div>
}
function TrainingTable({ progress }: { progress: TrainingProgress[] }) {
  return <div className="table-wrap"><table><thead><tr><th>연차</th><th>동원상태</th><th>훈련종류</th><th>목표시간</th><th>이수시간</th><th>잔여시간</th><th>고발위험</th></tr></thead><tbody>{progress.map(x => <tr className={x.prosecution_risk ? 'risk-row' : ''} key={x.service_year}><td>{x.service_year}년차</td><td>{x.mobilization_status ?? '-'}</td><td>{x.training_plan.map(p => `${p.name} ${p.hours}시간`).join(', ') || '-'}</td><td>{x.target_hours}시간</td><td>{x.completed_hours}시간</td><td>{x.remaining_hours}시간</td><td>{x.prosecution_risk ? <span className="risk-badge">주의</span> : '-'}</td></tr>)}</tbody></table></div>
}
function getRequired(progress: TrainingProgress[], year: number) {
  const p = progress.find(x => x.service_year === year)
  return Number(p?.required_hours ?? p?.target_hours ?? 0)
}
function RecordsTab({ progress, records, editingRecord, recordForm, setRecordForm, addingRecord, onStartAdd, onEdit, onCancel, onSave, onAdd, onDelete }: {
  progress: TrainingProgress[]; records: TrainingRecord[]; editingRecord: number | null; recordForm: TrainingRecordForm | null; setRecordForm: (f: TrainingRecordForm | null) => void; addingRecord: boolean; onStartAdd: () => void; onEdit: (r: TrainingRecord) => void; onCancel: () => void; onSave: (id: number) => void; onAdd: () => void; onDelete: (id: number) => void
}) {
  const update = (k: keyof TrainingRecordForm, v: string | number) => recordForm && setRecordForm({ ...recordForm, [k]: v })
  return <div className="modal-body"><div className="records-toolbar"><span>훈련시간, 훈련연도, 종류, 차수, 출결을 관리합니다.</span><button className="button primary" onClick={onStartAdd}>+ 훈련 기록 추가</button></div>
    {(addingRecord || editingRecord !== null) && recordForm && <div className="record-editor">
      <label>의무연차<input type="number" min="1" max="6" value={recordForm.service_year} onChange={e => update('service_year', Number(e.target.value))} /></label>
      <label>훈련연도<input type="number" value={recordForm.training_year} onChange={e => update('training_year', Number(e.target.value))} /></label>
      <label>훈련 종류<select value={recordForm.training_type} onChange={e => update('training_type', e.target.value)}>{trainingTypes.map(t => <option key={t}>{t}</option>)}</select></label>
      <label>차수<select value={recordForm.training_round} onChange={e => update('training_round', Number(e.target.value))}><option value={1}>1차</option><option value={2}>2차</option><option value={3}>3차</option></select></label>
      <label>출결<select value={recordForm.attendance_status} onChange={e => update('attendance_status', e.target.value)}><option value="completed">이수</option><option value="무단불참">무단불참</option><option value="postponed">연기</option></select></label>
      <label>훈련시간<input type="number" min="0" value={recordForm.training_hours} onChange={e => { const h = Number(e.target.value); setRecordForm({ ...recordForm, training_hours: h, attendance_status: getRequired(progress, recordForm.service_year) > 0 && h >= getRequired(progress, recordForm.service_year) ? 'completed' : 'postponed' }) }} /></label>
      <label className="wide">메모<input value={recordForm.notes} onChange={e => update('notes', e.target.value)} /></label>
      <div className="form-actions wide"><button className="button secondary" onClick={onCancel}>취소</button><button className="button primary" onClick={addingRecord ? onAdd : () => onSave(editingRecord as number)}>저장</button></div>
    </div>}
    <div className="table-wrap"><table><thead><tr><th>연차</th><th>훈련연도</th><th>훈련종류</th><th>차수</th><th>출결</th><th>시간</th><th>메모</th><th>관리</th></tr></thead><tbody>{records.map(r => <tr key={r.id}><td>{r.education_year}년차</td><td>{r.training_year ?? '-'}</td><td>{r.training_type}</td><td>{r.training_round}차</td><td>{r.attendance_status}</td><td>{r.training_hours}시간</td><td>{r.notes ?? '-'}</td><td><button className="button small secondary" onClick={() => onEdit(r)}>수정</button> <button className="button small danger-outline" onClick={() => onDelete(r.id)}>삭제</button></td></tr>)}</tbody></table></div>
  </div>
}

function PersonEditor({ form, setForm, records, onSave, onCancel }: { form: Partial<Person>; setForm: (f: Partial<Person>) => void; records: TrainingRecord[]; onSave: () => void; onCancel: () => void }) {
  const update = (k: keyof Person, v: string | number | null) => setForm({ ...form, [k]: v })
  return <div className="modal-body"><div className="edit-grid">
    <label>이름<input value={form.name ?? ''} onChange={e => update('name', e.target.value)} /></label><label>계급<input value={form.rank ?? ''} onChange={e => update('rank', e.target.value)} /></label>
    <label>군종<input value={form.branch ?? ''} onChange={e => update('branch', e.target.value)} /></label><label>소속부대<input value={form.unit ?? ''} onChange={e => update('unit', e.target.value)} /></label>
    <label>특기<input value={form.specialty ?? ''} onChange={e => { const s = suggestPositionForSpecialty(e.target.value); setForm({ ...form, specialty: e.target.value, position: s && (!form.position || form.position === '소총수' || form.position === '보충') ? s : form.position }) }} /></label>
    <label>직책<input value={form.position ?? ''} onChange={e => update('position', e.target.value)} /></label>
    <label>복무연차<input type="number" value={form.service_year ?? ''} onChange={e => update('service_year', Number(e.target.value))} /></label>
    <label>동원 상태<select value={form.mobilization_status ?? '해당없음'} onChange={e => update('mobilization_status', e.target.value)}>{mobilizationStatuses.map(x => <option key={x}>{x}</option>)}</select></label>
    <label>출신 유형<input value={form.origin_type ?? ''} onChange={e => update('origin_type', e.target.value || null)} /></label>
    <label>상태<select value={form.status ?? 'active'} onChange={e => update('status', e.target.value)}><option value="active">복무 중</option><option value="on_leave">휴가 중</option></select></label>
  </div><div className="history-panel"><h4>이전 훈련 기록</h4><div className="table-wrap"><table><thead><tr><th>연차</th><th>훈련연도</th><th>종류</th><th>시간</th></tr></thead><tbody>{records.map(r => <tr key={r.id}><td>{r.education_year}년차</td><td>{r.training_year ?? '-'}</td><td>{r.training_type}</td><td>{r.training_hours}시간</td></tr>)}</tbody></table></div></div><div className="form-actions"><button className="button secondary" onClick={onCancel}>취소</button><button className="button primary" onClick={onSave}>저장</button></div></div>
}

function CreatePersonModal({ open, form, setForm, loading, error, onClose, onSubmit }: { open: boolean; form: CreatePersonForm; setForm: Dispatch<SetStateAction<CreatePersonForm>>; loading: boolean; error: string; onClose: () => void; onSubmit: () => void }) {
  const [showSpecialty, setShowSpecialty] = useState(false)
  if (!open) return null
  const update = (k: keyof CreatePersonForm, v: string | number) => setForm(prev => ({ ...prev, [k]: v }))
  const category = originTypeOptions.includes(form.origin_type) ? form.origin_type : '병사'
  return <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}><section className="detail-modal create-modal"><div className="modal-head"><div><p className="eyebrow">NEW RESERVIST</p><h2>신규 예비군 등록</h2></div><button className="icon-button" onClick={onClose}>×</button></div><div className="modal-body">
    <div className="edit-grid">
      <label>군번 *<input value={form.military_number} onChange={e => update('military_number', e.target.value)} /></label><label>이름 *<input value={form.name} onChange={e => update('name', e.target.value)} /></label>
      <label>군종<select value={form.branch} onChange={e => update('branch', e.target.value)}>{branches.map(x => <option key={x}>{x}</option>)}</select></label><label>소속부대<input value={form.unit} onChange={e => update('unit', e.target.value)} /></label>
      <label>복무연차<input type="number" min="1" max="8" value={form.service_year} onChange={e => update('service_year', Number(e.target.value))} /></label><label>동원상태<select value={form.mobilization_status} onChange={e => update('mobilization_status', e.target.value)}>{mobilizationStatuses.map(x => <option key={x}>{x}</option>)}</select></label>
      <div className="wide"><span className="field-label">인원 유형</span><div className="choice-row">{originTypeOptions.map(x => <button key={x} className={`choice ${category === x ? 'selected' : ''}`} onClick={() => setForm(prev => ({ ...prev, origin_type: x, rank: rankCategoryMap[x][0] }))}>{x}</button>)}</div></div>
      <div className="wide"><span className="field-label">계급</span><div className="choice-row">{rankCategoryMap[category].map(x => <button key={x} className={`choice ${form.rank === x ? 'selected' : ''}`} onClick={() => update('rank', x)}>{x}</button>)}</div></div>
      <div className="wide">{!showSpecialty ? <button className="button secondary" onClick={() => setShowSpecialty(true)}>특기 입력</button> : <label>특기<input value={form.specialty} onChange={e => { const v = e.target.value; setForm(prev => ({ ...prev, specialty: v, position: suggestPositionForSpecialty(v) ?? prev.position })) }} /></label>}</div>
      <label>직책<select value={form.position} onChange={e => update('position', e.target.value)}>{positionOptions.map(x => <option key={x}>{x}</option>)}</select></label>
      <label>이전 훈련시간<input type="number" min="0" value={form.previous_training_hours} onChange={e => update('previous_training_hours', e.target.value)} /><small>{form.previous_training_hours === '' || Number(form.previous_training_hours) <= 0 ? '신규' : '예비군 전입'}</small></label>
    </div>{error && <div className="inline-error">{error}</div>}<div className="form-actions"><button className="button secondary" onClick={onClose}>취소</button><button className="button primary" disabled={loading} onClick={onSubmit}>{loading ? '등록 중...' : '등록 완료'}</button></div>
  </div></section></div>
}

function TransferAssignmentModal({ arrival, error, onClose, onConfirm }: { arrival: { person: Person; recommendations: AssignmentRecommendation[] } | null; error: string; onClose: () => void; onConfirm: (id: number) => void }) {
  if (!arrival) return null
  return <div className="modal-backdrop"><section className="detail-modal"><div className="modal-head"><div><p className="eyebrow">NEW ARRIVAL / SQUAD REVIEW</p><h2>{arrival.person.name} 전입 편성</h2><p className="military-number">{arrival.person.military_number}</p></div><button className="icon-button" onClick={onClose}>×</button></div><div className="modal-body"><p>새 전입자는 아직 분대에 배정되지 않았습니다. 추천 분대를 선택해 확정하세요.</p><div className="recommendation-list">{arrival.recommendations.map((r, i) => <article className="recommendation-card" key={r.squad_id}><b>{i + 1}</b><div><h3>{r.squad_name}</h3><p>{r.reason}</p><small>현재 {r.current_count}명 · 같은 직책 {r.same_position_count}명 · 같은 특기등급 {r.same_tier_count}명</small></div><button className="button primary" onClick={() => onConfirm(r.squad_id)}>이 분대로 확정</button></article>)}</div>{error && <div className="inline-error">{error}</div>}<div className="form-actions"><button className="button secondary" onClick={onClose}>나중에 편성</button></div></div></section></div>
}

function Select({ label, value, options, labels, onChange }: { label: string; value: string; options: string[]; labels?: Record<string, string>; onChange: (v: string) => void }) {
  return <label className="filter-field"><span>{label}</span><select value={value} onChange={e => onChange(e.target.value)}><option value="">전체</option>{options.map(x => <option key={x} value={x}>{labels?.[x] ?? x}</option>)}</select></label>
}
function StatusBadge({ status }: { status: string }) { return <span className={`status-badge ${status === 'active' ? 'active' : 'leave'}`}>{status === 'active' ? '복무 중' : '휴가 중'}</span> }
function Info({ label, value }: { label: string; value: string | number | null | undefined }) { return <div className="info-item"><span>{label}</span><strong>{value || '-'}</strong></div> }
function State({ children, error = false }: { children: ReactNode; error?: boolean }) { return <div className={`state-panel ${error ? 'error-state' : ''}`}>{children}</div> }


export default ReserveManagement