import { useState } from 'react'
import './ResourceManagement.css'
import ReviewManagement from '../review/ReviewManagement'
import ResourceRosterPage from './ResourceRosterPage'
import OrganizationPage from './OrganizationPage'

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

  return <section className="rm-shell" aria-label="자원관리">
    <nav className="rm-top-tabs" aria-label="자원관리 하위 메뉴">
      {resourceTabs.map(tab => <button
        key={tab.id}
        type="button"
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
    <div className="rm-tab-pane rm-empty-pane" hidden={activeTab !== 'prosecution'} aria-label="고발대상자 빈 화면" />
  </section>
}
