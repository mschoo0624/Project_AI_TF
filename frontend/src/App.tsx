<<<<<<< HEAD
import { useState } from 'react'
import type { FormEvent } from 'react'
=======
import { useEffect, useState } from 'react'
import type { Dispatch, FormEvent, SetStateAction } from 'react'
>>>>>>> main
import './App.css'
import ReserveManagement from './features/reserve/ReserveManagement'
import ResourceManagement from './features/resource/ResourceManagement'
import WorkLogManagement from './features/worklog/WorkLogManagement'

<<<<<<< HEAD
const featurePages = [
  { id: 'reserve', label: '부대관리', Component: ReserveManagement },
  { id: 'resource', label: '자원관리', Component: ResourceManagement },
  { id: 'worklog', label: '업무일지', Component: WorkLogManagement },
] as const
=======
type TabId = 'home' | 'reserve' | 'resource' | 'classifier'
type ResourcePage = 'lookup' | 'assignment'
type DetailTab = 'profile' | 'progress' | 'records'
>>>>>>> main

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

<<<<<<< HEAD
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
  const [resourceLanding, setResourceLanding] = useState<'roster' | 'hold' | 'prosecution' | 'travel'>('roster')
  const navigate = (destination: HomeDestination) => {
    if (destination === 'resource:hold' || destination === 'resource:prosecution' || destination === 'resource:travel') {
      setResourceLanding(destination === 'resource:hold' ? 'hold' : destination === 'resource:prosecution' ? 'prosecution' : 'travel')
      setActivePage('resource')
    } else {
      setResourceLanding('roster')
      setActivePage(destination)
    }
=======
type TrainingPlanItem = { name: string; hours: number }
type TrainingProgress = {
  service_year: number
  mobilization_status: string | null
  personnel_category: string
  training_plan: TrainingPlanItem[]
  target_hours: number
  carryover_hours?: number
  required_hours?: number
  completed_hours: number
  remaining_hours: number
  prosecution_risk: boolean
  completed: boolean
}
type TrainingRecord = {
  id: number
  education_year: number
  training_year: number | null
  training_type: string
  training_round: number
  attendance_status: string
  training_hours: number
  notes: string | null
}
type TrainingRecordForm = {
  service_year: number
  training_year: number
  training_type: string
  training_round: number
  attendance_status: string
  training_hours: number
  notes: string
}
type CreatePersonForm = {
  military_number: string
  name: string
  branch: string
  rank: string
  unit: string
  specialty: string
  origin_type: string
  service_year: number
  position: string
  mobilization_status: string
  status: string
  previous_training_hours: string
}
type Squad = {
  id: number
  name: string
  description: string | null
  person_count: number
  breakdown?: Record<string, number>
  roster?: SquadMember[]
}
type SquadMember = {
  military_number: string
  name: string
  branch: string
  category: string
  position: string | null
  specialty: string | null
  service_year: number | null
}
type AssignmentRecommendation = {
  squad_id: number
  squad_name: string
  current_count: number
  same_position_count: number
  same_tier_count: number
  reason: string
}
type AssignmentResult = {
  squad_id: number
  positions: Record<string, { requested: number; assigned: { military_number: string; name: string }[]; shortfall: number }>
  total_requested: number
  total_assigned: number
  total_shortfall: number
}
type AssignmentQuotas = Record<string, Record<string, Record<string, number>>>
type AssignmentCandidate = {
  military_number: string
  name: string
  position: string
  specialty: string | null
  service_year: number | null
  origin_type?: string | null
  personnel_category?: string
  tier: string
  branch: string
  category: string
}
type AssignmentCandidates = Record<string, Record<string, AssignmentCandidate[]>>
type ProposedAssignment = AssignmentCandidate & { squad_id: number }
type ClassifierExtraction = { name?: string; valid_until?: string; document_type?: string; stamp_present?: boolean; confidence?: number; anomaly_flags?: string[]; error?: string }
type ClassifierSubmission = { id: string; filename: string; saved_path: string; military_number: string | null; extraction: ClassifierExtraction; reason_category: string | null; status: 'pending' | 'approved' | 'declined'; note: string | null; created_at: string; decided_at: string | null; projectPostponementId?: number }
type ProjectPostponement = { id: number; person_id: string; status: string; category: string | null; classifier_submission_id: string | null }

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const branches = ['육군', '해군', '공군', '해병대']
const statuses = ['active', 'on_leave']
const mobilizationStatuses = ['동원지정', '동원미지정', '학생예비군', '일부보류', '해당없음']
const trainingTypes = ['기본훈련', '동원훈련Ⅰ형', '동원훈련Ⅱ형', '작계훈련(전·후반기)']
const assignmentPositions = ['행정병', '통신병', '의무병', '운전병', '보급병']
const personnelCategories = ['병사', '부사관', '장교']
const assignmentBranches = ['육군', '해군', '해병대', '공군']
const originTypeOptions = ['병사', '부사관', '장교']
const rankCategoryMap: Record<string, string[]> = {
  병사: ['이병', '일병', '상병', '병장'],
  부사관: ['하사', '중사', '상사'],
  장교: ['소위', '중위', '대위'],
}
const positionOptions = ['행정병', '병기취급병', '통신병', '의무병', '운전병', '보급병', '소총수', '보충']

const initialCreatePersonForm: CreatePersonForm = {
  military_number: '', name: '', branch: '육군', rank: '병장', unit: '', specialty: '',
  origin_type: '병사', service_year: 1, position: '소총수',
  mobilization_status: '동원지정', status: 'active', previous_training_hours: '',
}

function suggestPositionForSpecialty(specialty: string): string | null {
  const normalized = specialty.trim()
  if (!normalized) return null
  const compact = normalized.replace(/\s+/g, '').toLowerCase()
  const code = normalized.replace(/\D/g, '')
  const mapping: Record<string, string> = {
    행정: '행정병', 행정병: '행정병', '3111101': '행정병', '311102': '행정병',
    병기: '병기취급병', 병기취급: '병기취급병', 병기취급병: '병기취급병', '222101': '병기취급병', '222102': '병기취급병',
    통신: '통신병', 통신병: '통신병', '171101': '통신병', '171102': '통신병', '171104': '통신병', '171106': '통신병',
    의무: '의무병', 의무병: '의무병', '411101': '의무병', '411102': '의무병', '411103': '의무병', '411104': '의무병', '411105': '의무병', '411106': '의무병',
    운전: '운전병', 운전병: '운전병', '241102': '운전병', '241103': '운전병', '241104': '운전병', '231101': '운전병',
    보급: '보급병', 보급병: '보급병', '231103': '보급병', '231104': '보급병', '231105': '보급병',
  }
  return mapping[normalized] ?? mapping[compact] ?? mapping[code] ?? null
}

async function responseError(response: Response, fallback: string) {
  try {
    const data = await response.json() as { detail?: string | { loc?: (string | number)[]; msg?: string }[] }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map(item => item.msg ?? '입력값을 확인해 주세요.').join(' ')
    return fallback
  } catch { return fallback }
}

function App() {
  const [openTabs, setOpenTabs] = useState<TabId[]>(['home', 'resource', 'classifier'])
  const [activeTab, setActiveTab] = useState<TabId>('classifier')

  const openReserve = () => {
    setOpenTabs(t => t.includes('reserve') ? t : [...t, 'reserve'])
    setActiveTab('reserve')
  }
  const openResource = () => {
    setOpenTabs(t => t.includes('resource') ? t : [...t, 'resource'])
    setActiveTab('resource')
  }
  const openClassifier = () => {
    setOpenTabs(t => t.includes('classifier') ? t : [...t, 'classifier'])
    setActiveTab('classifier')
  }
  const closeTab = (tab: Exclude<TabId, 'home'>) => {
    setOpenTabs(t => t.filter(item => item !== tab))
    if (activeTab === tab) setActiveTab('home')
>>>>>>> main
  }
  const activeFeature = featurePages.find(page => page.id === activePage)
  const ActiveComponent = activeFeature?.Component

  return <div className="app">
    <header className="system-topbar">
      <div className="system-brand">예비군 업무체계</div>
      <div className="account-area" />
    </header>
    <div className="system-body">
<<<<<<< HEAD
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
            : activePage === 'resource' ? <ResourceManagement initialTab={resourceLanding} key="resource" />
            : ActiveComponent ? <ActiveComponent key={activePage} /> : null}
        </div>
=======
      <aside className="sidebar">
        <div className="user-icon">♙</div>
        <button className={`side-button ${activeTab === 'reserve' ? 'active' : ''}`} onClick={openReserve}>예비군관리</button>
        <button className={`side-button ${activeTab === 'resource' ? 'active' : ''}`} onClick={openResource}>자원관리</button>
        <button className={`side-button ${activeTab === 'classifier' ? 'active' : ''}`} onClick={openClassifier}>연기판정</button>
      </aside>
      <main className="workspace">
        <div className="workspace-tabs">
          <button className={`workspace-tab ${activeTab === 'home' ? 'selected' : ''}`} onClick={() => setActiveTab('home')}>홈</button>
          {openTabs.includes('reserve') && <div className={`workspace-tab compound ${activeTab === 'reserve' ? 'selected' : ''}`}>
            <button className="tab-main" onClick={() => setActiveTab('reserve')}>예비군관리</button>
            <button className="tab-close" onClick={() => closeTab('reserve')} aria-label="예비군관리 탭 닫기">×</button>
          </div>}
          {openTabs.includes('resource') && <div className={`workspace-tab compound ${activeTab === 'resource' ? 'selected' : ''}`}>
            <button className="tab-main" onClick={() => setActiveTab('resource')}>자원관리</button>
            <button className="tab-close" onClick={() => closeTab('resource')} aria-label="자원관리 탭 닫기">×</button>
          </div>}
          {openTabs.includes('classifier') && <div className={`workspace-tab compound ${activeTab === 'classifier' ? 'selected' : ''}`}>
            <button className="tab-main" onClick={() => setActiveTab('classifier')}>연기판정</button>
            <button className="tab-close" onClick={() => closeTab('classifier')} aria-label="연기판정 탭 닫기">×</button>
          </div>}
        </div>
        {activeTab === 'home' ? <Home onOpen={openResource} /> : activeTab === 'reserve' ? <div /> : activeTab === 'classifier' ? <PostponementModule /> : <ResourceModule />}
>>>>>>> main
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

<<<<<<< HEAD
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
=======
function PostponementModule() {
  const [file, setFile] = useState<File | null>(null)
  const [militaryNumber, setMilitaryNumber] = useState('')
  const [matchedPerson, setMatchedPerson] = useState<Person | null>(null)
  const [matching, setMatching] = useState(false)
  const [personNames, setPersonNames] = useState<Record<string, string>>({})
  const [submissions, setSubmissions] = useState<ClassifierSubmission[]>([])
  const [selected, setSelected] = useState<ClassifierSubmission | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingList, setLoadingList] = useState(true)
  const [error, setError] = useState('')

  const loadSubmissions = async () => {
    setLoadingList(true)
    try {
      const response = await fetch('/classifier-api/submissions')
      if (!response.ok) throw new Error(await responseError(response, '분류기 제출 목록을 불러오지 못했습니다.'))
      const loaded = await response.json() as ClassifierSubmission[]
      const projectResponse = await fetch(`${API_BASE}/postponements`)
      const projectItems = projectResponse.ok ? await projectResponse.json() as ProjectPostponement[] : []
      const linked = loaded.map(item => ({ ...item, projectPostponementId: projectItems.find(project => project.classifier_submission_id === item.id)?.id }))
      setSubmissions(linked)
      const matches = await Promise.all(loaded.filter(item => item.military_number).map(async item => {
        const response = await fetch(`${API_BASE}/persons/${encodeURIComponent(item.military_number!)}`)
        return response.ok ? [item.military_number!, (await response.json() as Person).name] as const : null
      }))
      setPersonNames(Object.fromEntries(matches.filter((match): match is readonly [string, string] => match !== null)))
    } catch (e) { setError(e instanceof Error ? e.message : '분류기 제출 목록을 불러오지 못했습니다.') }
    finally { setLoadingList(false) }
  }

  useEffect(() => { void loadSubmissions() }, [])

  const findPerson = async (value: string) => {
    setMilitaryNumber(value); setMatchedPerson(null)
    if (!value.trim()) return
    setMatching(true); setError('')
    try {
      const response = await fetch(`${API_BASE}/persons/${encodeURIComponent(value.trim())}`)
      if (response.ok) setMatchedPerson(await response.json() as Person)
    } catch { setError('군번 확인에 실패했습니다.') }
    finally { setMatching(false) }
  }

  const chooseFile = (candidate: File | undefined) => {
    if (!candidate) return
    if (!candidate.name.toLowerCase().endsWith('.pdf')) {
      setFile(null); setError('PDF 파일만 업로드할 수 있습니다.'); return
    }
    setError(''); setFile(candidate)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!file || !matchedPerson || matching) { setError('유효한 PDF와 등록된 군번을 먼저 입력해 주세요.'); return }
    setLoading(true); setError('')
    try {
      const form = new FormData(); form.append('file', file)
      if (militaryNumber.trim()) form.append('military_number', militaryNumber.trim())
      const response = await fetch('/classifier-api/submissions', { method: 'POST', body: form })
      if (!response.ok) throw new Error(await responseError(response, 'PDF 분석에 실패했습니다.'))
      const submission = await response.json() as ClassifierSubmission
      const projectResponse = await fetch(`${API_BASE}/postponements`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ person_id: matchedPerson.military_number, reason: submission.reason_category ?? submission.extraction.document_type ?? '서류 제출', category: submission.reason_category, training_year: matchedPerson.service_year, source_file: submission.filename, classifier_submission_id: submission.id }) })
      if (!projectResponse.ok) throw new Error(await responseError(projectResponse, 'Project backend 연기 기록 연결에 실패했습니다.'))
      const projectItem = await projectResponse.json() as ProjectPostponement
      const linkedSubmission = { ...submission, projectPostponementId: projectItem.id }
      setSubmissions(items => [linkedSubmission, ...items]); setPersonNames(names => ({ ...names, [matchedPerson.military_number]: matchedPerson.name })); setSelected(linkedSubmission); setFile(null)
    } catch (e) { setError(e instanceof Error ? e.message : 'PDF 분석에 실패했습니다.') }
    finally { setLoading(false) }
  }

  const decide = async (submission: ClassifierSubmission, decision: 'approved' | 'declined') => {
    setError('')
    try {
      if (!submission.projectPostponementId) throw new Error('Project backend에 연결된 연기 기록이 없습니다.')
      const action = decision === 'approved' ? 'approve' : 'reject'
      const response = await fetch(`${API_BASE}/postponements/${submission.projectPostponementId}/${action}`, { method: 'PATCH' })
      if (!response.ok) throw new Error(await responseError(response, '제출 건 처리에 실패했습니다.'))
      await response.json()
      const nextStatus: ClassifierSubmission['status'] = decision === 'approved' ? 'approved' : 'declined'
      const updated = { ...submission, status: nextStatus }
      setSubmissions(items => items.map(item => item.id === submission.id ? updated : item)); setSelected(updated)
    } catch (e) { setError(e instanceof Error ? e.message : '제출 건 처리에 실패했습니다.') }
  }

  return <section className="classifier-module">
    <div className="page-intro"><div><p className="eyebrow">CLASSIFIER_AITF API TEST</p><h2>서류 AI 판정</h2><p>PDF를 업로드하고 군번을 연결해 추출·분류·검토 결과를 확인합니다.</p></div><button className="button secondary" onClick={() => void loadSubmissions()}>목록 새로고침</button></div>
    <form className="classifier-form" onSubmit={submit}>
      <label>군번<span className="field-hint">등록된 예비군만 업로드할 수 있습니다.</span><input value={militaryNumber} onChange={e => void findPerson(e.target.value)} placeholder="예: 26-72000500" /></label>
      <label>PDF 파일<span className="field-hint">PDF 형식만 가능</span><input type="file" accept="application/pdf,.pdf" onChange={e => chooseFile(e.target.files?.[0])} /></label>
      <div className={`classifier-match wide ${matchedPerson ? 'matched' : militaryNumber && !matching ? 'unmatched' : ''}`}>{matching ? <span>군번을 확인하는 중입니다...</span> : matchedPerson ? <><strong>매칭됨: {matchedPerson.name}</strong><span>{matchedPerson.military_number} · {matchedPerson.branch} · {matchedPerson.status}</span></> : militaryNumber ? <span>등록된 예비군을 찾지 못했습니다. 군번을 확인해 주세요.</span> : <span>군번을 입력하면 등록된 예비군과 매칭합니다.</span>}</div>
      {file && <div className="selected-file wide"><span className="file-icon">PDF</span><div><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(2)} MB · 업로드 준비 완료</small></div><button type="button" className="file-remove" onClick={() => setFile(null)} aria-label="선택한 PDF 제거">×</button></div>}
      <div className="form-actions wide"><button className="button primary" disabled={!file || !matchedPerson || matching || loading}>{loading ? 'AI 분석 중...' : 'PDF 업로드 및 분석'}</button></div>
    </form>
    {error && <div className="inline-error">{error}</div>}
    <div className="classifier-layout">
      <section className="list-card"><div className="list-caption"><h3>제출 목록</h3><span>{submissions.filter(item => item.status === 'pending').length}건 검토대기</span></div>{loadingList ? <State>제출 목록을 불러오는 중입니다...</State> : submissions.length === 0 ? <State>아직 업로드된 PDF가 없습니다.</State> : <div className="classifier-submission-list">{submissions.map(item => <button key={item.id} className={`classifier-submission ${selected?.id === item.id ? 'selected' : ''}`} onClick={() => setSelected(item)}><strong>{personNames[item.military_number ?? ''] ?? item.extraction.name ?? '이름 미확인'}</strong><span>{item.military_number ?? '군번 미기재'} · {item.filename}</span><em className={`submission-status ${item.status}`}>{item.status === 'pending' ? '검토대기' : item.status === 'approved' ? '승인' : '반려'}</em></button>)}</div>}</section>
      <ClassifierResult submission={selected} onDecision={decide} />
    </div>
  </section>
}

function ClassifierResult({ submission, onDecision }: { submission: ClassifierSubmission | null; onDecision: (submission: ClassifierSubmission, decision: 'approved' | 'declined') => void }) {
  if (!submission) return <section className="classifier-result state-panel">목록에서 제출 건을 선택하세요.</section>
  const extraction = submission.extraction
  const originalPdfUrl = `/classifier-api${submission.saved_path}`
  return <section className="classifier-result"><div className="section-heading"><h3>AI 분석 결과</h3><span className={`submission-status ${submission.status}`}>{submission.status === 'pending' ? '검토대기' : submission.status === 'approved' ? '승인' : '반려'}</span></div><div className="original-pdf-panel"><div className="original-pdf-heading"><div><strong>원본 PDF</strong><span>{submission.filename}</span></div><a className="button small secondary" href={originalPdfUrl} target="_blank" rel="noreferrer">새 탭에서 열기 ↗</a></div><iframe className="original-pdf-viewer" title={`${submission.filename} 원본 PDF`} src={originalPdfUrl} /></div><div className="classifier-facts"><Fact label="성명" value={extraction.name ?? '-'} /><Fact label="서류종류" value={extraction.document_type ?? '-'} /><Fact label="유효기간" value={extraction.valid_until ?? '-'} /><Fact label="사유 분류" value={submission.reason_category ?? '모델 미학습'} /><Fact label="신뢰도" value={extraction.confidence != null ? `${Math.round(extraction.confidence * 100)}%` : '-'} /><Fact label="도장/서명" value={extraction.stamp_present ? '있음' : '없음'} /></div>{extraction.anomaly_flags?.length ? <div className="classifier-alerts"><strong>이상 신호</strong>{extraction.anomaly_flags.map(flag => <span key={flag}>! {flag}</span>)}</div> : <p className="classifier-ok">문서 이상 신호가 없습니다.</p>}<p className="classifier-file">원본: {submission.filename}</p>{submission.status === 'pending' && (submission.projectPostponementId ? <div className="review-actions"><button className="button primary" onClick={() => onDecision(submission, 'approved')}>승인</button><button className="button danger-outline" onClick={() => onDecision(submission, 'declined')}>반려</button></div> : <p className="classifier-unlinked">기존 제출 건입니다. Project 연기 기록과 연결되지 않아 새 업로드부터 통합 결재를 사용할 수 있습니다.</p>)}</section>
}

function Fact({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div> }

function ResourceModule() {
  const [page, setPage] = useState<ResourcePage>('lookup')
  const [search, setSearch] = useState('')
  const [branch, setBranch] = useState('')
  const [status, setStatus] = useState('')
  const [mobilizationStatus, setMobilizationStatus] = useState('')
  const [people, setPeople] = useState<Person[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
>>>>>>> main

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

<<<<<<< HEAD
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
=======
    {page === 'lookup' ? <>
      <div className="page-intro"><div><h2>예비군 조회</h2><p>인원 정보를 검색하고 훈련 기록을 관리하세요.</p></div><div className="page-intro-actions"><button className="button primary" onClick={() => { setAddingPerson(true); setCreatePersonError(''); setCreatePersonForm(initialCreatePersonForm) }}>+ 신규 예비군 등록</button><div className="result-count"><strong>{people.length}</strong><span>조회 인원</span></div></div></div>
      <section className="search-panel">
        <label className="search-field"><span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="이름 또는 군번으로 검색" /></label>
        <Select label="군종" value={branch} options={branches} onChange={setBranch} />
        <Select label="상태" value={status} options={statuses} labels={{ active: '복무 중', on_leave: '휴가 중' }} onChange={setStatus} />
        <Select label="동원 상태" value={mobilizationStatus} options={mobilizationStatuses} onChange={setMobilizationStatus} />
      </section>
      <section className="list-card"><div className="list-caption"><h3>인원 목록</h3><span>{search || branch || status || mobilizationStatus ? '필터 적용 중' : '전체 인원'}</span></div>
        {listLoading && <State>인원 목록을 불러오는 중입니다...</State>}
        {listError && <State error>{listError}</State>}
        {!listLoading && !listError && people.length === 0 && <State><strong>검색 결과가 없습니다</strong><span>검색어나 필터를 바꿔 다시 시도해 보세요.</span></State>}
        {!listLoading && !listError && people.length > 0 && <div className="table-wrap"><table><thead><tr><th>군번</th><th>이름</th><th>군종</th><th>계급</th><th>소속부대</th><th>분대</th><th>상태</th></tr></thead><tbody>{people.map(p => <tr key={p.military_number} onClick={() => openDetail(p)} tabIndex={0} onKeyDown={e => e.key === 'Enter' && openDetail(p)}><td className="mono">{p.military_number}</td><td className="person-name">{p.name}</td><td>{p.branch}</td><td>{p.rank ?? '-'}</td><td>{p.unit ?? '-'}</td><td>{p.squad_id ? `${p.squad_id}분대` : '-'}</td><td><StatusBadge status={p.status} /></td></tr>)}</tbody></table></div>}
      </section>
    </> : <AssignmentReviewView squads={squads} candidates={candidates} squadId={assignmentSquad} setSquadId={setAssignmentSquad} quotas={quotas} setQuotas={setQuotas} result={assignmentResult} proposal={proposal} setProposal={setProposal} tab={assignmentTab} setTab={setAssignmentTab} loading={assignmentLoading} error={assignmentError} onPrepare={prepareAssignment} onToggleCandidate={toggleAssignmentCandidate} onConfirm={confirmAssignments} onReset={resetAssignments} onAutoAssign={autoAssign300} />}

    {selectedId && <DetailModal person={selectedPerson} progress={progress} records={records} loading={detailLoading} error={detailError} tab={detailTab} setTab={setDetailTab} onClose={closeDetail}
      onEdit={() => { if (selectedPerson) { setPersonForm(selectedPerson); setEditingPerson(true) } }} onDelete={deletePerson}
      editingPerson={editingPerson} personForm={personForm} setPersonForm={setPersonForm} onSavePerson={savePerson} onCancelPerson={() => setEditingPerson(false)}
      editingRecord={editingRecord} recordForm={recordForm} setRecordForm={setRecordForm} addingRecord={addingRecord}
      onStartAdd={() => { setAddingRecord(true); setEditingRecord(null); setRecordForm({ service_year: selectedPerson?.service_year && selectedPerson.service_year <= 6 ? selectedPerson.service_year : 1, training_year: selectedPerson?.service_year && selectedPerson.service_year <= 8 ? selectedPerson.service_year : 1, training_type: '기본훈련', training_round: 1, attendance_status: 'postponed', training_hours: 0, notes: '' }) }}
      onEditRecord={r => { setEditingRecord(r.id); setAddingRecord(false); setRecordForm({ service_year: r.education_year, training_year: r.training_year ?? r.education_year, training_type: r.training_type, training_round: r.training_round, attendance_status: r.attendance_status, training_hours: r.training_hours, notes: r.notes ?? '' }) }}
      onCancelRecord={() => { setEditingRecord(null); setAddingRecord(false); setRecordForm(null) }} onSaveRecord={saveRecord} onAddRecord={addRecord} onDeleteRecord={deleteRecord} actionError={actionError} />}
    <CreatePersonModal open={addingPerson} form={createPersonForm} setForm={setCreatePersonForm} loading={createPersonLoading} error={createPersonError} onClose={() => setAddingPerson(false)} onSubmit={submitCreatePerson} />
    <TransferAssignmentModal arrival={newArrival} error={createPersonError} onClose={() => setNewArrival(null)} onConfirm={confirmNewArrival} />
  </div>
}

function AssignmentReviewView({ squads, candidates, squadId, setSquadId, quotas, setQuotas, result, proposal, setProposal, tab, setTab, loading, error, onPrepare, onToggleCandidate, onConfirm, onReset, onAutoAssign }: {
  squads: Squad[]; candidates: AssignmentCandidates; squadId: string; setSquadId: (v: string) => void; quotas: AssignmentQuotas; setQuotas: (v: AssignmentQuotas) => void;
  result: AssignmentResult | null; proposal: ProposedAssignment[]; setProposal: Dispatch<SetStateAction<ProposedAssignment[]>>; tab: string; setTab: (v: string) => void; loading: boolean; error: string; onPrepare: () => void; onToggleCandidate: (candidate: AssignmentCandidate) => void; onConfirm: () => void; onReset: () => void; onAutoAssign: () => void
}) {
  const tabs = assignmentBranches.flatMap(b => personnelCategories.map(c => `${b}-${c}`))
  const [selectedBranch, selectedCategory] = tab.split('-')
  const tabCandidates = candidates[selectedBranch]?.[selectedCategory] ?? []
  const tabProposal = proposal.filter(p => p.branch === selectedBranch && p.category === selectedCategory)
  const required = assignmentPositions.reduce((s, p) => s + (quotas[selectedBranch]?.[p]?.[selectedCategory] ?? 0), 0)
  const branchRequested = assignmentPositions.reduce((s, p) => s + personnelCategories.reduce((s2, c) => s2 + (quotas[selectedBranch]?.[p]?.[c] ?? 0), 0), 0)
  const selectedSquad = squads.find(s => String(s.id) === squadId)

  return <div className="assignment-page">
    <div className="page-intro"><div><h2>전투편성 검토</h2><p>군별·인원유형별·직책별로 후보를 분리해 확인한 뒤 확정합니다.</p></div></div>
    <div className="squad-profile-layout">
      <section className="assignment-panel"><div className="assignment-toolbar"><button className="button secondary" disabled={loading} onClick={onReset}>편성 초기화</button><button className="button primary" disabled={loading} onClick={onAutoAssign}>300명 자동 편성</button></div><label className="assignment-select">대상 분대<select value={squadId} onChange={e => setSquadId(e.target.value)}>{squads.map(s => <option key={s.id} value={s.id}>{s.name} · 현재 {s.person_count}명</option>)}</select></label>{selectedSquad && <SquadProfile squad={selectedSquad} />}</section>
      <section className="assignment-panel"><div className="section-heading"><h3>{selectedBranch} 필요 인원</h3><span>{branchRequested}명 요청</span></div><div className="quota-table"><div className="quota-row quota-head"><span>직책</span>{personnelCategories.map(c => <span key={c}>{c}</span>)}</div>{assignmentPositions.map(p => <div className="quota-row" key={p}><strong>{p}</strong>{personnelCategories.map(c => <label key={c}><input type="number" min="0" value={quotas[selectedBranch][p][c]} onChange={e => setQuotas({ ...quotas, [selectedBranch]: { ...quotas[selectedBranch], [p]: { ...quotas[selectedBranch][p], [c]: Number(e.target.value) } } })} /></label>)}</div>)}</div></section>
    </div>
    <section className="assignment-panel review-panel">
      <div className="assignment-tabs">{tabs.map(t => <button key={t} className={tab === t ? 'selected' : ''} onClick={() => setTab(t)}>{t.replace('-', ' · ')}</button>)}</div>
      <div className="review-heading"><div><h3>{selectedBranch} · {selectedCategory}</h3><p>가용 {tabCandidates.filter(p => assignmentPositions.includes(p.position)).length}명 · 필요 {required}명 · 검토안 {tabProposal.length}명</p></div><span className={tabProposal.length < required ? 'shortfall-label' : 'ready-label'}>{Math.max(required - tabProposal.length, 0)}명 부족</span></div>
      <div className="candidate-list">{tabCandidates.length === 0 && <State>현재 조건에 맞는 후보가 없습니다.</State>}{tabCandidates.map(c => { const proposed = proposal.find(p => p.military_number === c.military_number); return <article className={`candidate-row ${proposed ? 'proposed' : ''}`} key={c.military_number} onClick={() => onToggleCandidate(c)}><div><strong>{c.name}</strong><span>{c.military_number} · {c.position} · {c.specialty ?? '특기 없음'} · {c.service_year ?? '-'}년차</span></div><span className="tier-badge">{c.tier}</span>{proposed ? <select value={String(proposed.squad_id)} onClick={e => e.stopPropagation()} onChange={e => setProposal(items => items.map(p => p.military_number === c.military_number ? { ...p, squad_id: Number(e.target.value) } : p))}>{squads.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select> : <span className="candidate-status">후보 · 클릭하여 선택</span>}</article> })}</div>
      <div className="review-actions"><button className="button secondary" onClick={onPrepare}>편성안 만들기</button><button className="button primary" disabled={loading || proposal.length === 0} onClick={onConfirm}>{loading ? '확정 중...' : '검토안 확정 배정'}</button></div>
      {error && <div className="inline-error">{error}</div>}{result && <div className="confirmation-note">{result.total_assigned}명이 확정 배정되었습니다.</div>}
>>>>>>> main
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
