import { useEffect, useState } from 'react'
import './ResourceManagement.css'
import ReviewManagement from '../review/ReviewManagement'
import ResourceRosterPage from './ResourceRosterPage'
import OrganizationPage from './OrganizationPage'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

type ProsecutionTarget = {
  military_number: string
  name: string
  branch: string
  rank: string | null
  service_year: number | null
  squad_id: number | null
  mobilization_status: string | null
  prosecution_reason: string | null
  consecutive_unexcused_absences: number
  target_years: number[]
}

type ResourceTabId = 'roster' | 'organization' | 'hold' | 'travel' | 'prosecution'

const resourceTabs: { id: ResourceTabId; label: string }[] = [
  { id: 'roster', label: '편성인원목록' },
  { id: 'organization', label: '전투편성기구도' },
  { id: 'hold', label: '보류자/연기자' },
  { id: 'travel', label: '출국자/귀국자' },
  { id: 'prosecution', label: '고발대상자' },
]

export default function ResourceManagement(
  { initialTab = 'organization' }: { initialTab?: ResourceTabId } = {},
) {
  const [activeTab, setActiveTab] = useState<ResourceTabId>(initialTab)
  const [revision, setRevision] = useState(0)

  const refreshResourceData = () => setRevision(value => value + 1)

  return <section className={`rm-shell${activeTab === 'organization' ? ' rm-shell--organization' : ''}`} aria-label="자원관리">
    <nav className="rm-top-tabs" aria-label="자원관리 하위 메뉴">
      {resourceTabs.map(tab => <button
        key={tab.id}
        type="button"
        aria-label={`${tab.label} 화면 열기`}
        className={`rm-top-tab ${activeTab === tab.id ? 'is-active' : ''}`}
        aria-current={activeTab === tab.id ? 'page' : undefined}
        onClick={() => setActiveTab(tab.id)}
      >
        {tab.label}
      </button>)}
    </nav>

    <div className="rm-tab-pane" hidden={activeTab !== 'roster'}>
      <ResourceRosterPage revision={revision} />
    </div>
    <div className="rm-tab-pane" hidden={activeTab !== 'organization'}>
      <OrganizationPage revision={revision} onDataChanged={refreshResourceData} />
    </div>
    <div className="rm-tab-pane" hidden={activeTab !== 'hold'}>
      <ReviewManagement />
    </div>
    <div className="rm-tab-pane rm-empty-pane" hidden={activeTab !== 'travel'} aria-label="출국자/귀국자 빈 화면" />
    <div id="resource-prosecution" className="rm-tab-pane" hidden={activeTab !== 'prosecution'}>
      <ProsecutionTargets revision={revision} />
    </div>
  </section>
}

function ProsecutionTargets({ revision }: { revision: number }) {
  const [targets, setTargets] = useState<ProsecutionTarget[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    fetch(`${API_BASE}/reservists/prosecution-targets`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('고발대상자 목록을 불러오지 못했습니다.')
        return response.json() as Promise<ProsecutionTarget[]>
      })
      .then(data => { if (!controller.signal.aborted) { setTargets(data); setError('') } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '고발대상자 목록을 불러오지 못했습니다.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [revision])

  return <main className="rm-prosecution-page" aria-busy={loading}>
    <header className="rm-prosecution-heading"><div><p className="rm-prosecution-eyebrow">TRAINING COMPLIANCE</p><h1>고발대상자</h1><p>훈련 미이수 및 연속 무단불참 기준에 해당하는 예비군입니다.</p></div><strong>{loading ? '확인 중...' : `${targets.length}명`}</strong></header>
    {loading && <p className="rm-list-message">고발대상자 목록을 불러오는 중입니다...</p>}
    {error && <p className="rm-org-error">{error}</p>}
    {!loading && !error && targets.length === 0 && <p className="rm-list-message">현재 고발대상자가 없습니다.</p>}
    {!loading && !error && targets.length > 0 && <div className="rm-prosecution-table-wrap"><table className="rm-prosecution-table"><thead><tr><th>군번</th><th>성명</th><th>복무연차</th><th>분대</th><th>고발 사유</th><th>무단불참</th></tr></thead><tbody>{targets.map(target => <tr key={target.military_number}><td className="mono">{target.military_number}</td><td><strong>{target.name}</strong><small>{target.branch} · {target.rank ?? '-'}</small></td><td>{target.service_year ? `${target.service_year}년차` : '-'}</td><td>{target.squad_id ? `${target.squad_id}분대` : '미편성'}</td><td><span className="rm-prosecution-badge">{target.prosecution_reason ?? '훈련 미이수'}</span><small>{target.target_years.map(year => `${year}년차`).join(', ')}</small></td><td>{target.consecutive_unexcused_absences}회</td></tr>)}</tbody></table></div>}
  </main>
}
