import { useEffect, useState } from 'react'
import './App.css'

type TabId = 'home' | 'resource'
type ResourceView = 'people' | 'assignment'

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

type Squad = {
  id: number
  name: string
  person_count: number
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

function App() {
  const [openTabs, setOpenTabs] = useState<TabId[]>(['home'])
  const [activeTab, setActiveTab] = useState<TabId>('home')

  const openResource = () => {
    setOpenTabs(tabs => tabs.includes('resource') ? tabs : [...tabs, 'resource'])
    setActiveTab('resource')
  }

  const closeResource = () => {
    setOpenTabs(['home'])
    setActiveTab('home')
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">31사단 예비군 업무체계</div>
        <div className="account-area" />
      </header>

      <div className="body">
        <aside className="sidebar">
          <div className="user-icon">♙</div>
          <div className="side-label">예비군관리</div>
          <button
            className={`side-button ${activeTab === 'resource' ? 'active' : ''}`}
            onClick={openResource}
          >
            자원관리
          </button>
        </aside>

        <main className="workspace">
          <div className="tabs">
            <button
              className={`tab ${activeTab === 'home' ? 'selected' : ''}`}
              onClick={() => setActiveTab('home')}
            >
              홈
            </button>

            {openTabs.includes('resource') && (
              <div className={`tab compound ${activeTab === 'resource' ? 'selected' : ''}`}>
                <button className="tab-main" onClick={() => setActiveTab('resource')}>
                  자원관리
                </button>
                <button className="tab-close" onClick={closeResource} aria-label="자원관리 탭 닫기">
                  ×
                </button>
              </div>
            )}
          </div>

          {activeTab === 'home'
            ? <Home onOpenResource={openResource} />
            : <ResourceManagement />}
        </main>
      </div>
    </div>
  )
}

function Home({ onOpenResource }: { onOpenResource: () => void }) {
  return (
    <section className="home">
      <div className="home-box">
        <h1>홈화면입니다</h1>
        <button className="link-button" onClick={onOpenResource}>자원관리</button>
      </div>
    </section>
  )
}

function ResourceManagement() {
  const [view, setView] = useState<ResourceView>('people')

  return (
    <section className="resource">
      <div className="page-title">자원관리</div>

      <div className="subtabs">
        <button className={view === 'people' ? 'selected' : ''} onClick={() => setView('people')}>
          예비군 자원관리
        </button>
        <button className={view === 'assignment' ? 'selected' : ''} onClick={() => setView('assignment')}>
          전투편성기구
        </button>
      </div>

      {view === 'people' ? <PeopleView /> : <AssignmentView />}
    </section>
  )
}

function PeopleView() {
  const [people, setPeople] = useState<Person[]>([])
  const [search, setSearch] = useState('')
  const [branch, setBranch] = useState('')
  const [mobilization, setMobilization] = useState('')
  const [selected, setSelected] = useState<Person | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setLoading(true)
      setError('')
      const params = new URLSearchParams()
      if (search.trim()) params.set('query', search.trim())
      if (branch) params.set('branch', branch)
      if (mobilization) params.set('mobilization_status', mobilization)

      try {
        const res = await fetch(`${API_BASE}/persons?${params.toString()}`, { signal: controller.signal })
        if (!res.ok) throw new Error('인원 목록을 불러오지 못했습니다.')
        setPeople(await res.json())
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setError(e instanceof Error ? e.message : '조회 중 오류가 발생했습니다.')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }, 250)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [search, branch, mobilization])

  const count = (name: string) => people.filter(p => p.branch === name).length

  return (
    <div className="resource-layout">
      <aside className="summary-panel">
        <div className="panel-head">자원현황</div>
        <div className="profile-summary">
          <div className="round-icon">♙</div>
          <div><b>예비군 자원</b><small>현재 조회 기준</small></div>
        </div>
        <div className="stat-line"><span>전체 인원</span><b>{people.length}</b></div>
        <div className="stat-line"><span>편성 인원</span><b>{people.filter(p => p.squad_id).length}</b></div>
        <div className="stat-line"><span>미편성 인원</span><b>{people.filter(p => !p.squad_id).length}</b></div>

        <div className="stat-grid">
          <div><span>육군</span><b>{count('육군')}</b></div>
          <div><span>해군</span><b>{count('해군')}</b></div>
          <div><span>공군</span><b>{count('공군')}</b></div>
          <div><span>해병대</span><b>{count('해병대')}</b></div>
        </div>
      </aside>

      <section className="content-panel">
        <div className="searchbar">
          <label className="search-field">
            <span>조회</span>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="이름 또는 군번을 입력하세요" />
          </label>
          <select value={branch} onChange={e => setBranch(e.target.value)}>
            <option value="">군종 전체</option>
            <option>육군</option><option>해군</option><option>공군</option><option>해병대</option>
          </select>
          <select value={mobilization} onChange={e => setMobilization(e.target.value)}>
            <option value="">동원상태 전체</option>
            <option>동원지정</option><option>동원미지정</option><option>학생예비군</option><option>일부보류</option><option>해당없음</option>
          </select>
          <button className="small-btn">검색</button>
        </div>

        <div className="list-head"><b>예비군 자원목록</b><span>총 {people.length}명</span></div>

        {loading && <div className="empty">자료를 조회하고 있습니다.</div>}
        {error && <div className="empty error">{error}</div>}

        {!loading && !error && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>군번</th><th>성명</th><th>군종</th><th>계급</th><th>소속부대</th>
                  <th>연차</th><th>동원상태</th><th>직책</th><th>분대</th>
                </tr>
              </thead>
              <tbody>
                {people.length === 0 ? (
                  <tr><td colSpan={9} className="no-data">조회된 인원이 없습니다.</td></tr>
                ) : people.map(person => (
                  <tr key={person.military_number} onClick={() => setSelected(person)} className="click-row">
                    <td>{person.military_number}</td>
                    <td className="strong">{person.name}</td>
                    <td>{person.branch}</td>
                    <td>{person.rank ?? '-'}</td>
                    <td>{person.unit ?? '-'}</td>
                    <td>{person.service_year != null ? `${person.service_year}년차` : '-'}</td>
                    <td>{person.mobilization_status ?? '-'}</td>
                    <td>{person.position ?? '-'}</td>
                    <td>{person.squad_id ? `${person.squad_id}분대` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selected && <PersonDialog person={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function PersonDialog({ person, onClose }: { person: Person; onClose: () => void }) {
  return (
    <div className="backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="dialog">
        <div className="dialog-title"><b>예비군 자원 상세</b><button onClick={onClose}>×</button></div>
        <div className="dialog-person"><strong>{person.name}</strong><span>{person.military_number}</span></div>
        <div className="detail-grid">
          <Detail label="군종" value={person.branch} />
          <Detail label="계급" value={person.rank} />
          <Detail label="소속부대" value={person.unit} />
          <Detail label="특기" value={person.specialty} />
          <Detail label="연차" value={person.service_year != null ? `${person.service_year}년차` : null} />
          <Detail label="동원상태" value={person.mobilization_status} />
          <Detail label="직책" value={person.position} />
          <Detail label="분대" value={person.squad_id ? `${person.squad_id}분대` : null} />
        </div>
      </div>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string | null }) {
  return <div className="detail"><span>{label}</span><b>{value ?? '-'}</b></div>
}

function AssignmentView() {
  const [squads, setSquads] = useState<Squad[]>([])
  const [selected, setSelected] = useState('')

  useEffect(() => {
    fetch(`${API_BASE}/squads`)
      .then(res => res.ok ? res.json() : Promise.reject())
      .then((data: Squad[]) => {
        setSquads(data)
        if (data.length) setSelected(String(data[0].id))
      })
      .catch(() => setSquads([]))
  }, [])

  return (
    <div className="assignment-layout">
      <aside className="tree-panel">
        <div className="panel-head">편성대상</div>
        <div className="tree-root">▾ 전투편성</div>
        {squads.map(squad => (
          <button
            key={squad.id}
            className={selected === String(squad.id) ? 'selected' : ''}
            onClick={() => setSelected(String(squad.id))}
          >
            ▪ {squad.name}
          </button>
        ))}
      </aside>

      <section className="assignment-content">
        <div className="commandbar">
          <b>전투편성기구</b>
          <button className="small-btn">편성 실행</button>
        </div>
        <div className="assignment-empty">
          좌측에서 분대를 선택하여 전투편성 정보를 확인합니다.
        </div>
      </section>
    </div>
  )
}

export default App