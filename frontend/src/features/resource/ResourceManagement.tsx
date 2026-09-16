import { useEffect, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import './ResourceManagement.css'

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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const assignmentPositions = ['행정병', '통신병', '의무병', '운전병', '보급병']
const personnelCategories = ['병사', '부사관', '장교']
const assignmentBranches = ['육군', '해군', '해병대', '공군']

async function responseError(response: Response, fallback: string) {
  try {
    const data = await response.json() as { detail?: string }
    return data.detail ?? fallback
  } catch { return fallback }
}

function ResourceManagement() {
  const [squads, setSquads] = useState<Squad[]>([])
  const [candidates, setCandidates] = useState<AssignmentCandidates>({})
  const [assignmentSquad, setAssignmentSquad] = useState('1')
  const [assignmentTab, setAssignmentTab] = useState('육군-병사')
  const [proposal, setProposal] = useState<ProposedAssignment[]>([])
  const [assignmentResult, setAssignmentResult] = useState<AssignmentResult | null>(null)
  const [assignmentLoading, setAssignmentLoading] = useState(false)
  const [assignmentError, setAssignmentError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [quotas, setQuotas] = useState<AssignmentQuotas>(
    Object.fromEntries(assignmentBranches.map(b => [b, Object.fromEntries(assignmentPositions.map(p => [p, { 병사: 1, 부사관: 0, 장교: 0 }]))])) as AssignmentQuotas
  )

  useEffect(() => {
    Promise.all([fetch(`${API_BASE}/squads`), fetch(`${API_BASE}/squads/assignment-candidates`)])
      .then(async ([s, c]) => {
        if (!s.ok) throw new Error(await responseError(s, '분대 목록을 불러오지 못했습니다.'))
        if (!c.ok) throw new Error(await responseError(c, '가용 인원을 불러오지 못했습니다.'))
        return [await s.json() as Squad[], await c.json() as AssignmentCandidates] as const
      })
      .then(([s, c]) => {
        setSquads(s)
        setCandidates(c)
        if (s.length && !s.some(x => String(x.id) === assignmentSquad)) setAssignmentSquad(String(s[0].id))
      })
      .catch(e => setAssignmentError(e instanceof Error ? e.message : '전투편성 자료를 불러오지 못했습니다.'))
  }, [refreshKey])

  const prepareAssignment = () => {
    const next: ProposedAssignment[] = []
    const used = new Set<string>()
    const [selectedBranch, selectedCategory] = assignmentTab.split('-')
    assignmentPositions.forEach(p => {
      const requested = quotas[selectedBranch]?.[p]?.[selectedCategory] ?? 0
      ;(candidates[selectedBranch]?.[selectedCategory] ?? []).filter(x => x.position === p).slice(0, requested).forEach(x => {
        if (used.has(x.military_number)) return
        used.add(x.military_number)
        next.push({ ...x, branch: selectedBranch, category: selectedCategory, squad_id: Number(assignmentSquad) })
      })
    })
    setProposal(next)
    setAssignmentResult(null)
    setAssignmentError('')
  }

  const toggleAssignmentCandidate = (candidate: AssignmentCandidate) => {
    const [selectedBranch, selectedCategory] = assignmentTab.split('-')
    setProposal(items => {
      const existing = items.find(item => item.military_number === candidate.military_number)
      if (existing) return items.filter(item => item.military_number !== candidate.military_number)
      const requested = quotas[selectedBranch]?.[candidate.position]?.[selectedCategory] ?? 0
      const selectedForPosition = items.filter(item => item.branch === selectedBranch && item.category === selectedCategory && item.position === candidate.position).length
      if (selectedForPosition >= requested) return items
      return [...items, { ...candidate, branch: selectedBranch, category: selectedCategory, squad_id: Number(assignmentSquad) }]
    })
    setAssignmentResult(null)
    setAssignmentError('')
  }

  const confirmAssignments = async () => {
    setAssignmentLoading(true); setAssignmentError('')
    try {
      const r = await fetch(`${API_BASE}/squads/assignments/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assignments: proposal.map(x => ({ person_id: x.military_number, squad_id: x.squad_id })) })
      })
      if (!r.ok) throw new Error(await responseError(r, '전투편성에 실패했습니다.'))
      setAssignmentResult({ squad_id: Number(assignmentSquad), positions: {}, total_requested: proposal.length, total_assigned: proposal.length, total_shortfall: 0 })
      setProposal([])
      setRefreshKey(k => k + 1)
    } catch (e) { setAssignmentError(e instanceof Error ? e.message : '전투편성에 실패했습니다.') }
    finally { setAssignmentLoading(false) }
  }

  const resetAssignments = async () => {
    if (!window.confirm('모든 예비군의 현재 분대와 배정 기록을 초기화하시겠습니까?')) return
    setAssignmentLoading(true); setAssignmentError('')
    try {
      const r = await fetch(`${API_BASE}/squads/assignments/reset`, { method: 'POST' })
      if (!r.ok) throw new Error(await responseError(r, '전투편성 초기화에 실패했습니다.'))
      setProposal([]); setAssignmentResult(null); setRefreshKey(k => k + 1)
    } catch (e) { setAssignmentError(e instanceof Error ? e.message : '전투편성 초기화에 실패했습니다.') }
    finally { setAssignmentLoading(false) }
  }

  const autoAssign300 = async () => {
    setAssignmentLoading(true); setAssignmentError('')
    try {
      const r = await fetch(`${API_BASE}/squads/assignments/auto`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ limit: 300 })
      })
      if (!r.ok) throw new Error(await responseError(r, '300명 자동 편성에 실패했습니다.'))
      const data = await r.json() as { total_assigned: number }
      setAssignmentResult({ squad_id: 0, positions: {}, total_requested: data.total_assigned, total_assigned: data.total_assigned, total_shortfall: 0 })
      setProposal([]); setRefreshKey(k => k + 1)
    } catch (e) { setAssignmentError(e instanceof Error ? e.message : '300명 자동 편성에 실패했습니다.') }
    finally { setAssignmentLoading(false) }
  }

  return <div className="resource-module">
    <AssignmentReviewView
      squads={squads} candidates={candidates} squadId={assignmentSquad} setSquadId={setAssignmentSquad}
      quotas={quotas} setQuotas={setQuotas} result={assignmentResult} proposal={proposal} setProposal={setProposal}
      tab={assignmentTab} setTab={setAssignmentTab} loading={assignmentLoading} error={assignmentError}
      onPrepare={prepareAssignment} onToggleCandidate={toggleAssignmentCandidate} onConfirm={confirmAssignments}
      onReset={resetAssignments} onAutoAssign={autoAssign300}
    />
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
    </section>
    {selectedSquad && <section className="assignment-panel roster-panel"><div className="section-heading"><h3>{selectedSquad.name} 전투편성표</h3><span>{selectedSquad.person_count}명</span></div>{selectedSquad.roster?.length ? <div className="table-wrap"><table><thead><tr><th>군번</th><th>성명</th><th>군종</th><th>인원유형</th><th>직책</th><th>주특기</th><th>연차</th></tr></thead><tbody>{selectedSquad.roster.map(person => <tr key={person.military_number}><td className="mono">{person.military_number}</td><td className="person-name">{person.name}</td><td>{person.branch}</td><td>{person.category}</td><td>{person.position ?? '-'}</td><td>{person.specialty ?? '-'}</td><td>{person.service_year ?? '-'}년차</td></tr>)}</tbody></table></div> : <State>현재 배정된 인원이 없습니다.</State>}</section>}
  </div>
}

function SquadProfile({ squad }: { squad: Squad }) {
  const entries = Object.entries(squad.breakdown ?? {})
  return <div className="squad-profile"><div className="circle-chart"><strong>{squad.person_count}</strong><span>현재 인원</span></div><div>{entries.length ? entries.map(([k, v]) => <span key={k}>{k.replace('-', ' · ')} {v}명</span>) : <span>구성 데이터 없음</span>}</div></div>
}


function State({ children }: { children: React.ReactNode }) {
  return <div className="state">{children}</div>
}
export default ResourceManagement