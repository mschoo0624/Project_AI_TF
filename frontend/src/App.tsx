import { useState } from 'react'
import './App.css'
import ReserveManagement from './features/reserve/ReserveManagement'
import ResourceManagement from './features/resource/ResourceManagement'
import ReviewManagement from './features/review/ReviewManagement'

const featureTabs = [
  { id: 'reserve', label: '예비군관리', Component: ReserveManagement },
  { id: 'resource', label: '자원관리', Component: ResourceManagement },
  { id: 'review', label: '보류·연기 검토', Component: ReviewManagement },
] as const

type FeatureTabId = typeof featureTabs[number]['id']
type TabId = 'home' | FeatureTabId

function App() {
  const [openTabs, setOpenTabs] = useState<TabId[]>(['home'])
  const [activeTab, setActiveTab] = useState<TabId>('home')

  const openFeature = (tab: FeatureTabId) => {
    setOpenTabs(tabs => tabs.includes(tab) ? tabs : [...tabs, tab])
    setActiveTab(tab)
  }

  const closeFeature = (tab: FeatureTabId) => {
    setOpenTabs(tabs => tabs.filter(item => item !== tab))
    if (activeTab === tab) setActiveTab('home')
  }

  const activeFeature = featureTabs.find(tab => tab.id === activeTab)
  const ActiveComponent = activeFeature?.Component

  return <div className="app">
    <header className="system-topbar">
      <div className="system-brand">31사단 예비군 업무체계</div>
      <div className="account-area" />
    </header>

    <div className="system-body">
      <aside className="sidebar">
        <div className="user-icon">♙</div>
        {featureTabs.map(tab =>
          <button
            key={tab.id}
            className={`side-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => openFeature(tab.id)}
          >
            {tab.label}
          </button>
        )}
      </aside>

      <main className="workspace">
        <div className="workspace-tabs">
          <button
            className={`workspace-tab ${activeTab === 'home' ? 'selected' : ''}`}
            onClick={() => setActiveTab('home')}
          >
            홈
          </button>

          {featureTabs.map(tab => openTabs.includes(tab.id) &&
            <div key={tab.id} className={`workspace-tab compound ${activeTab === tab.id ? 'selected' : ''}`}>
              <button className="tab-main" onClick={() => setActiveTab(tab.id)}>{tab.label}</button>
              <button className="tab-close" onClick={() => closeFeature(tab.id)} aria-label={`${tab.label} 탭 닫기`}>×</button>
            </div>
          )}
        </div>
        <div className="workspace-content">
        {activeTab === 'home'
          ? <Home onOpenResource={() => openFeature('resource')} />
          : ActiveComponent
            ? <ActiveComponent />
            : null}
        </div>
      </main>
    </div>
  </div>
}

function Home({ onOpenResource }: { onOpenResource: () => void }) {
  return <section className="home">
    <div className="home-box">
      <h1>홈화면입니다</h1>
      <button onClick={onOpenResource}>자원관리</button>
    </div>
  </section>
}

export default App