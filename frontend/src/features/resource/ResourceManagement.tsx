import { useEffect, useState } from 'react'
import './ResourceManagement.css'
import ReviewManagement from '../review/ReviewManagement'
import ResourceRosterPage from './ResourceRosterPage'
import OrganizationPage from './OrganizationPage'
import TransferIntakePage from './TransferIntakePage'
import ProsecutionPage from '../prosecution/ProsecutionPage'
import { resourceTabs } from './resourceTabs'
import type { ResourceTabId } from './resourceTabs'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

type RosterSubTabId = 'people' | 'transfers'

// 업무 Copilot이 보낸 화면 명령 (필터·강조). key가 바뀔 때마다 하위 탭을 다시 맞춥니다.
export type CopilotView = {
  key: number
  subtab: RosterSubTabId
  filter: { label: string; ids: string[] } | null
  highlight: string[]
}

export default function ResourceManagement(
  { initialTab = 'organization', selectedTab, onTabChange, copilotView = null, dataRevision = 0, onClearCopilotFilter, onOpenTrainingEvent }: {
    initialTab?: ResourceTabId
    selectedTab?: ResourceTabId
    onTabChange?: (tab: ResourceTabId) => void
    copilotView?: CopilotView | null
    dataRevision?: number
    onClearCopilotFilter?: () => void
    onOpenTrainingEvent?: (scheduleId: number) => void
  } = {},
) {
  const [localTab, setLocalTab] = useState<ResourceTabId>(initialTab)
  const activeTab = selectedTab ?? localTab
  const setActiveTab = (tab: ResourceTabId) => { setLocalTab(tab); onTabChange?.(tab) }
  const [rosterSubTab, setRosterSubTab] = useState<RosterSubTabId>('people')
  const [localRevision, setRevision] = useState(0)
  const [pendingTransfers, setPendingTransfers] = useState(0)
  const revision = localRevision + dataRevision
  const copilotKey = copilotView?.key
  const copilotSubtab = copilotView?.subtab

  const [seenCopilotKey, setSeenCopilotKey] = useState(copilotKey)
  if (copilotKey !== seenCopilotKey) {
    setSeenCopilotKey(copilotKey)
    if (copilotSubtab) setRosterSubTab(copilotSubtab)
  }

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
          <ResourceRosterPage revision={revision} onDataChanged={refreshResourceData}
            copilotFilter={copilotView?.filter ?? null} onClearCopilotFilter={onClearCopilotFilter}
            onOpenTrainingEvent={onOpenTrainingEvent} />
        </div>
        <div className="rm-roster-subtab-pane" hidden={rosterSubTab !== 'transfers'}>
          <TransferIntakePage revision={revision} onDataChanged={refreshResourceData} onPendingCountChange={setPendingTransfers}
            highlightIds={copilotView?.highlight ?? []} />
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
      <ProsecutionPage revision={revision} />
    </div>
  </section>
}
