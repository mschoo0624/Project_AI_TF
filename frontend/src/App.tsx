import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import ResourceManagement from './features/resource/ResourceManagement'
import WorkLogManagement from './features/worklog/WorkLogManagement'
import { countReviewDocuments, fetchBootstrap } from './features/review/api'

const featurePages = [
  { id: 'reserve', label: '부대관리', Component: EmptyReservePage },
  { id: 'resource', label: '자원관리', Component: ResourceManagement },
  { id: 'worklog', label: '업무일지', Component: WorkLogManagement },
] as const

function EmptyReservePage() {
  return <section className="empty-reserve-page" aria-label="부대관리" />
}

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
  alerts: [
    { label: '보류/연기 대상자 처리', reviewKey: 'pending', page: 'resource:hold' },
    { label: '고발 대상자 처리', count: 17, page: 'resource:prosecution' },
    { label: '현재 출국자', count: 16, page: 'resource:travel' },
  ] as const,


}

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

function App() {
  const [homeRevision, setHomeRevision] = useState(0)
  const [activePage, setActivePage] = useState<PageId>('home')
  const [resourceLanding, setResourceLanding] = useState<'roster' | 'hold' | 'prosecution' | 'travel'>('roster')
  const navigate = (destination: HomeDestination) => {
    if (destination === 'home') setHomeRevision(value => value + 1)
    if (destination === 'resource:hold' || destination === 'resource:prosecution' || destination === 'resource:travel') {
      setResourceLanding(destination === 'resource:hold' ? 'hold' : destination === 'resource:prosecution' ? 'prosecution' : 'travel')
      setActivePage('resource')
    } else {
      setResourceLanding('roster')
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
            ? <Home key={homeRevision} onNavigate={navigate} />
            : activePage === 'resource' ? <ResourceManagement initialTab={resourceLanding} key="resource" />
            : ActiveComponent ? <ActiveComponent key={activePage} /> : null}
        </div>
      </main>
    </div>
  </div>
}

function Home({ onNavigate }: { onNavigate: (page: HomeDestination) => void }) {
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

      <DailyPanel />
    </div>

    <section className="home-metrics-area" aria-label="DB 대상자 통계" aria-busy={!summary && !summaryError}>
      {summaryError && <p className="home-metrics-error" role="alert">{summaryError}</p>}
      <div className="home-metrics-grid">
        {demoDashboard.metrics.map(metric =>
          <article className="home-metric-card" key={metric.label}>
            <div className="home-metric-label">
              <span className={`home-metric-icon icon-${metric.icon}`}><Icon name={metric.icon} size={19} /></span>
              <strong>{metric.label}</strong>
            </div>
            <p className="home-metric-number">{summary ? `${summary[metric.key].toLocaleString('ko-KR')}명` : '—'}</p>
            <p className="home-metric-detail">{metric.detail}</p>
          </article>
        )}
      </div>
    </section>

    <section className="home-alerts-card" aria-label="알림">
      <h2><span className="home-alert-icon"><Icon name="bell" size={19} /></span>알림</h2>
      <div className="home-alert-list">
        {demoDashboard.alerts.map(alert =>
          <div className="home-alert-row" key={alert.label}>
            <span className="home-alert-text"><span className="home-dot" />{alert.label}</span>
            <span className="home-alert-count">{'reviewKey' in alert ? reviewCounts !== null ? `${reviewCounts}건` : '—' : `${alert.count}명`}</span>
            <button type="button" className="home-alert-link" title={`${alert.page === 'resource:hold' ? '자원관리 · 보류자/연기자 검토' : alert.page === 'resource:prosecution' ? '자원관리 · 고발대상자' : '자원관리 · 출국자/귀국자'} 화면 열기`} aria-label={`${alert.label}: 관리 화면 열기`} onClick={() => onNavigate(alert.page)}><Icon name="arrow" size={19} /></button>
          </div>
        )}
      </div>
      {reviewError && <p className="home-data-note" role="alert">{reviewError}</p>}
    </section>

    <HomeForecast />

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

function HomeForecast() {
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

  if (error) return <section className="home-forecast home-forecast-status" aria-label="예비군 예상 추이"><strong>예측 데이터를 불러오지 못했습니다.</strong><span>{error}</span></section>
  if (!forecast) return <section className="home-forecast home-forecast-status" aria-label="예비군 예상 추이"><strong>예측 데이터 로딩 중…</strong></section>

  const values = series.map(row => row.value).filter((value): value is number => value != null && Number.isFinite(value))
  const minimum = values.length ? Math.min(...values) : 0
  const maximum = values.length ? Math.max(...values) : 1
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

  return <section className="home-forecast" aria-label="예비군 예상 추이">
    <div className="forecast-header">
      <div>
        <h2>예비군 정원 워치</h2>
        <p>20~29세 남성 인구 기준 · 2024~2025년 실측 · 2026~2028년 예측</p>
      </div>
      <div className="forecast-controls">
        <label>지역<select value={region} onChange={e => setRegion(e.target.value)}>{forecast.regions.map(item => <option key={item}>{item}</option>)}</select></label>
      </div>
    </div>

    <div className="forecast-chart-wrap">
      <svg className="forecast-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${region} 2024~2028년 20~29세 남성 인구 추이, 단위 만명`}>
        <text x={pad.l} y={16} className="forecast-axis">단위: 만명</text>
        {Array.from({ length: 6 }, (_, index) => {
          const value = minValue + (maxValue - minValue) * index / 5
          const yy = y(value)
          return <g key={index}><line x1={pad.l} x2={W - pad.r} y1={yy} y2={yy} className="forecast-gridline" /><text x={pad.l - 10} y={yy + 4} className="forecast-axis" textAnchor="end">{value.toFixed(2)}</text></g>
        })}
        {series.map((row, index) => <text key={row.year} x={x(index)} y={H - 10} className="forecast-axis" textAnchor="middle">{row.year}년</text>)}
        <path d={path} className="forecast-line" />
        {series.map((row, index) => row.value != null && Number.isFinite(row.value) ? <g key={row.year}>
          <circle cx={x(index)} cy={y(row.value)} r="5" className="forecast-point"><title>{row.year}년 {row.value.toFixed(2)}만명</title></circle>
          <text x={x(index)} y={y(row.value) - 14} className="forecast-value" textAnchor="middle">{row.value.toFixed(2)}</text>
        </g> : <text key={row.year} x={x(index)} y={H - pad.b - 12} className="forecast-axis" textAnchor="middle">자료 없음</text>)}
      </svg>
    </div>
  </section>
}
export default App

const movementLabels = { transfer_in: '전입자', transfer_out: '전출자', departure: '출국자', arrival: '귀국자' }
const dailyLabels = { ...movementLabels, hold: '보류자', delay: '연기자' }
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
