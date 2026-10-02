import { useEffect, useState } from 'react'
import './ResourceManagement.css'
import ReviewManagement from '../review/ReviewManagement'
import ResourceRosterPage from './ResourceRosterPage'
import OrganizationPage from './OrganizationPage'
import TransferIntakePage from './TransferIntakePage'
import { resourceTabs } from './resourceTabs'
import type { ResourceTabId } from './resourceTabs'

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

type TrainingReviewTarget = {
  military_number: string
  name: string
  branch: string
  rank: string | null
  service_year: number
  squad_id: number | null
  review_years: number[]
  remaining_hours: number
}

type ProsecutionTrainingProgress = {
  service_year: number
  training_plan: { name: string; hours: number }[]
  required_hours: number
  completed_hours: number
  remaining_hours: number
  training_status: string
  prosecution_risk: boolean
  absence_recorded: boolean
  round_escalated: boolean
  review_hints: string[]
}

type ProsecutionTrainingRecord = {
  id: number
  education_year: number
  training_year: number | null
  training_type: string
  training_round: number
  attendance_status: string
  training_hours: number
  notes: string | null
}

type RosterSubTabId = 'people' | 'transfers'
export default function ResourceManagement(
  { initialTab = 'organization', selectedTab, onTabChange }: { initialTab?: ResourceTabId; selectedTab?: ResourceTabId; onTabChange?: (tab: ResourceTabId) => void } = {},
) {
  const [localTab, setLocalTab] = useState<ResourceTabId>(initialTab)
  const activeTab = selectedTab ?? localTab
  const setActiveTab = (tab: ResourceTabId) => { setLocalTab(tab); onTabChange?.(tab) }
  const [rosterSubTab, setRosterSubTab] = useState<RosterSubTabId>('people')
  const [revision, setRevision] = useState(0)
  const [pendingTransfers, setPendingTransfers] = useState(0)

  const refreshResourceData = () => setRevision(value => value + 1)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/transfers`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('전입자 수를 불러오지 못했습니다.')
        return response.json() as Promise<unknown[]>
      })
      .then(transfers => { if (!controller.signal.aborted) setPendingTransfers(transfers.length) })
      .catch(() => { if (!controller.signal.aborted) setPendingTransfers(0) })
    return () => controller.abort()
  }, [revision])

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
      <div className="rm-roster-tab-container">
        <nav className="rm-roster-subtabs" aria-label="편성인원목록 메뉴">
          <button type="button" className={rosterSubTab === 'people' ? 'is-active' : ''}
            aria-current={rosterSubTab === 'people' ? 'page' : undefined} onClick={() => setRosterSubTab('people')}>편성인원목록</button>
          <button type="button" className={rosterSubTab === 'transfers' ? 'is-active' : ''}
            aria-current={rosterSubTab === 'transfers' ? 'page' : undefined} onClick={() => setRosterSubTab('transfers')}>
            전입자{pendingTransfers > 0 && <span className="rm-transfer-tab-count" aria-label={`확인 대기 ${pendingTransfers}명`}>
              {pendingTransfers > 99 ? '99+' : pendingTransfers}
            </span>}
          </button>
        </nav>
        <div className="rm-roster-subtab-pane" hidden={rosterSubTab !== 'people'}>
          <ResourceRosterPage revision={revision} onDataChanged={refreshResourceData} />
        </div>
        <div className="rm-roster-subtab-pane" hidden={rosterSubTab !== 'transfers'}>
          <TransferIntakePage revision={revision} onDataChanged={refreshResourceData} onPendingCountChange={setPendingTransfers} />
        </div>
      </div>
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
  const [reviewTargets, setReviewTargets] = useState<TrainingReviewTarget[]>([])
  const [loading, setLoading] = useState(true)
  const [reviewLoading, setReviewLoading] = useState(true)
  const [error, setError] = useState('')
  const [reviewError, setReviewError] = useState('')
  const [selectedTarget, setSelectedTarget] = useState<ProsecutionTarget | null>(null)

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

  useEffect(() => {
    const controller = new AbortController()
    setReviewLoading(true)
    fetch(`${API_BASE}/reservists/training-review-targets`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('훈련 미이수 검토 목록을 불러오지 못했습니다.')
        return response.json() as Promise<TrainingReviewTarget[]>
      })
      .then(data => { if (!controller.signal.aborted) { setReviewTargets(data); setReviewError('') } })
      .catch(cause => { if (!controller.signal.aborted) setReviewError(cause instanceof Error ? cause.message : '훈련 미이수 검토 목록을 불러오지 못했습니다.') })
      .finally(() => { if (!controller.signal.aborted) setReviewLoading(false) })
    return () => controller.abort()
  }, [revision])

  return <main className="rm-prosecution-page" aria-busy={loading}>
    <header className="rm-prosecution-heading"><div><p className="rm-prosecution-eyebrow">TRAINING COMPLIANCE</p><h1>고발대상자</h1><p>훈련 종류와 차수에 따른 고발 요건이 확인된 예비군입니다.</p></div><strong>{loading ? '확인 중...' : `${targets.length}명`}</strong></header>
    {loading && <p className="rm-list-message">고발대상자 목록을 불러오는 중입니다...</p>}
    {error && <p className="rm-org-error">{error}</p>}
    {!loading && !error && targets.length === 0 && <p className="rm-list-message">현재 고발대상자가 없습니다.</p>}
    {!loading && !error && targets.length > 0 && <div className="rm-prosecution-table-wrap"><table className="rm-prosecution-table"><thead><tr><th>군번</th><th>성명</th><th>복무연차</th><th>분대</th><th>고발 사유</th><th>연속 무단불참 (참고)</th></tr></thead><tbody>{targets.map(target => <tr key={target.military_number} className="rm-prosecution-row" tabIndex={0} onClick={() => setSelectedTarget(target)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedTarget(target) } }}><td className="mono">{target.military_number}</td><td><strong>{target.name}</strong><small>{target.branch} · {target.rank ?? '-'}</small></td><td>{target.service_year ? `${target.service_year}년차` : '-'}</td><td>{target.squad_id ? `${target.squad_id}분대` : '미편성'}</td><td><span className="rm-prosecution-badge">{target.prosecution_reason ?? '훈련 요건 충족'}</span><small>{target.target_years.map(year => `${year}년차`).join(', ')}</small></td><td>{target.consecutive_unexcused_absences}회</td></tr>)}</tbody></table></div>}
    <section className="rm-training-review-section" aria-busy={reviewLoading}>
      <header><div><h2>훈련 미이수 검토</h2><p>잔여시간 확인 목록이며 고발대상자 판정과 별도입니다.</p></div><strong>{reviewLoading ? '확인 중...' : `${reviewTargets.length}명`}</strong></header>
      {reviewError && <p className="rm-org-error">{reviewError}</p>}
      {!reviewLoading && !reviewError && reviewTargets.length === 0 && <p className="rm-list-message">검토할 미이수 훈련이 없습니다.</p>}
      {!reviewLoading && !reviewError && reviewTargets.length > 0 && <div className="rm-training-review-table-wrap"><table><thead><tr><th>군번</th><th>성명</th><th>복무연차</th><th>미이수 연차</th><th>잔여시간</th></tr></thead><tbody>{reviewTargets.map(target => <tr key={target.military_number}><td className="mono">{target.military_number}</td><td><strong>{target.name}</strong><small>{target.branch} · {target.rank ?? '-'}</small></td><td>{target.service_year}년차</td><td>{target.review_years.map(year => `${year}년차`).join(', ')}</td><td>{target.remaining_hours}시간</td></tr>)}</tbody></table></div>}
    </section>
    {selectedTarget && <ProsecutionTargetProfile target={selectedTarget} onClose={() => setSelectedTarget(null)} />}
  </main>
}

function ProsecutionTargetProfile({ target, onClose }: { target: ProsecutionTarget; onClose: () => void }) {
  const [progress, setProgress] = useState<ProsecutionTrainingProgress[]>([])
  const [records, setRecords] = useState<ProsecutionTrainingRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/reservists/${encodeURIComponent(target.military_number)}/training-hours`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('훈련 이력을 불러오지 못했습니다.')
        return response.json() as Promise<{ progress: ProsecutionTrainingProgress[]; records: ProsecutionTrainingRecord[] }>
      })
      .then(data => { if (!controller.signal.aborted) { setProgress(data.progress ?? []); setRecords(data.records ?? []) } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '훈련 이력을 불러오지 못했습니다.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [target.military_number])

  return <div className="rm-prosecution-profile" role="dialog" aria-modal="true" aria-label={`${target.name} 훈련 이력`}>
    <header><div><p>PROSECUTION PROFILE</p><h2>{target.name}</h2><span>{target.military_number} · {target.service_year ?? '-'}년차 · {target.branch} · {target.rank ?? '-'}</span></div><button type="button" onClick={onClose} aria-label="프로필 닫기">×</button></header>
    <div className="rm-prosecution-profile-body">
      <div className="rm-prosecution-profile-reason"><strong>고발 사유</strong><span>{target.prosecution_reason ?? '훈련 미이수'}</span></div>
      {loading && <p className="rm-list-message">훈련 이력을 불러오는 중입니다...</p>}
      {error && <p className="rm-list-message rm-error">{error}</p>}
      {!loading && !error && <>
        <h3>연차별 훈련 현황</h3>
        <div className="rm-prosecution-progress">{progress.filter(item => item.service_year > 0).map(item => <div className={item.prosecution_risk ? 'is-risk' : ''} key={item.service_year}><span>{item.service_year}년차</span><small>{item.training_plan.map(plan => plan.name).join(', ') || '훈련 대상 아님'}</small><b>{item.completed_hours}/{item.required_hours}시간 · {item.training_status}</b></div>)}</div>
        <h3>훈련 기록</h3>
        {records.length === 0 ? <p className="rm-list-message">등록된 훈련 기록이 없습니다.</p> : <div className="rm-prosecution-history"><table><thead><tr><th>연차</th><th>훈련연도</th><th>종류</th><th>차수</th><th>출결</th><th>시간</th></tr></thead><tbody>{records.map(record => <tr key={record.id}><td>{record.education_year}년차</td><td>{record.training_year ?? '-'}</td><td>{record.training_type}</td><td>{record.training_round}차</td><td>{record.attendance_status}</td><td>{record.training_hours}시간</td></tr>)}</tbody></table></div>}
      </>}
    </div>
  </div>
}