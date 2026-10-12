import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import ministryLogo from './assets/국방부 마크_컬러본.png'
import { forecastThreshold } from './forecastThreshold'
import ResourceManagement from './features/resource/ResourceManagement'
import TrainingManagementPage from './features/training/TrainingManagementPage'
import { resourceTabs } from './features/resource/resourceTabs'
import type { ResourceTabId } from './features/resource/resourceTabs'
import WorkLogManagement from './features/worklog/WorkLogManagement'
import { countReviewDocuments, fetchBootstrap } from './features/review/api'
import ChatLauncher from './features/chatbot/ChatLauncher'
import LegalChatbot from './features/chatbot/LegalChatbot'
import type { CopilotAction } from './features/chatbot/CopilotChat'
import type { CopilotView } from './features/resource/ResourceManagement'
import noticeBannerImg from './assets/배너.png'
import worklogIcon from './assets/shortcut/worklog.png'
import travelIcon from './assets/shortcut/travel.png'
import holdIcon from './assets/shortcut/hold.png'
import prosecutionIcon from './assets/shortcut/prosecution.png'
import formationIcon from './assets/shortcut/formation.png'
import trainingIcon from './assets/shortcut/training.png'
import noticeIcon from './assets/shortcut/notice.png'
import myPageIcon from "./assets/shortcut/mypage.png";
import Messenger, { MessengerLauncher } from './features/messenger/Messenger'
import { initialConversations, formatAlertTime } from './features/messenger/messengerData'
import type { Conversation } from './features/messenger/messengerData'
import { trainingTabs } from './features/training/trainingtabs'
import type { TrainingTabId } from './features/training/trainingtabs'


const featurePages = [
  { id: 'reserve', label: '부대관리', Component: EmptyReservePage },
  { id: 'resource', label: '자원관리', Component: ResourceManagement },
  { id: 'training', label: '교육훈련', Component: TrainingManagementPage },
  { id: 'worklog', label: '업무일지', Component: WorkLogManagement },
] as const

function EmptyReservePage() {
  return <section className="empty-reserve-page" aria-label="부대관리"><HomeForecastSection /></section>
}
function MyPage() {
  return <section className="mypage" aria-label="마이페이지"><h2>마이페이지</h2></section>
}
type FeaturePageId = typeof featurePages[number]['id']
type PageId = 'home' | FeaturePageId | 'mypage'
type HomeDestination = PageId | 'resource:hold' | 'resource:prosecution' | 'resource:travel'

type IconName = 'person' | 'bell' | 'calendar' | 'check' | 'warning' | 'plus' | 'minus' | 'list' | 'settings' | 'edit' | 'arrow' | 'left' | 'right' | 'inbox'| 'more' | 'task' | 'travel' | 'clipboard' | 'users' | 'star' | 'dashboard' | 'shield' | 'training' | 'notebook'
const pageIcons: Record<FeaturePageId, IconName> = { reserve: 'shield', resource: 'users', training: 'training', worklog: 'notebook' }


function Icon({ name, size = 19 }: { name: IconName; size?: number }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.9, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true as const }
  const drawing = (() => {
    switch (name) {
      case 'person': return <><circle cx="12" cy="7.5" r="3.4" /><path d="M4.7 20c.4-4 3-6 7.3-6s6.9 2 7.3 6" /></>
      case 'bell': return <><path d="M18 8a6 6 0 0 0-12 0c0 7-2 7-2 9h16c0-2-2-2-2-9Z" /><path d="M10 21h4" /></>
      case 'calendar': return <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4m10-4v4M3 10h18m-13 5h3m-3 3h3" /></>
      case 'check': return <><circle cx="12" cy="12" r="9" /><path d="m7.5 12 3 3 6-6" /></>
      case 'warning': return <><path d="M10 4a2.3 2.3 0 0 1 4 0l8 14a2 2 0 0 1-1.8 3H3.8A2 2 0 0 1 2 18Z" /><path d="M12 9v5m0 3h.01" /></>
      case 'plus': return <><circle cx="12" cy="12" r="9" /><path d="M12 7v10M7 12h10" /></>
      case 'minus': return <><circle cx="12" cy="12" r="9" /><path d="M7 12h10" /></>
      case 'list': return <><path d="M9 6h12M9 12h12M9 18h12" /><path d="M4 6h.01M4 12h.01M4 18h.01" /></>
      case 'settings': return <><circle cx="12" cy="12" r="3" /><path d="m10 2 4 0 .5 2.3 2 .8 2-.9 2.8 2.8-.9 2 .8 2 2.3.5v4l-2.3.5-.8 2 .9 2-2.8 2.8-2-.9-2 .8L14 22h-4l-.5-2.3-2-.8-2 .9-2.8-2.8.9-2-.8-2L.5 14v-4l2.3-.5.8-2-.9-2L5.5 2.7l2 .9 2-.8Z" transform="translate(1 0) scale(.92 1)" /></>
      case 'edit': return <><path d="m4 17 0 3 3-.5L20 6.6l-3.6-3.6L4 17Z" /><path d="m14 5 4 4" /></>
      case 'arrow': return <><path d="M4 12h16m-6-6 6 6-6 6" /></>
      case 'left': return <path d="m15 6-6 6 6 6" />
      case 'right': return <path d="m9 6 6 6-6 6" />
      case 'inbox': return <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 14h5l2 3h4l2-3h5" /></>
      case 'more': return <path d="M5 12h.01M12 12h.01M19 12h.01" strokeWidth={3} />
      case 'task': return <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="m8.5 12 2.5 2.5 4.5-5" /></>
      case 'travel': return <path d="M4 8h14m-4-4 4 4-4 4M20 16H6m4-4-4 4 4 4" />
      case 'clipboard': return <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4h6v3H9zM9 12h6m-6 4h4" /></>
      case 'users': return <><circle cx="9" cy="8" r="3.2" /><path d="M3 20c.4-3.6 2.7-5.5 6-5.5s5.6 1.9 6 5.5" /><circle cx="17.5" cy="9" r="2.5" /><path d="M17 14.5c2.4.2 3.8 1.9 4 4.5" /></>
      case 'star': return <path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 17l-5.2 2.7 1-5.9-4.3-4.1 5.9-.8Z" />
      case 'dashboard': return <><rect x="3" y="3" width="8" height="8" rx="1.5" /><rect x="13" y="3" width="8" height="5" rx="1.5" /><rect x="13" y="11" width="8" height="10" rx="1.5" /><rect x="3" y="14" width="8" height="7" rx="1.5" /></>
      case 'shield': return <><path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6l8-3Z" /><path d="m9 12 2 2 4-4" /></>
      case 'training': return <><path d="M2 9l10-5 10 5-10 5L2 9Z" /><path d="M6 11.5V16c0 1.5 2.7 3 6 3s6-1.5 6-3v-4.5" /><path d="M22 9v6" /></>
      case 'notebook': return <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 3v18M12 8h4M12 12h4" /></>    
    
    }

  })()
  return <svg {...common}>{drawing}</svg>
}

// Metrics use the DB; hold/delay alerts use the review inbox document queue.
const demoDashboard = {
  metrics: [
    { label: '전체 대상자', key: 'total_people', detail: '전체 예비군 대상자 수', icon: 'person' },
    { label: '보류자/연기자', key: 'held_or_delayed', detail: '현재 보류·연기 상태 또는 승인 인원', icon: 'person' },
    { label: '고발대상자', key: 'prosecution_people', detail: '무단불참 규칙에 따른 검토 대상', icon: 'person' },
    { label: '금년도 대상자', key: 'training_targets', detail: '현재 연차 훈련 대상 인원', icon: 'calendar' },
    { label: '훈련 완료', key: 'training_completed', detail: '현재 연차 필요시간 이수 인원', icon: 'check' },
    { label: '미응소', key: 'absent_people', detail: '현재 연차 무단불참 기록 인원', icon: 'warning' },
  ] as const,

}

// 예시 데이터 (API 생기면 교체)
const demoTravelCount = 16
const demoWorkAlerts: { title: string; body: string; page: HomeDestination }[] = [
  { title: '교육훈련 일정 관리', body: '10월 5일 1형 훈련 일정 관리가 필요합니다.', page: 'training' },
  { title: '홍보메일 전송', body: '9월 28일, 훈련 대상자 134명을 대상으로 홍보메일 발송을 완료했습니다.', page: 'training' },
]

const demoNotices = [
  { id: 61, type: '긴급공지', title: '12월 31일 ~~~~일정이 있으니 확인 부탁드립니다', author: 'admin01', date: '2026-10-07', writtenAt: '2026-10-07 09:00:00', approver: '승인자 예시', views: 120, content: '12월 31일 일정이 예정되어 있으니 대상자 확인을 부탁드립니다.\n\n자세한 사항은 담당자에게 문의해 주세요.' },
  ...[41, 23, 22, 21, 20].map(id => ({ id, type: '일반공지', title: '12월 31일 ~~~~일정이 있으니 확인 부탁드립니다', author: 'admin01', date: '2026-10-07', writtenAt: '2026-10-07 09:00:00', approver: '승인자 예시', views: 120, content: '공지사항 내용 예시입니다.\n실제 데이터가 연결되면 이 자리에 본문이 표시됩니다.' })),
]
type Notice = typeof demoNotices[number]

type Composition = {
  officers: number
  soldiers: number
  other: number
  service_years: Record<string, number>
  positions: { label: string; count: number }[]
}

function isComposition(value: unknown): value is Composition {
  if (!value || typeof value !== 'object') return false
  const data = value as Composition
  const isCount = (count: unknown) => typeof count === 'number' && Number.isInteger(count) && count >= 0
  return [data.officers, data.soldiers, data.other].every(isCount)
    && !!data.service_years && typeof data.service_years === 'object'
    && Object.values(data.service_years).every(isCount)
    && Array.isArray(data.positions)
    && data.positions.every(item => !!item && typeof item.label === 'string' && isCount(item.count))
}

function CompositionPanel({ data, error }: { data: Composition | null; error: string }) {
  const colors = ['#2162e5', '#619eef', '#b8d5fc', '#c4cbd5']
  const years = Object.entries(data?.service_years ?? {})
  const maximum = Math.max(1, ...(data?.positions.map(item => item.count) ?? []))
  return <section className="home-composition" aria-label="DB 대상자 구성" aria-busy={!data && !error}>
    <h2>대상자 구성</h2>
    <div className="home-composition-head">
      <div className="home-composition-tile"><span>간부</span><strong>{data?.officers.toLocaleString('ko-KR') ?? '—'} <small>명</small></strong></div>
      <div className="home-composition-tile"><span>일반 병사</span><strong>{data?.soldiers.toLocaleString('ko-KR') ?? '—'} <small>명</small></strong></div>
    </div>
    {!!data?.other && <p className="home-data-note">계급 미분류 {data.other}명</p>}
    <h3>일반 병사 연차별</h3>
    <div className="home-service-bar" aria-label={years.map(([label, count]) => `${label} ${count}명`).join(', ')}>
      {years.map(([label, count], index) => <span key={label} style={{ flex: `${count} 1 0%`, backgroundColor: colors[index] }} />)}
    </div>
    <div className="home-service-legend">{years.filter(([, count], index) => index < 3 || count > 0).map(([label, count]) => <span key={label}><i style={{ backgroundColor: colors[years.findIndex(([key]) => key === label)] }} />{label} {count.toLocaleString('ko-KR')}명</span>)}</div>
    <div className="home-composition-divider" />
    <h3>보직별 인원</h3>
    <div className="home-category-list">{data?.positions.map(item => <div className="home-category-row" key={item.label}>
      <span title={item.label}>{item.label}</span>
      <div className="home-category-track"><i style={{ width: `${item.count / maximum * 100}%` }} /></div>
      <strong>{item.count.toLocaleString('ko-KR')}명</strong>
    </div>)}</div>
    {!data && <p className="home-data-note" role={error ? 'alert' : 'status'}>{error || '대상자 구성 조회 중…'}</p>}
    {data && data.positions.length === 0 && <p className="home-data-note">등록된 인원이 없습니다.</p>}
  </section>
}

type Schedule = { id: number; date: string; title: string }
const initialSchedules: Schedule[] = [
  { id: 1, date: '01/14', title: '동원훈련 1형 예정' },
  { id: 2, date: '01/15', title: '월 중간 결산' },
]

function SidebarClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const pad = (value: number) => String(value).padStart(2, '0')
  const date = `${now.getFullYear()}.${pad(now.getMonth() + 1)}.${pad(now.getDate())} (${weekdayLabels[now.getDay()]})`
  return <div className="sidebar-clock" role="timer" aria-label={`현재 시각 ${pad(now.getHours())}시 ${pad(now.getMinutes())}분`}>
    <time dateTime={now.toISOString()}>
      <span className="sidebar-clock-main">{pad(now.getHours())}:{pad(now.getMinutes())}</span>
      <span className="sidebar-clock-sec">:{pad(now.getSeconds())}</span>
    </time>
    <small>{date}</small>
  </div>
}

function App() {
  const [homeRevision, setHomeRevision] = useState(0)
  const [activePage, setActivePage] = useState<PageId>('home')
  const [resourceLanding, setResourceLanding] = useState<ResourceTabId>('organization')
  const [trainingLanding, setTrainingLanding] = useState<TrainingTabId>('schedule')
  const [trainingScheduleFocus, setTrainingScheduleFocus] = useState<number | null>(null)
  const [expandedMenus, setExpandedMenus] = useState<Set<FeaturePageId>>(() => new Set())
  const [chatOpen, setChatOpen] = useState(false)
  const [copilotView, setCopilotView] = useState<CopilotView | null>(null)
  const [dataRevision, setDataRevision] = useState(0)
  const [messengerOpen, setMessengerOpen] = useState(false)
  const [messengerRoom, setMessengerRoom] = useState<number | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>(initialConversations)
  const unreadTotal = conversations.reduce((sum, item) => sum + item.unread, 0)
  const contactAlerts = conversations.filter(item => item.unread > 0).map(item => ({
    id: item.id,
    title: `${item.name}님에게 메시지가 왔습니다.`,
    time: formatAlertTime(item.messages[item.messages.length - 1].sentAt),
  }))
  const changeMessengerRoom = (roomId: number | null) => {
    setMessengerRoom(roomId)
    if (roomId !== null) setConversations(list => list.map(item => item.id === roomId ? { ...item, unread: 0 } : item))
  }
  const openMessenger = (roomId: number | null = null) => {
    setChatOpen(false)
    setMessengerOpen(true)
    changeMessengerRoom(roomId)
  }
  const sendMessengerMessage = (roomId: number, text: string) => setConversations(list => list.map(item =>
    item.id === roomId ? { ...item, messages: [...item.messages, { id: Date.now(), from: 'me' as const, text, sentAt: Date.now() }] } : item))
  // Copilot의 화면 명령. 응답마다 navigate가 먼저 와서 이전 필터·강조를 지웁니다.
  const runCopilotAction = (action: CopilotAction) => {
    if (action.tab !== 'roster') return
    setResourceLanding('roster')
    setActivePage('resource')
    setCopilotView(current => {
      const next: CopilotView = {
        key: (current?.key ?? 0) + 1,
        subtab: action.subtab ?? current?.subtab ?? 'people',
        filter: current?.filter ?? null,
        highlight: current?.highlight ?? [],
      }
      if (action.type === 'navigate') { next.filter = null; next.highlight = [] }
      else if (action.type === 'filter') next.filter = { label: action.label ?? 'Copilot 검색', ids: action.ids }
      else if (next.subtab === 'people') next.filter = { label: action.ids.join(', '), ids: action.ids }
      else next.highlight = action.ids
      return next
    })
  }
  const navigate = (destination: HomeDestination) => {
    if (destination === 'home') setHomeRevision(value => value + 1)
    if (destination === 'resource:hold' || destination === 'resource:prosecution' || destination === 'resource:travel') {
      setResourceLanding(destination === 'resource:hold' ? 'hold' : destination === 'resource:prosecution' ? 'prosecution' : 'travel')
      setActivePage('resource')
    } else {
      setResourceLanding('organization')
      if (destination === 'training') setTrainingScheduleFocus(null)
      if (destination === 'training') setTrainingLanding('schedule')
      setActivePage(destination)
    }
  }
  const activeFeature = featurePages.find(page => page.id === activePage)
  const ActiveComponent = activeFeature?.Component

  return <div className={`app ${chatOpen ? 'chat-open' : ''} ${messengerOpen ? 'messenger-open' : ''}`}>
    <header className="system-topbar">
      <div className="system-brand"><img className="system-brand-logo" src={ministryLogo} alt="대한민국 국방부" />
      <div className="system-brand-title"><span>국방동원정보체계 2.0</span><small>DEFENSE MOBILIZATION INFORMATION SYSTEM</small></div>
    </div>
      <div className="account-area" />
    </header>
    <div className="system-body">
      <aside className="sidebar" aria-label="주 메뉴">
        <SidebarClock />
        <button className={`side-button home-button ${activePage === 'home' ? 'active' : ''}`} type="button" onClick={() => navigate('home')} aria-label="대시보드로 이동" title="대시보드로 이동">
          <Icon name="dashboard" size={20} />대시보드
        </button>
        {featurePages.map(page => {
          const hasSubmenus = page.id === 'resource' || page.id === 'worklog' || page.id === 'training'
          const expanded = expandedMenus.has(page.id)
          return <div key={page.id} className="side-menu-group">
            <div className={`side-menu-row ${activePage === page.id ? 'active' : ''}`}>
              <button type="button" className="side-button" onClick={() => navigate(page.id)}><Icon name={pageIcons[page.id]} size={20} />{page.label}</button>
              {hasSubmenus && <button type="button" className="side-menu-toggle" aria-label={`${page.label} 하위 메뉴 ${expanded ? '접기' : '펼치기'}`}
                aria-expanded={expanded} aria-controls={`submenu-${page.id}`}
                onClick={() => setExpandedMenus(current => { const next = new Set(current); if (next.has(page.id)) next.delete(page.id); else next.add(page.id); return next })}>{expanded ? '▲' : '▼'}</button>}
            </div>
            {hasSubmenus && <div id={`submenu-${page.id}`} className="side-submenu" hidden={!expanded}>
              {page.id === 'resource' ? resourceTabs.map(tab => <button key={tab.id} type="button"
                aria-current={activePage === 'resource' && resourceLanding === tab.id ? 'page' : undefined}
                onClick={() => { setResourceLanding(tab.id); setActivePage('resource') }}>{tab.label}</button>)

                : page.id === 'training' ? trainingTabs.map(tab => <button key={tab.id} type="button"
                  aria-current={activePage === 'training' && trainingLanding === tab.id ? 'page' : undefined}
                  onClick={() => { setTrainingScheduleFocus(null); setTrainingLanding(tab.id); setActivePage('training') }}>{tab.label}</button>)
                : <button type="button" aria-current={activePage === 'worklog' ? 'page' : undefined} onClick={() => navigate('worklog')}>업무일지 목록</button>}
            </div>}
          </div>
        })}
        <MessengerLauncher open={messengerOpen} unread={unreadTotal}
          onToggle={() => messengerOpen ? setMessengerOpen(false) : openMessenger(messengerRoom)} />
        <ChatLauncher open={chatOpen} onToggle={() => { setMessengerOpen(false); setChatOpen(value => !value) }} />
      </aside>
      <main className="workspace">
        <div className="workspace-content">
          {activePage === 'home'
            ? <Home key={homeRevision} onNavigate={navigate} contactAlerts={contactAlerts} onOpenMessenger={openMessenger} />
            : activePage === 'resource' ? <ResourceManagement selectedTab={resourceLanding} onTabChange={setResourceLanding}
              copilotView={copilotView} dataRevision={dataRevision}
              onOpenTrainingEvent={scheduleId => { setTrainingScheduleFocus(scheduleId); setActivePage('training') }}
              onClearCopilotFilter={() => setCopilotView(current => current && { ...current, filter: null })} />
  : activePage === 'training' ? <TrainingManagementPage selectedTab={trainingLanding} onTabChange={setTrainingLanding}
              focusScheduleId={trainingScheduleFocus} onScheduleFocusHandled={() => setTrainingScheduleFocus(null)}
              onDataChanged={() => setDataRevision(value => value + 1)} />
            : activePage === 'mypage' ? <MyPage />
            : ActiveComponent ? <ActiveComponent key={activePage} /> : null}
        </div>
      </main>
      <LegalChatbot open={chatOpen} onClose={() => setChatOpen(false)}
        onCopilotAction={runCopilotAction} onDataChanged={() => setDataRevision(value => value + 1)} />
      <Messenger open={messengerOpen} conversations={conversations} roomId={messengerRoom}
        onRoomChange={changeMessengerRoom} onSend={sendMessengerMessage} onClose={() => setMessengerOpen(false)} />
    </div>
  </div>
}

const weekdayLabels = ['일', '월', '화', '수', '목', '금', '토']

function MiniCalendar({ schedules, onPickDate }: { schedules: Schedule[]; onPickDate: (date: string) => void }) {
  const [today] = useState(() => new Date())
  const [cursor, setCursor] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1))
  const year = cursor.getFullYear()
  const month = cursor.getMonth()
  const leading = new Date(year, month, 1).getDay()
  const cells = Array.from({ length: 42 }, (_, i) => new Date(year, month, 1 - leading + i))
  const isToday = (d: Date) => d.getFullYear() === today.getFullYear() && d.getMonth() === today.getMonth() && d.getDate() === today.getDate()
  const toKey = (d: Date) => `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
  const dayClass = (d: Date) => ['home-calendar-day', d.getDay() === 0 ? 'is-sun' : d.getDay() === 6 ? 'is-sat' : '', d.getMonth() !== month ? 'is-other' : '', isToday(d) ? 'is-today' : ''].filter(Boolean).join(' ')
  return <section className="home-calendar-card" aria-label="월간 달력">
    <div className="home-calendar-head">
      <button type="button" aria-label="이전 달" onClick={() => setCursor(new Date(year, month - 1, 1))}><Icon name="left" size={15} /></button>
      <strong>{year}년 {month + 1}월</strong>
      <button type="button" aria-label="다음 달" onClick={() => setCursor(new Date(year, month + 1, 1))}><Icon name="right" size={15} /></button>
    </div>
    <div className="home-calendar-grid" role="grid">
      {weekdayLabels.map((l, i) => <span key={l} role="columnheader" className={`home-calendar-weekday ${i === 0 ? 'is-sun' : i === 6 ? 'is-sat' : ''}`}>{l}</span>)}
      {cells.map(d => {
        const key = toKey(d)
        const items = schedules.filter(s => s.date === key)
        return <button type="button" key={d.getTime()} role="gridcell"
          className={`${dayClass(d)}${items.length ? ' has-schedule' : ''}`}
          aria-current={isToday(d) ? 'date' : undefined}
          aria-label={`${d.getMonth() + 1}월 ${d.getDate()}일${items.length ? `, 일정 ${items.length}건` : ''}, 일정 추가`}
          title={items.length ? items.map(s => s.title).join('\n') : `${key} 일정 추가`}
          onClick={() => onPickDate(key)}><span>{d.getDate()}</span></button>
      })}
      </div>
  </section>
}

function Home({ onNavigate, contactAlerts, onOpenMessenger }: {
  onNavigate: (page: HomeDestination) => void
  contactAlerts: { id: number; title: string; time: string }[]
  onOpenMessenger: (roomId?: number | null) => void
}) {
  const [reviewCounts, setReviewCounts] = useState<number | null>(null)
  const [reviewError, setReviewError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted) return
      try {
        const payload = await fetchBootstrap(controller.signal)
        if (!controller.signal.aborted) setReviewCounts(countReviewDocuments(payload.queue))
      } catch {
        if (!controller.signal.aborted) setReviewError('검토함 서류 수를 불러오지 못했습니다.')
      }
    })
    return () => controller.abort()
  }, [])
  const [summary, setSummary] = useState<(Record<typeof demoDashboard.metrics[number]['key'], number> & { composition: Composition }) | null>(null)
  const [summaryError, setSummaryError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    const refresh = async () => {
      try {
        const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? '/api'}/dashboard/summary`, { signal: controller.signal, cache: 'no-store' })
        if (!response.ok) throw new Error('인원 현황을 불러오지 못했습니다.')
        const payload = await response.json()
        if (!isComposition(payload.composition) || !demoDashboard.metrics.every(metric => Number.isInteger(payload[metric.key]) && payload[metric.key] >= 0)) {
          throw new Error('인원 현황 응답을 확인해 주세요. 백엔드 재시작이 필요할 수 있습니다.')
        }
        if (!controller.signal.aborted) setSummary(payload)
        setSummaryError('')
      } catch (error) {
        if (!controller.signal.aborted) {
          setSummary(null)
          setSummaryError(error instanceof Error ? error.message : '인원 조회 오류')
        }
      }
    }
    void Promise.resolve().then(() => { if (!controller.signal.aborted) return refresh() })
    return () => controller.abort()
  }, [])
  const [schedules, setSchedules] = useState<Schedule[]>(initialSchedules)
  const [selectedSchedule, setSelectedSchedule] = useState<number | null>(null)
  const [editingSchedule, setEditingSchedule] = useState<number | 'new' | null>(null)
  const [draftDate, setDraftDate] = useState('')
  const [draftTitle, setDraftTitle] = useState('')
  const [showScheduleList, setShowScheduleList] = useState(true)
  const [showScheduleInfo, setShowScheduleInfo] = useState(false)
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [noticeDetail, setNoticeDetail] = useState<Notice | null>(null)
  const [notices, setNotices] = useState<Notice[]>(demoNotices)
  const [noticeWriting, setNoticeWriting] = useState(false)
  const [draftNotice, setDraftNotice] = useState({ type: '일반공지', title: '', author: '', approver: '', content: '' })
  const openNoticeList = () => { setNoticeDetail(null); setNoticeWriting(false); setNoticeOpen(true) }
  const openNoticeDetail = (notice: Notice) => { setNoticeDetail(notice); setNoticeWriting(false); setNoticeOpen(true) }
  const closeNotice = () => { setNoticeOpen(false); setNoticeDetail(null); setNoticeWriting(false) }
  const openNoticeWrite = () => {
    setDraftNotice({ type: '일반공지', title: '', author: '', approver: '', content: '' })
    setNoticeDetail(null)
    setNoticeWriting(true)
  }
  const saveNotice = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!draftNotice.title.trim() || !draftNotice.author.trim() || !draftNotice.content.trim()) return
    const now = new Date()
    const pad = (value: number) => String(value).padStart(2, '0')
    const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    const writtenAt = `${date} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
    setNotices(prev => [{
      id: Math.max(0, ...prev.map(n => n.id)) + 1,
      type: draftNotice.type,
      title: draftNotice.title.trim(),
      author: draftNotice.author.trim(),
      approver: draftNotice.approver.trim() || '-',
      content: draftNotice.content,
      date, writtenAt, views: 0,
    }, ...prev])
    setNoticeWriting(false)
  }

  const renderNotice = (n: Notice) => <li key={n.id}>
    <button type="button" className="home-notice-row" onClick={() => openNoticeDetail(n)}>
      <span>{n.id}</span>
      <span className="home-notice-title">{n.type === '긴급공지' && <b className="home-notice-urgent">[긴급] </b>}{n.title}</span>
      <span>{n.author}</span>
      <span>{n.date}</span>
    </button>
  </li>

  const editSchedule = (schedule?: Schedule) => {
    setEditingSchedule(schedule?.id ?? 'new')
    setDraftDate(schedule?.date ?? '')
    setDraftTitle(schedule?.title ?? '')
  }
  const saveSchedule = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!/^\d{2}\/\d{2}$/.test(draftDate) || !draftTitle.trim()) return
    if (editingSchedule === 'new') {
      setSchedules(prev => [...prev, { id: Date.now(), date: draftDate, title: draftTitle.trim() }])
    } else if (typeof editingSchedule === 'number') {
      setSchedules(prev => prev.map(schedule => schedule.id === editingSchedule ? { ...schedule, date: draftDate, title: draftTitle.trim() } : schedule))
    }
    setEditingSchedule(null)
  }
  const removeSelectedSchedule = () => {
    if (selectedSchedule === null) return
    setSchedules(prev => prev.filter(schedule => schedule.id !== selectedSchedule))
    setSelectedSchedule(null)
  }
  const pickScheduleDate = (date: string) => {
  setShowScheduleList(true)
  setShowScheduleInfo(false)
  setEditingSchedule('new')
  setDraftDate(date)
  setDraftTitle('')
}


  const shortcuts: { label: string; icon: string | IconName; page: HomeDestination; onClick?: () => void }[] = [
    { label: '보류자/연기자', icon: holdIcon, page: 'resource:hold'},
    { label: '출국자/귀국자', icon: travelIcon, page: 'resource:travel'},
    { label: '고발대상자', icon: prosecutionIcon, page: 'resource:prosecution'},
    { label: '업무일지 작성', icon: worklogIcon, page: 'worklog' },
    { label: '전투편성기구도', icon: formationIcon, page: 'resource' },
    { label: '교육훈련', icon: trainingIcon, page: 'training' },
    { label: '공지사항', icon: noticeIcon, page: 'home', onClick: openNoticeList },
    { label: '마이페이지', icon: myPageIcon, page: 'mypage' },
  ] 

  return <section className="home-dashboard" aria-label="홈 대시보드">
    <div className="home-left-column">
      <section className="home-user-card" aria-label="사용자 정보">
        <strong>담당자</strong>
        <span>소속 정보 미연결</span>
        <small>화면 예시 · 실데이터 미연결</small>
      </section>

    <MiniCalendar schedules={schedules} onPickDate={pickScheduleDate} />

      <section className="home-schedule-card" aria-label="주요 일정">
        <div className="home-schedule-toolbar">
          <span className="home-schedule-heading"><Icon name="bell" size={19} />주요 일정</span>
          <div className="home-toolbar-actions">
            <button type="button" className="home-icon-button" title="예시 일정 추가" aria-label="예시 일정 추가" onClick={() => editSchedule()}><Icon name="plus" /></button>
            <button type="button" className="home-icon-button" title="선택한 예시 일정 삭제" aria-label="선택한 예시 일정 삭제" disabled={selectedSchedule === null} onClick={removeSelectedSchedule}><Icon name="minus" /></button>
            <button type="button" className="home-icon-button" title={showScheduleList ? '일정 목록 접기' : '일정 목록 펼치기'} aria-label={showScheduleList ? '일정 목록 접기' : '일정 목록 펼치기'} onClick={() => setShowScheduleList(v => !v)}><Icon name="list" /></button>
            <button type="button" className="home-icon-button" title="일정 안내" aria-label="일정 안내" onClick={() => setShowScheduleInfo(v => !v)}><Icon name="settings" /></button>
          </div>
        </div>
        {showScheduleInfo && <p className="home-schedule-info">예시 일정은 현재 화면에서만 변경되며 서버에 저장되지 않습니다.</p>}
        {showScheduleList && <div className="home-schedule-list">
          {schedules.map(schedule =>
            <div className={`home-schedule-row ${selectedSchedule === schedule.id ? 'selected' : ''}`} key={schedule.id}>
              <button type="button" className="home-schedule-select" onClick={() => setSelectedSchedule(selectedSchedule === schedule.id ? null : schedule.id)} aria-pressed={selectedSchedule === schedule.id}>
                <span className="home-dot" />{schedule.date} {schedule.title}
              </button>
              <button type="button" className="home-schedule-edit" title="일정 수정" aria-label={`${schedule.date} ${schedule.title} 수정`} onClick={() => editSchedule(schedule)}><Icon name="edit" size={18} /></button>
            </div>
          )}
          {schedules.length === 0 && <p className="home-schedule-empty">예시 일정이 없습니다.</p>}
        </div>}
        {editingSchedule !== null && <form className="home-schedule-form" onSubmit={saveSchedule}>
          <input aria-label="날짜" value={draftDate} placeholder="MM/DD" pattern="[0-9]{2}/[0-9]{2}" onChange={e => setDraftDate(e.target.value)} required />
          <input aria-label="일정 내용" value={draftTitle} placeholder="일정 내용" onChange={e => setDraftTitle(e.target.value)} required />
          <button type="submit">저장</button><button type="button" onClick={() => setEditingSchedule(null)}>취소</button>
        </form>}
        {!showScheduleInfo && editingSchedule === null && schedules.length === 0 && <p className="home-schedule-add-hint">+ 버튼으로 일정을 추가하세요.</p>}
      </section>

      <DailyPanel />
    </div>

    <section className="home-notice-banner" aria-label="공지사항" style={{ backgroundImage: `url("${noticeBannerImg}")` }}>
      <div className="home-notice-content">
        <span className="home-panel-chip"><Icon name="calendar" size={14} />공지사항</span>
        <div className="home-notice-head-row"><span>번호</span><span>제목</span><span>글쓴이</span><span>등록일</span></div>
        <ul className="home-notice-list">{notices.slice(0, 5).map(renderNotice)}</ul>
        <button type="button" className="home-notice-more" aria-label="공지사항 전체 보기" onClick={openNoticeList}><Icon name="more" size={16} /></button>
      </div>
      {noticeOpen && <div className="home-notice-backdrop" onClick={closeNotice}>
        <div className="home-notice-modal" role="dialog" aria-modal="true" aria-label="공지사항" onClick={e => e.stopPropagation()}>
          <button type="button" className="home-notice-close" aria-label="닫기" onClick={closeNotice}>✕</button>
<h2 className={`home-notice-modal-title${noticeDetail && !noticeWriting ? ' is-detail' : ''}`}>{noticeWriting ? '공지사항 작성' : noticeDetail ? noticeDetail.type : '공지사항'}</h2>
                    {noticeWriting ? <form className="home-notice-write" onSubmit={saveNotice}>
            <label>게시형태
              <select value={draftNotice.type} onChange={e => setDraftNotice(d => ({ ...d, type: e.target.value }))}>
                <option value="일반공지">일반</option>
                <option value="긴급공지">긴급</option>
              </select>
            </label>
            <label>제목
              <input value={draftNotice.title} onChange={e => setDraftNotice(d => ({ ...d, title: e.target.value }))} placeholder="제목을 입력하세요" required />
            </label>
            <div className="home-notice-write-row">
              <label>작성자
                <input value={draftNotice.author} onChange={e => setDraftNotice(d => ({ ...d, author: e.target.value }))} required />
              </label>
              <label>승인자
                <input value={draftNotice.approver} onChange={e => setDraftNotice(d => ({ ...d, approver: e.target.value }))} />
              </label>
            </div>
            <label>내용
              <textarea rows={10} value={draftNotice.content} onChange={e => setDraftNotice(d => ({ ...d, content: e.target.value }))} placeholder="내용을 입력하세요" required />
            </label>
            <div className="home-notice-write-actions">
              <button type="submit" className="home-notice-back">저장</button>
              <button type="button" className="home-notice-cancel" onClick={() => setNoticeWriting(false)}>취소</button>
            </div>
          </form> : noticeDetail ? <article className="home-notice-detail">
            <header>
              <h3><span className="home-notice-star"><Icon name="star" size={26} /></span>{noticeDetail.title}</h3>
              <dl>
                <div><dt>작성자 :</dt><dd>{noticeDetail.author}</dd></div>
                <div><dt>작성일 :</dt><dd>{noticeDetail.writtenAt}</dd></div>
                <div><dt>승인자 :</dt><dd>{noticeDetail.approver}</dd></div>
                <div><dt>조회수 :</dt><dd>{noticeDetail.views.toLocaleString('ko-KR')}</dd></div>
                <div><dt>게시형태 :</dt><dd>{noticeDetail.type === '긴급공지' ? '긴급' : '일반'}</dd></div>
              </dl>
            </header>
            <div className="home-notice-body">{noticeDetail.content}</div>
            <button type="button" className="home-notice-back" onClick={() => setNoticeDetail(null)}>목록</button>
          </article> : <>
            <div className="home-notice-table-head"><span>번호</span><span>제목</span><span>글쓴이</span><span>등록일</span></div>
            <ul className="home-notice-table">{notices.map(n => <li key={n.id}>
              <button type="button" className="home-notice-table-row" onClick={() => setNoticeDetail(n)}>
                <span>{n.id}</span>
                <span className="home-notice-table-title">{n.type === '긴급공지' && <b>[긴급] </b>}{n.title}</span>
                <span>{n.author}</span>
                <span>{n.date}</span>
              </button>
            </li>)}</ul>
            <div className="home-notice-actions"><button type="button" className="home-notice-back" onClick={openNoticeWrite}>작성하기</button></div>
          </>}
        </div>
      </div>}
    </section>


  
  <div className="home-lower-area">
    <div className="home-notify-row">
      <section className="home-panel" aria-label="업무 알림">
        <span className="home-panel-chip"><Icon name="bell" size={14} />업무 알림</span>
        <div className="home-bubble-list">
          <button type="button" className="home-bubble" onClick={() => onNavigate('resource:hold')}>
            <strong>보류자 검토 신청</strong>
            <span>{reviewCounts === null ? '검토함 서류를 확인하는 중입니다.' : `검토함에 ${reviewCounts}건의 서류가 대기 중입니다.`}</span>
          </button>
          {demoWorkAlerts.map(a => <button type="button" className="home-bubble" key={a.title} onClick={() => onNavigate(a.page)}><strong>{a.title}</strong><span>{a.body}</span></button>)}
        </div>
        {reviewError && <p className="home-data-note" role="alert">{reviewError}</p>}
        <span className="home-panel-more" aria-hidden="true"><Icon name="more" size={16} /></span>
      </section>
      <section className="home-panel" aria-label="연락 알림">
        <span className="home-panel-chip"><Icon name="inbox" size={14} />연락 알림</span>
        <div className="home-bubble-list">
          {contactAlerts.map(a => <button type="button" className="home-bubble" key={a.id} onClick={() => onOpenMessenger(a.id)}><strong>{a.title}</strong><span>{a.time}</span></button>)}
          {contactAlerts.length === 0 && <p className="home-data-note">새 메시지가 없습니다.</p>}
        </div>
        <button type="button" className="home-panel-more" aria-label="메신저 열기" onClick={() => onOpenMessenger()}><Icon name="more" size={16} /></button>
      </section>
    </div>

<nav className="home-shortcuts" aria-label="바로가기">
  {shortcuts.map(item => <button type="button" className="home-shortcut" key={item.label} onClick={() => item.onClick ? item.onClick() : onNavigate(item.page)}>
    <span className="home-shortcut-icon">
      {/[/:]/.test(item.icon)
        ? <img src={item.icon} alt="" />
        : <Icon name={item.icon as IconName} size={36} />}
    </span>
    <span className="home-shortcut-label">{item.label}</span>
  </button>)}
</nav>
</div>
    <CompositionPanel data={summary?.composition ?? null} error={summaryError} />
  </section>
}

type ForecastScenario = 'outflow_down' | 'baseline' | 'outflow_up'
type ForecastPayload = {
  scenarios: ForecastScenario[]
  years: number[]
  hist_cutoff: number
  regions: string[]
  data: Record<ForecastScenario, Record<string, Record<string, number | null>>>
}

const forecastYears = [2024, 2025, 2026, 2027, 2028]
const requiredFormationPopulation = 7 // Chart values are in units of 10,000 people.

type ForecastView = 'population' | 'attendance'
const forecastViewTabs: { id: ForecastView; label: string }[] = [
  { id: 'population', label: '정원 워치' },
  { id: 'attendance', label: '참석 예측' },
]

function HomeForecastSection() {
  const [view, setView] = useState<ForecastView>('population')
  return <section className="home-forecast" aria-label="예비군 예상 추이">
    <div className="forecast-view-toggle" role="tablist" aria-label="예측 화면 전환">
      {forecastViewTabs.map(tab =>
        <button key={tab.id} type="button" role="tab" aria-selected={view === tab.id}
          className={`forecast-view-tab ${view === tab.id ? 'is-active' : ''}`}
          onClick={() => setView(tab.id)}>{tab.label}</button>
      )}
    </div>
    {view === 'population' ? <PopulationForecast /> : <AttendanceForecast />}
  </section>
}

type AttendanceRound = { round: string; date: string; planned: number; final: number; attended: number; absent: number; rate: number }
type AttendancePayload = { rounds: AttendanceRound[]; history_sessions: number }

function AttendanceForecast() {
  const [payload, setPayload] = useState<AttendancePayload | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = () => fetch('/api/dashboard/attendance-forecast', { cache: 'no-store' })
      .then(async response => {
        if (!response.ok) throw new Error(`참석 예측 API 응답 오류 (${response.status})`)
        return response.json() as Promise<AttendancePayload>
      })
      .then(data => { if (!cancelled) setPayload(data) })
      .catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : '참석 예측 데이터를 불러오지 못했습니다.')
      })
    void Promise.resolve().then(() => { if (!cancelled) return load() })
    return () => { cancelled = true }
  }, [])

  if (error) return <div className="home-forecast-status"><strong>참석 예측 데이터를 불러오지 못했습니다.</strong><span>{error}</span></div>
  if (!payload) return <div className="home-forecast-status"><strong>참석 예측 데이터 로딩 중…</strong></div>

  const attendanceRounds = payload.rounds
  const values = attendanceRounds.map(round => round.attended)
  const dataMin = Math.min(...values)
  const dataMax = Math.max(...values)
  const margin = Math.max((dataMax - dataMin) * 0.6, dataMax * 0.12)
  const maxValue = dataMax + margin
  const minValue = Math.max(0, dataMin - margin)
  const W = 760, H = 208, pad = { l: 58, r: 42, t: 26, b: 34 }
  const x = (index: number) => pad.l + (W - pad.l - pad.r) * index / (attendanceRounds.length - 1)
  const y = (value: number) => pad.t + (H - pad.t - pad.b) * (1 - (value - minValue) / (maxValue - minValue))
  const path = attendanceRounds.map((round, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(round.attended)}`).join(' ')
  const totalFinal = attendanceRounds.reduce((sum, round) => sum + round.final, 0)
  const totalAttended = attendanceRounds.reduce((sum, round) => sum + round.attended, 0)

  return <>
    <div className="forecast-header">
      <div>
        <h2>예비군 참석 예측</h2>
        <p>회차별(1차~3차) 참석 예측 · 과거 세션 평균 참석률 기반 · 2026년</p>
      </div>
    </div>

    <div className="forecast-chart-wrap attendance-chart-wrap">
      <svg className="forecast-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="2026년 회차별 참석 예측 인원, 단위 명">
        <text x={pad.l} y={13} className="forecast-axis">단위: 명</text>
        {Array.from({ length: 5 }, (_, index) => {
          const value = minValue + (maxValue - minValue) * index / 4
          const yy = y(value)
          return <g key={index}>
            <line x1={pad.l} x2={W - pad.r} y1={yy} y2={yy} className="forecast-gridline" />
            <text x={pad.l - 10} y={yy + 4} className="forecast-axis" textAnchor="end">{Math.round(value)}</text>
          </g>
        })}
        <path d={path} className="forecast-line" />
        {attendanceRounds.map((round, index) => <g key={round.round}>
          <circle cx={x(index)} cy={y(round.attended)} r="5" className="forecast-point"><title>{round.round} {round.attended}명 (참석률 {(round.rate * 100).toFixed(1)}%)</title></circle>
          <text x={x(index)} y={y(round.attended) - 10} className="forecast-value" textAnchor="middle">{round.attended}</text>
          <text x={x(index)} y={y(round.attended) + 17} className="forecast-rate-label" textAnchor="middle">참석률 {(round.rate * 100).toFixed(1)}%</text>
          <text x={x(index)} y={H - 16} className="forecast-axis" textAnchor="middle">{round.round}</text>
          <text x={x(index)} y={H - 4} className="forecast-axis forecast-axis-sub" textAnchor="middle">{round.date.slice(5).replace('-', '/')}</text>
        </g>)}
      </svg>
    </div>

    <p className="forecast-note">올해 전체 총원 {totalFinal}명 중 {totalAttended}명 참석 예상. 훈련이 끝날 때마다 로그를 갱신해 정확도를 높이세요.</p>

    <details className="attendance-details">
      <summary>회차별 표로 보기</summary>
      <table className="attendance-table">
        <thead><tr><th>회차</th><th>훈련일</th><th>총원(최종대상)</th><th>참석</th><th>불참</th><th>참석률</th></tr></thead>
        <tbody>
          {attendanceRounds.map(round => <tr key={round.round}>
            <td>{round.round}</td><td>{round.date}</td><td>{round.final}</td>
            <td>{round.attended}</td><td>{round.absent}</td><td>{(round.rate * 100).toFixed(1)}%</td>
          </tr>)}
          <tr>
            <td><strong>합계</strong></td><td>-</td><td><strong>{totalFinal}</strong></td>
            <td><strong>{totalAttended}</strong></td><td><strong>{totalFinal - totalAttended}</strong></td>
            <td><strong>{(totalAttended / totalFinal * 100).toFixed(1)}%</strong></td>
          </tr>
        </tbody>
      </table>
    </details>
  </>
}

function PopulationForecast() {
  const [forecast, setForecast] = useState<ForecastPayload | null>(null)
  const [region, setRegion] = useState('전라남도')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = () => fetch('/api/dashboard/forecast', { cache: 'no-store' })
      .then(async response => {
        if (!response.ok) throw new Error(`예측 API 응답 오류 (${response.status})`)
        return response.json() as Promise<ForecastPayload>
      })
      .then(payload => {
        if (cancelled) return
        setForecast(payload)
        setRegion(payload.regions.includes('전라남도') ? '전라남도' : payload.regions[0])
      })
      .catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : '예측 데이터를 불러오지 못했습니다.')
      })
    void Promise.resolve().then(() => { if (!cancelled) return load() })
    return () => { cancelled = true }
  }, [])

  const series = useMemo(() => forecastYears.map(year => ({
    year,
    value: forecast?.data.baseline[region]?.[String(year)] ?? null,
  })), [forecast, region])

  if (error) return <div className="home-forecast-status"><strong>예측 데이터를 불러오지 못했습니다.</strong><span>{error}</span></div>
  if (!forecast) return <div className="home-forecast-status"><strong>예측 데이터 로딩 중…</strong></div>

  const thresholdResult = forecastThreshold(forecast.years, forecast.data.baseline[region] ?? {}, forecast.hist_cutoff, requiredFormationPopulation)
  const thresholdText = thresholdResult.status === 'breach'
    ? `${thresholdResult.year}년 병력 기준선 붕괴`
    : thresholdResult.status === 'safe'
      ? `${thresholdResult.year}년까지 유지`
      : '예측 자료 부족으로 판정 불가'

  const values = series.map(row => row.value).filter((value): value is number => value != null && Number.isFinite(value))
  const minimum = Math.min(requiredFormationPopulation, ...values)
  const maximum = Math.max(requiredFormationPopulation, ...values)
  const margin = Math.max((maximum - minimum) * 0.2, maximum * 0.01, 0.05)
  const minValue = Math.max(0, minimum - margin)
  const maxValue = maximum + margin
  const W = 760, H = 340, pad = { l: 58, r: 42, t: 38, b: 35 }
  const x = (index: number) => pad.l + (W - pad.l - pad.r) * index / (series.length - 1)
  const y = (value: number) => H - pad.b - (H - pad.t - pad.b) * (value - minValue) / (maxValue - minValue)
  // Start a new segment after missing data instead of inventing a connection.
  const path = series.map((row, index) => {
    if (row.value == null || !Number.isFinite(row.value)) return ''
    const previous = series[index - 1]?.value
    const command = previous == null || !Number.isFinite(previous) ? 'M' : 'L'
    return `${command} ${x(index)} ${y(row.value)}`
  }).join(' ')

  return <>
    <div className="forecast-header">
      <div>
        <h2>예비군 정원 워치</h2>
        <p>20~29세 남성 인구 기준 · 2024~2025년 실측 · 2026~2028년 예측</p>
      </div>
      <div className="forecast-controls">
        <label>지역<select value={region} onChange={e => setRegion(e.target.value)}>{forecast.regions.map(item => <option key={item}>{item}</option>)}</select></label>
      </div>
    </div>

    <div className="forecast-chart-wrap forecast-chart-with-status">
      <svg className="forecast-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${region} 2024~2028년 20~29세 남성 인구 추이, 단위 만명, 편제 필요인원 ${requiredFormationPopulation}만명`}>
        <text x={pad.l} y={16} className="forecast-axis">단위: 만명</text>
        {Array.from({ length: 6 }, (_, index) => {
          const value = minValue + (maxValue - minValue) * index / 5
          const yy = y(value)
          return <g key={index}><line x1={pad.l} x2={W - pad.r} y1={yy} y2={yy} className="forecast-gridline" /><text x={pad.l - 10} y={yy + 4} className="forecast-axis" textAnchor="end">{value.toFixed(2)}</text></g>
        })}
        {series.map((row, index) => <text key={row.year} x={x(index)} y={H - 10} className="forecast-axis" textAnchor="middle">{row.year}년</text>)}
        <path d={path} className="forecast-line" />
        <line x1={pad.l} x2={W - pad.r} y1={y(requiredFormationPopulation)} y2={y(requiredFormationPopulation)} className="forecast-required-line" />
        <text x={W - pad.r} y={y(requiredFormationPopulation) - 10} textAnchor="end" className="forecast-required-label">필요 병력 {requiredFormationPopulation}만명</text>
        {series.map((row, index) => row.value != null && Number.isFinite(row.value) ? <g key={row.year}>
          <circle cx={x(index)} cy={y(row.value)} r="5" className="forecast-point"><title>{row.year}년 {row.value.toFixed(2)}만명</title></circle>
          <text x={x(index)} y={y(row.value) - 14} className="forecast-value" textAnchor="middle">{row.value.toFixed(2)}</text>
        </g> : <text key={row.year} x={x(index)} y={H - pad.b - 12} className="forecast-axis" textAnchor="middle">자료 없음</text>)}
      </svg>
      <aside className={`forecast-threshold-status is-${thresholdResult.status}`} aria-live="polite">
        <strong>{thresholdText}</strong>
        <span>필요 병력 {requiredFormationPopulation}만명 기준</span>
      </aside>
    </div>
  </>
}
export default App

const dailyLabels = { departure: '출국자', arrival: '귀국자', transfer_in: '전입자', transfer_out: '전출자' }
type DailyPayload = { date: string; counts: Record<'hold' | 'delay', number> }

function koreaDate(offset = 0) {
  const date = new Date(Date.now() + 9 * 3600000)
  date.setUTCDate(date.getUTCDate() + offset)
  return date.toISOString().slice(0, 10)
}

function DailyPanel() {
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<(DailyPayload & { offset: number }) | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    const refresh = async () => {
      try {
        const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? '/api'}/dashboard/daily?day=${koreaDate(offset)}`, { signal: controller.signal, cache: 'no-store' })
        if (!response.ok) throw new Error('당일 현황을 불러오지 못했습니다.')
        const payload = await response.json() as DailyPayload
        if (!(['hold', 'delay'] as const).every(key => Number.isInteger(payload.counts?.[key as 'hold' | 'delay']))) throw new Error('당일 현황 응답 오류')
        if (!controller.signal.aborted) { setData({ ...payload, offset }); setError('') }
      } catch (reason) {
        if (!controller.signal.aborted) { setData(null); setError(reason instanceof Error ? reason.message : '조회 오류') }
      }
    }
    void Promise.resolve().then(() => { if (!controller.signal.aborted) return refresh() })
    return () => controller.abort()
  }, [offset])
  const current = data?.offset === offset ? data : null
  const demoMovements: Record<string, number> = { transfer_in: 0, transfer_out: 3, departure: 10, arrival: 4 }
  return <section className="home-today" aria-label="날짜별 인원 현황">
    <div className="home-today-header">
      <button type="button" aria-label="이전 날짜" onClick={() => setOffset(value => value - 1)}>‹</button>
      <strong>{offset === 0 ? 'Today' : koreaDate(offset)}</strong>
      <button type="button" aria-label="다음 날짜" onClick={() => setOffset(value => value + 1)}>›</button>
    </div>
    <div className="home-today-grid">{Object.entries(dailyLabels).map(([key, label]) => <div className="home-today-tile" key={key}><span>{label}</span><strong>{key in demoMovements ? (offset === 0 ? demoMovements[key] : '—') : current ? current.counts[key as 'hold' | 'delay'].toLocaleString('ko-KR') : '—'}</strong></div>)}</div>
    {error && <p role="alert" className="home-data-note">{error}</p>}

  </section>
}
