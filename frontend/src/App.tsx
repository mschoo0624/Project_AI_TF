import { useEffect, useState } from 'react'
import './App.css'

type Person = {
  military_number: string
  name: string
  branch: string
  rank: string | null
  unit: string | null
  specialty: string | null
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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'
const branches = ['육군', '해군', '공군', '해병대']
const statuses = ['active', 'on_leave']
const mobilizationStatuses = ['동원지정', '동원미지정', '학생예비군', '해당없음']

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
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')

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

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [search, branch, status, mobilizationStatus])

  useEffect(() => {
    if (!selectedId) return
    const controller = new AbortController()
    const loadDetail = async () => {
      setDetailLoading(true)
      setDetailError('')
      try {
        const [personResponse, progressResponse] = await Promise.all([
          fetch(`${API_BASE}/persons/${selectedId}`, { signal: controller.signal }),
          fetch(`${API_BASE}/persons/${selectedId}/training-progress`, { signal: controller.signal }),
        ])
        if (personResponse.status === 404 || progressResponse.status === 404) {
          throw new Error('해당 예비군을 찾을 수 없습니다.')
        }
        if (!personResponse.ok || !progressResponse.ok) throw new Error('상세 정보를 불러오지 못했습니다.')
        setSelectedPerson(await personResponse.json() as Person)
        setProgress(await progressResponse.json() as TrainingProgress[])
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setDetailError(error instanceof Error ? error.message : '상세 정보를 불러오지 못했습니다.')
      } finally {
        if (!controller.signal.aborted) setDetailLoading(false)
      }
    }
    void loadDetail()
    return () => controller.abort()
  }, [selectedId])

  const openDetail = (person: Person) => {
    setSelectedId(person.military_number)
    setSelectedPerson(null)
    setProgress([])
  }

  const goBack = () => {
    setSelectedId(null)
    setSelectedPerson(null)
    setProgress([])
    setDetailError('')
  }

  if (selectedId) {
    return (
      <main className="app-shell">
        <Header />
        <section className="content detail-page">
          <button className="back-button" type="button" onClick={goBack}>← 목록으로 돌아가기</button>
          {detailLoading && <div className="state-panel">상세 정보를 불러오는 중입니다...</div>}
          {detailError && <div className="state-panel error-state">{detailError}</div>}
          {!detailLoading && !detailError && selectedPerson && (
            <>
              <section className="person-heading">
                <div><p className="eyebrow">RESERVIST PROFILE</p><h2>{selectedPerson.name}</h2><p className="military-number">{selectedPerson.military_number}</p></div>
                <StatusBadge status={selectedPerson.status} />
              </section>
              <section className="info-grid">
                <InfoItem label="계급" value={selectedPerson.rank} />
                <InfoItem label="군종" value={selectedPerson.branch} />
                <InfoItem label="소속부대" value={selectedPerson.unit} />
                <InfoItem label="특기" value={selectedPerson.specialty} />
                <InfoItem label="직책" value={selectedPerson.position} />
                <InfoItem label="분대" value={selectedPerson.squad_id ? `${selectedPerson.squad_id}분대` : '-'} />
              </section>
              <section className="section-block">
                <div className="section-heading"><div><p className="eyebrow">ANNUAL TRAINING</p><h3>훈련 이수 현황</h3></div>{progress.some((item) => item.prosecution_risk) && <span className="risk-summary">고발 위험 연차 있음</span>}</div>
                <TrainingTable progress={progress} />
              </section>
            </>
          )}
        </section>
      </main>
    )
  }

  return (
    <main className="app-shell">
      <Header />
      <section className="content">
        <div className="page-intro"><div><p className="eyebrow">PERSONNEL DIRECTORY</p><h2>예비군 조회</h2><p>인원 정보를 검색하고 연간 훈련 이수 현황을 확인하세요.</p></div><div className="result-count"><strong>{people.length}</strong><span>조회 인원</span></div></div>
        <section className="search-panel">
          <label className="search-field"><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="이름 또는 군번으로 검색" /></label>
          <Select label="군종" value={branch} options={branches} onChange={setBranch} />
          <Select label="상태" value={status} options={statuses} labels={{ active: '복무 중', on_leave: '휴가 중' }} onChange={setStatus} />
          <Select label="동원 상태" value={mobilizationStatus} options={mobilizationStatuses} onChange={setMobilizationStatus} />
        </section>
        <section className="list-card">
          <div className="list-caption"><h3>인원 목록</h3><span>{search || branch || status || mobilizationStatus ? '필터 적용 중' : '전체 인원'}</span></div>
          {listLoading && <div className="state-panel">인원 목록을 불러오는 중입니다...</div>}
          {listError && <div className="state-panel error-state">{listError}</div>}
          {!listLoading && !listError && people.length === 0 && <div className="state-panel empty-state"><strong>검색 결과가 없습니다</strong><span>검색어나 필터를 바꿔 다시 시도해 보세요.</span></div>}
          {!listLoading && !listError && people.length > 0 && <div className="table-wrap"><table className="people-table"><thead><tr><th>군번</th><th>이름</th><th>군종</th><th>계급</th><th>소속부대</th><th>분대</th><th>상태</th></tr></thead><tbody>{people.map((person) => <tr key={person.military_number} onClick={() => openDetail(person)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') openDetail(person) }}><td className="mono">{person.military_number}</td><td className="person-name">{person.name}</td><td>{person.branch}</td><td>{person.rank ?? '-'}</td><td>{person.unit ?? '-'}</td><td>{person.squad_id ? `${person.squad_id}분대` : '-'}</td><td><StatusBadge status={person.status} /></td></tr>)}</tbody></table></div>}
        </section>
      </section>
    </main>
  )
}

function Header() { return <header className="topbar"><div className="brand-lockup"><span className="brand-mark">31</span><div><p className="eyebrow">31사단 AI TF</p><h1>예비군 관리 대시보드</h1></div></div><span className="system-status"><i /> 운영 중</span></header> }
function StatusBadge({ status }: { status: string }) { return <span className={`status-badge ${status === 'active' ? 'active' : 'leave'}`}>{status === 'active' ? '복무 중' : '휴가 중'}</span> }
function InfoItem({ label, value }: { label: string; value: string | number | null | undefined }) { return <div className="info-item"><span>{label}</span><strong>{value || '-'}</strong></div> }
function Select({ label, value, options, labels, onChange }: { label: string; value: string; options: string[]; labels?: Record<string, string>; onChange: (value: string) => void }) { return <label className="filter-field"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">전체</option>{options.map((option) => <option key={option} value={option}>{labels?.[option] ?? option}</option>)}</select></label> }
function TrainingTable({ progress }: { progress: TrainingProgress[] }) { return <div className="table-wrap"><table><thead><tr><th>연차</th><th>목표시간</th><th>이수시간</th><th>잔여시간</th><th>고발위험</th></tr></thead><tbody>{progress.map((item) => <tr className={item.prosecution_risk ? 'risk-row' : ''} key={item.service_year}><td>{item.service_year}년차</td><td>{item.target_hours}시간</td><td>{item.completed_hours}시간</td><td className={item.remaining_hours > 0 ? 'remaining' : ''}>{item.remaining_hours}시간</td><td>{item.prosecution_risk ? <span className="risk-badge">주의</span> : <span className="clear-mark">-</span>}</td></tr>)}</tbody></table></div> }

export default App
