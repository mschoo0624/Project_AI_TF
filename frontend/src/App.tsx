import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import ReserveManagement from './features/reserve/ReserveManagement'
import ResourceManagement from './features/resource/ResourceManagement'
import WorkLogManagement from './features/worklog/WorkLogManagement'

const featurePages = [
  { id: 'reserve', label: '부대관리', Component: ReserveManagement },
  { id: 'resource', label: '자원관리', Component: ResourceManagement },
  { id: 'worklog', label: '업무일지', Component: WorkLogManagement },
] as const

type FeaturePageId = typeof featurePages[number]['id']
type PageId = 'home' | FeaturePageId
type HomeDestination = PageId | 'resource:hold' | 'resource:prosecution' | 'resource:travel'

type IconName = 'person' | 'bell' | 'calendar' | 'check' | 'warning' | 'plus' | 'minus' | 'list' | 'settings' | 'edit' | 'arrow' | 'left' | 'right' | 'inbox'

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
    }
  })()
  return <svg {...common}>{drawing}</svg>
}

// 아래 숫자와 일정은 첨부된 Figma 시안의 예시값이며 서버 데이터가 아닙니다.
// 추후 API 연결 시 이 객체를 API 응답으로 대체할 수 있습니다.
const demoDashboard = {
  metrics: [
    { label: '전체 대상자', count: 547, detail: '전체 예비군 대상자 수', icon: 'person' },
    { label: '보류자/연기자', count: 230, detail: '현재 보류자/연기자 수', icon: 'person' },
    { label: '고발대상자', count: 17, detail: '현재 고발대상자 수', icon: 'person' },
    { label: '금년도 대상자', count: 276, detail: '금년도 예비군 대상자 수', icon: 'calendar' },
    { label: '훈련 완료', count: 243, detail: '금년도 완료한 인원', icon: 'check' },
    { label: '미응소', count: 33, detail: '훈련 미참석 인원', icon: 'warning' },
  ] as const,
  alerts: [
    { label: '보류 대상자 처리', count: 8, page: 'resource:hold' },
    { label: '연기 대상자 처리', count: 10, page: 'resource:hold' },
    { label: '고발 대상자 처리', count: 17, page: 'resource:prosecution' },
    { label: '현재 출국자', count: 16, page: 'resource:travel' },
  ] as const,
  today: [
    { label: '전입자', count: 0 }, { label: '전출자', count: 3 },
    { label: '출국자', count: 10 }, { label: '귀국자', count: 4 },
    { label: '보류자', count: 7 }, { label: '연기자', count: 1 },
  ] as const,
  categories: [
    { label: '보병', count: 198 }, { label: '포병', count: 87 },
    { label: '기갑', count: 62 }, { label: '공병', count: 55 },
    { label: '통신', count: 48 }, { label: '병참', count: 42 },
    { label: '수송', count: 31 }, { label: '의무', count: 24 },
  ] as const,
}

type Schedule = { id: number; date: string; title: string }
const initialSchedules: Schedule[] = [
  { id: 1, date: '01/14', title: '동원훈련 1형 예정' },
  { id: 2, date: '01/15', title: '월 중간 결산' },
]

function App() {
  const [activePage, setActivePage] = useState<PageId>('home')
  const [resourceLanding, setResourceLanding] = useState<'roster' | 'organization' | 'hold' | 'prosecution' | 'travel'>('organization')
  const navigate = (destination: HomeDestination) => {
    if (destination === 'resource:hold' || destination === 'resource:prosecution' || destination === 'resource:travel') {
      setResourceLanding(destination === 'resource:hold' ? 'hold' : destination === 'resource:prosecution' ? 'prosecution' : 'travel')
      setActivePage('resource')
    } else {
      setResourceLanding('organization')
      setActivePage(destination)
    }
  }
  const activeFeature = featurePages.find(page => page.id === activePage)
  const ActiveComponent = activeFeature?.Component

  return <div className="app">
    <header className="system-topbar">
      <div className="system-brand">예비군 업무체계</div>
      <div className="account-area" />
    </header>
    <div className="system-body">
      <aside className="sidebar" aria-label="주 메뉴">
        <button className={`user-icon ${activePage === 'home' ? 'active' : ''}`} type="button" onClick={() => navigate('home')} aria-label="홈으로 이동" title="홈으로 이동">
          <span className="user-icon-figure"><Icon name="person" size={28} /></span>
        </button>
        {featurePages.map(page =>
          <button key={page.id} type="button" className={`side-button ${activePage === page.id ? 'active' : ''}`} onClick={() => navigate(page.id)}>
            {page.label}
          </button>
        )}
      </aside>
      <main className="workspace">
        <div className="workspace-content">
          {activePage === 'home'
            ? <Home onNavigate={navigate} />
            : activePage === 'resource' ? <ResourceManagement initialTab={resourceLanding} key={`resource-${resourceLanding}`} />
            : ActiveComponent ? <ActiveComponent key={activePage} /> : null}
        </div>
      </main>
    </div>
  </div>
}

function Home({ onNavigate }: { onNavigate: (page: HomeDestination) => void }) {
  const [schedules, setSchedules] = useState<Schedule[]>(initialSchedules)
  const [selectedSchedule, setSelectedSchedule] = useState<number | null>(null)
  const [editingSchedule, setEditingSchedule] = useState<number | 'new' | null>(null)
  const [draftDate, setDraftDate] = useState('')
  const [draftTitle, setDraftTitle] = useState('')
  const [showScheduleList, setShowScheduleList] = useState(true)
  const [showScheduleInfo, setShowScheduleInfo] = useState(false)
  const [dayOffset, setDayOffset] = useState(0)

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
  const dayLabel = (() => {
    if (dayOffset === 0) return 'Today'
    const date = new Date()
    date.setDate(date.getDate() + dayOffset)
    return `${date.getMonth() + 1}월 ${date.getDate()}일`
  })()

  return <section className="home-dashboard" aria-label="홈 대시보드">
    <div className="home-left-column">
      <section className="home-user-card" aria-label="사용자 정보">
        <strong>담당자</strong>
        <span>소속 정보 미연결</span>
        <small>화면 예시 · 실데이터 미연결</small>
      </section>

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

      <section className="home-today" aria-label="당일 현황">
        <div className="home-today-header">
          <button type="button" aria-label="이전 날짜" onClick={() => setDayOffset(day => day - 1)}><Icon name="left" size={17} /></button>
          <strong>{dayLabel}</strong>
          <button type="button" aria-label="다음 날짜" onClick={() => setDayOffset(day => day + 1)}><Icon name="right" size={17} /></button>
        </div>
        <div className="home-today-grid">
          {demoDashboard.today.map(entry =>
            <div className="home-today-tile" key={entry.label}>
              <span>{entry.label}</span><strong>{dayOffset === 0 ? entry.count : '—'}</strong>
            </div>
          )}
        </div>
      </section>
    </div>

    <section className="home-metrics-area" aria-label="대상자 통계 예시">
      <div className="home-metrics-grid">
        {demoDashboard.metrics.map(metric =>
          <article className="home-metric-card" key={metric.label}>
            <div className="home-metric-label">
              <span className={`home-metric-icon icon-${metric.icon}`}><Icon name={metric.icon} size={19} /></span>
              <strong>{metric.label}</strong>
            </div>
            <p className="home-metric-number">{metric.count.toLocaleString('ko-KR')}명</p>
            <p className="home-metric-detail">{metric.detail}</p>
          </article>
        )}
      </div>
    </section>

    <section className="home-alerts-card" aria-label="알림 예시">
      <h2><span className="home-alert-icon"><Icon name="bell" size={19} /></span>알림</h2>
      <div className="home-alert-list">
        {demoDashboard.alerts.map(alert =>
          <div className="home-alert-row" key={alert.label}>
            <span className="home-alert-text"><span className="home-dot" />{alert.label}</span>
            <span className="home-alert-count">{alert.count}명</span>
            <button type="button" className="home-alert-link" title={`${alert.page === 'resource:hold' ? '자원관리 · 보류자/연기자 검토' : alert.page === 'resource:prosecution' ? '자원관리 · 고발대상자' : '자원관리 · 출국자/귀국자'} 화면 열기`} aria-label={`${alert.label}: 관리 화면 열기`} onClick={() => onNavigate(alert.page)}><Icon name="arrow" size={19} /></button>
          </div>
        )}
      </div>
    </section>

    <HomeForecast />

    <section className="home-composition" aria-label="대상자 구성 예시">
      <h2>대상자 구성</h2>
      <div className="home-composition-head">
        <div className="home-composition-tile"><span>간부</span><strong>120 <small>명</small></strong></div>
        <div className="home-composition-tile"><span>일반 병사</span><strong>427 <small>명</small></strong></div>
      </div>
      <h3>일반 병사 연차별</h3>
      <div className="home-service-bar" aria-label="1~4년차 215명, 5~6년차 138명, 7~8년차 74명">
        <span style={{ flex: 215, backgroundColor: '#2162e5' }} />
        <span style={{ flex: 138, backgroundColor: '#619eef' }} />
        <span style={{ flex: 74, backgroundColor: '#b8d5fc' }} />
      </div>
      <div className="home-service-legend"><span><i style={{ backgroundColor: '#2162e5' }} />1~4년차 215명</span><span><i style={{ backgroundColor: '#619eef' }} />5~6년차 138명</span><span><i style={{ backgroundColor: '#b8d5fc' }} />7~8년차 74명</span></div>
      <div className="home-composition-divider" />
      <h3>병과별 인원</h3>
      <div className="home-category-list">
        {demoDashboard.categories.map(category =>
          <div className="home-category-row" key={category.label}>
            <span>{category.label}</span>
            <div className="home-category-track"><i style={{ width: `${category.count / 198 * 100}%` }} /></div>
            <strong>{category.count}명</strong>
          </div>
        )}
      </div>
    </section>
  </section>
}

// 추후 API 차트 컴포넌트로 바꿀 때 이 컴포넌트만 교체하면 됩니다.
function HomeForecast() {
  return <section className="home-forecast" aria-label="예비군 예상 추이 시안 이미지">
    <img src="/home-forecast-sample.png" alt="예비군 예상 추이 시안: 2024년부터 2030년까지의 계획 인원과 실제 편성 예시 선 그래프. 실제 예측 자료가 아닙니다." />
  </section>
}

export default App
