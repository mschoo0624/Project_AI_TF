import { useEffect, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'

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
  status: string
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

type OrganizationNode = {
  id: number
  parent_id: number | null
  kind: 'root' | 'company' | 'platoon' | 'squad'
  name: string
  squad_id: number | null
  person_count: number
  planned_strength: number | null
  planned_actual: number | null
  shortfall: number | null
}
type ScopedResult = {
  total_assigned: number
  total_shortfall: number
  scope_id: number
}
type ExpansionResult = { created_platoons: { id: number; name: string }[]; created_squads: { id: number; squad_id: number; name: string }[]; total_platoons: number; total_squads: number }

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const assignmentPositions = ['행정병', '통신병', '의무병', '운전병', '보급병']
const personnelCategories = ['병사', '부사관', '장교']
const assignmentBranches = ['육군', '해군', '해병대', '공군']

const unitNames: Record<OrganizationNode['kind'], string> = {
  root: '편제', company: '중대', platoon: '소대', squad: '분대',
}
const canAdd: Record<OrganizationNode['kind'], OrganizationNode['kind'][]> = {
  root: ['company', 'platoon', 'squad'], company: ['platoon', 'squad'],
  platoon: ['squad'], squad: [],
}

async function responseError(response: Response, fallback: string) {
  try {
    const data = await response.json() as { detail?: string }
    return data.detail ?? fallback
  } catch {
    return fallback
  }
}

export default function OrganizationPage({
  revision,
  onDataChanged,
}: {
  revision: number
  onDataChanged: () => void
}) {
  const [squads, setSquads] = useState<Squad[]>([])
  const [candidates, setCandidates] = useState<AssignmentCandidates>({})
  const [assignmentSquad, setAssignmentSquad] = useState('1')
  const [assignmentTab, setAssignmentTab] = useState('육군-병사')
  const [proposal, setProposal] = useState<ProposedAssignment[]>([])
  const [assignmentResult, setAssignmentResult] = useState<AssignmentResult | null>(null)
  const [assignmentLoading, setAssignmentLoading] = useState(false)
  const [assignmentError, setAssignmentError] = useState('')
  const [quotas, setQuotas] = useState<AssignmentQuotas>(
    Object.fromEntries(assignmentBranches.map(branch => [
      branch,
      Object.fromEntries(assignmentPositions.map(position => [
        position,
        { 병사: 1, 부사관: 0, 장교: 0 },
      ])),
    ])) as AssignmentQuotas,
  )

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      fetch(`${API_BASE}/squads`, { signal: controller.signal }),
      fetch(`${API_BASE}/squads/assignment-candidates`, { signal: controller.signal }),
    ]).then(async ([squadResponse, candidateResponse]) => {
      if (!squadResponse.ok) throw new Error(await responseError(squadResponse, '분대 목록을 불러오지 못했습니다.'))
      if (!candidateResponse.ok) throw new Error(await responseError(candidateResponse, '가용 인원을 불러오지 못했습니다.'))
      return [
        await squadResponse.json() as Squad[],
        await candidateResponse.json() as AssignmentCandidates,
      ] as const
    }).then(([nextSquads, nextCandidates]) => {
      if (controller.signal.aborted) return
      setSquads(nextSquads)
      setCandidates(nextCandidates)
      setAssignmentSquad(current =>
        nextSquads.length && !nextSquads.some(squad => String(squad.id) === current)
          ? String(nextSquads[0].id)
          : current)
    }).catch(cause => {
      if (!controller.signal.aborted) {
        setAssignmentError(cause instanceof Error ? cause.message : '편성 자료를 불러오지 못했습니다.')
      }
    })
    return () => controller.abort()
  }, [revision])

  const prepareAssignment = () => {
    const next: ProposedAssignment[] = []
    const used = new Set<string>()
    const [selectedBranch, selectedCategory] = assignmentTab.split('-')
    assignmentPositions.forEach(position => {
      const requested = quotas[selectedBranch]?.[position]?.[selectedCategory] ?? 0
      ;(candidates[selectedBranch]?.[selectedCategory] ?? [])
        .filter(candidate => candidate.position === position)
        .slice(0, requested)
        .forEach(candidate => {
          if (used.has(candidate.military_number)) return
          used.add(candidate.military_number)
          next.push({
            ...candidate,
            branch: selectedBranch,
            category: selectedCategory,
            squad_id: Number(assignmentSquad),
          })
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
      const selectedForPosition = items.filter(item =>
        item.branch === selectedBranch &&
        item.category === selectedCategory &&
        item.position === candidate.position).length
      if (selectedForPosition >= requested) return items
      return [...items, {
        ...candidate,
        branch: selectedBranch,
        category: selectedCategory,
        squad_id: Number(assignmentSquad),
      }]
    })
    setAssignmentResult(null)
    setAssignmentError('')
  }

  const confirmAssignments = async () => {
    setAssignmentLoading(true)
    setAssignmentError('')
    try {
      const response = await fetch(`${API_BASE}/squads/assignments/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          assignments: proposal.map(item => ({
            person_id: item.military_number,
            squad_id: item.squad_id,
          })),
        }),
      })
      if (!response.ok) throw new Error(await responseError(response, '전투편성에 실패했습니다.'))
      setAssignmentResult({
        squad_id: Number(assignmentSquad),
        positions: {},
        total_requested: proposal.length,
        total_assigned: proposal.length,
        total_shortfall: 0,
      })
      setProposal([])
      onDataChanged()
    } catch (cause) {
      setAssignmentError(cause instanceof Error ? cause.message : '전투편성에 실패했습니다.')
    } finally {
      setAssignmentLoading(false)
    }
  }

  const resetAssignments = async () => {
    if (!window.confirm('전체 예비군의 배정과 배정 기록을 초기화합니다. 선택한 부대에만 적용되지 않습니다. 계속하시겠습니까?')) return
    setAssignmentLoading(true)
    setAssignmentError('')
    try {
      const response = await fetch(`${API_BASE}/squads/assignments/reset`, { method: 'POST' })
      if (!response.ok) throw new Error(await responseError(response, '전투편성 초기화에 실패했습니다.'))
      setProposal([])
      setAssignmentResult(null)
      onDataChanged()
    } catch (cause) {
      setAssignmentError(cause instanceof Error ? cause.message : '전투편성 초기화에 실패했습니다.')
    } finally {
      setAssignmentLoading(false)
    }
  }

  return <OrganizationView
    squads={squads}
    refreshKey={revision}
    onRefresh={onDataChanged}
    onSelectSquad={id => setAssignmentSquad(String(id))}
  >
    <AssignmentReviewView
      squads={squads}
      candidates={candidates}
      squadId={assignmentSquad}
      setSquadId={setAssignmentSquad}
      quotas={quotas}
      setQuotas={setQuotas}
      result={assignmentResult}
      proposal={proposal}
      setProposal={setProposal}
      tab={assignmentTab}
      setTab={setAssignmentTab}
      loading={assignmentLoading}
      error={assignmentError}
      onPrepare={prepareAssignment}
      onToggleCandidate={toggleAssignmentCandidate}
      onConfirm={confirmAssignments}
      onReset={resetAssignments}
    />
  </OrganizationView>
}

function OrganizationView({ squads, refreshKey, onRefresh, onSelectSquad, children }: {
  squads: Squad[]; refreshKey: number; onRefresh: () => void; onSelectSquad: (id: number) => void;
  children: React.ReactNode
}) {
  const [nodes, setNodes] = useState<OrganizationNode[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [result, setResult] = useState<ScopedResult | null>(null)
  const [expansionResult, setExpansionResult] = useState<ExpansionResult | null>(null)
  const [draft, setDraft] = useState({ query: '', status: '', category: '', position: '' })
  const [applied, setApplied] = useState(draft)
  const [page, setPage] = useState(1)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/organization`, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(await responseError(response, '편제 정보를 불러오지 못했습니다.'))
      return response.json() as Promise<OrganizationNode[]>
    }).then(data => {
      if (controller.signal.aborted) return
      setNodes(data)
      setSelectedId(current => data.some(node => node.id === current)
        ? current : (data.find(node => node.kind === 'root')?.id
          ?? data.find(node => node.kind === 'platoon')?.id ?? null))
      setExpanded(current => new Set([...current, ...data.filter(node =>
        node.kind === 'root' || node.kind === 'platoon').map(node => node.id)]))
      setError('')
    }).catch(e => {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '편제 정보를 불러오지 못했습니다.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [refreshKey])

  const selected = nodes.find(node => node.id === selectedId) ?? null
  const childrenOf = (id: number) => nodes.filter(node => node.parent_id === id)
  const descendants = (id: number): OrganizationNode[] => childrenOf(id).flatMap(node => [node, ...descendants(node.id)])
  const scopedNodes = selected ? [selected, ...descendants(selected.id)] : []
  const scopedIds = new Set(scopedNodes.map(node => node.squad_id).filter((id): id is number => id !== null))
  const roster = squads.filter(squad => scopedIds.has(squad.id)).flatMap(squad =>
    (squad.roster ?? []).map(person => ({ ...person, squadName: squad.name })))
  const filtered = roster.filter(person => {
    const q = applied.query.trim().toLowerCase()
    return (!q || person.name.toLowerCase().includes(q) || person.military_number.toLowerCase().includes(q))
      && (!applied.category || person.category === applied.category)
      && (!applied.position || person.position === applied.position)
      && (!applied.status || person.status === applied.status)
  })
  const pageCount = Math.max(1, Math.ceil(filtered.length / 10))
  const actualPage = Math.min(page, pageCount)
  const pageRows = filtered.slice((actualPage - 1) * 10, actualPage * 10)
  const positions = [...new Set(roster.map(person => person.position).filter((value): value is string => !!value))].sort()
  const breadcrumb: OrganizationNode[] = []
  if (selected) {
    let current: OrganizationNode | undefined = selected
    while (current) {
      breadcrumb.unshift(current)
      current = nodes.find(node => node.id === current?.parent_id)
    }
  }
  const mayAdd = selected ? canAdd[selected.kind] : []
  const canAutoFill = scopedNodes.some(node =>
    node.kind === 'squad' && node.planned_strength !== null)
  const candidateParents = selected ? nodes.filter(node =>
    node.id !== selected.id && canAdd[node.kind].includes(selected.kind)
      && !descendants(selected.id).some(child => child.id === node.id)) : []

  const mutate = async (path: string, init: RequestInit, failure: string) => {
    setWorking(true); setError(''); setResult(null)
    try {
      const response = await fetch(`${API_BASE}${path}`, init)
      if (!response.ok) throw new Error(await responseError(response, failure))
      onRefresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : failure) }
    finally { setWorking(false) }
  }
  const addUnit = (kind: OrganizationNode['kind']) => {
    if (!selected || !mayAdd.includes(kind)) return
    const name = window.prompt(`${unitNames[kind]} 이름을 입력하세요.`)?.trim()
    if (!name) return
    void mutate('/organization', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parent_id: selected.id, kind, name }) }, `${unitNames[kind]} 추가 실패`)
    setExpanded(current => new Set([...current, selected.id]))
  }
  const deleteSelected = () => {
    if (!selected || selected.kind === 'root' || !window.confirm(`${selected.name}을(를) 삭제하시겠습니까?\n분대인 경우 연결된 분대도 함께 삭제됩니다. 하위 단위나 배정 인원이 있는 경우 삭제되지 않습니다.`)) return
    void mutate(`/organization/${selected.id}`, { method: 'DELETE' }, '편제 삭제 실패')
  }
  const moveSelected = (parentId: number) => {
    if (!selected) return
    void mutate(`/organization/${selected.id}/parent`, { method: 'PATCH',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ parent_id: parentId }) }, '편제 이동 실패')
    setExpanded(current => new Set([...current, parentId]))
  }
  const autoFill = async () => {
    if (!selected || working || !canAutoFill) return
    setWorking(true); setError(''); setResult(null)
    try {
      const response = await fetch(`${API_BASE}/organization/${selected.id}/auto-fill`, { method: 'POST' })
      if (!response.ok) throw new Error(await responseError(response, '자동편성 실패'))
      setResult(await response.json() as ScopedResult)
      onRefresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '자동편성 실패') }
    finally { setWorking(false) }
  }
  const expandFormation = async () => {
    if (!selected || selected.kind !== 'root' || working) return
    setWorking(true); setError(''); setExpansionResult(null)
    try {
      const response = await fetch(`${API_BASE}/organization/${selected.id}/expand`, { method: 'POST' })
      if (!response.ok) throw new Error(await responseError(response, '편제 확장 실패'))
      setExpansionResult(await response.json() as ExpansionResult)
      onRefresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '편제 확장 실패') }
    finally { setWorking(false) }
  }

  const treeRows = (parentId: number | null, level: number): React.ReactNode =>
    nodes.filter(node => node.parent_id === parentId)
      .sort((a, b) => {
        const order = { root: 0, platoon: 1, company: 2, squad: 3 }
        return order[a.kind] - order[b.kind] || a.id - b.id
      }).map(node => {
      const hasChildren = childrenOf(node.id).length > 0
      const open = expanded.has(node.id)
      const complete = node.planned_strength === null ? '—' : `${node.person_count}/${node.planned_strength}`
      return <div key={node.id}>
        <div className={`rm-org-tree-item ${selectedId === node.id ? 'is-active' : ''}`}
          style={{ paddingLeft: `${12 + level * 13}px` }}>
          {hasChildren ? <button type="button" className="rm-org-toggle"
            aria-label={`${node.name} ${open ? '접기' : '펼치기'}`} aria-expanded={open}
            onClick={() => setExpanded(old => { const next = new Set(old); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); return next })}>
            {open ? '⌄' : '›'}</button> : <span className="rm-org-toggle-placeholder" />}
          <button type="button" className="rm-org-tree-select" onClick={() => {
            setSelectedId(node.id); setPage(1); setResult(null)
            if (node.squad_id !== null) onSelectSquad(node.squad_id)
          }} aria-current={selectedId === node.id ? 'page' : undefined}>
            <span aria-hidden="true" className="rm-org-folder">{node.kind === 'squad' ? '▢' : '▱'}</span>{node.name}
          </button>
          <span className={`rm-org-tree-count ${node.shortfall ? 'is-short' : ''}`}>{complete}</span>
        </div>
        {hasChildren && open && treeRows(node.id, level + 1)}
      </div>
    })

  return <div className="rm-org-layout">
    <aside className="rm-org-navigator" aria-label="전투편성 트리">
      <header><strong>전투편성표</strong><span>⌄</span></header>
      <div className="rm-org-tree">{treeRows(null, 0)}</div>
      <footer className="rm-org-nav-footer">
        <strong>편성 기준</strong>
        <p>분대 계획 정원 <b>11명</b></p>
        <p>소속 분대 총수 <b>{nodes.filter(node => node.kind === 'squad').length}개</b></p>
        <p>이전 예시 분대에 배정된 인원은 미편성으로 전환됩니다.</p>
        <p>상위 단위 정원은 하위 분대 정원을 합산합니다.</p>
      </footer>
    </aside>

    <main className="rm-org-main">
      {loading && <p className="rm-org-message">편제 정보를 불러오는 중입니다.</p>}
      {selected && <>
        <div className="rm-org-breadcrumb">{breadcrumb.map((node, index) =>
          <span key={node.id}>{index > 0 ? ' › ' : ''}{node.name}</span>)}</div>
        <h1>{selected.name} 전투편성</h1>
        <p className="rm-org-description">선택한 {unitNames[selected.kind]}와 하위 단위에 편성된 인원을 조회합니다.</p>
        <div className="rm-org-metrics">
          <section><span>계획인원</span><b>{selected.planned_strength === null ? '미설정' : `${selected.planned_strength}명`}</b></section>
          <section><span>편성인원</span><b>{selected.person_count}명</b></section>
          <section><span>편성부족인원</span><b>{selected.shortfall === null ? '미설정' : `${selected.shortfall}명`}</b></section>
        </div>
        <form className="rm-org-filters" onSubmit={event => { event.preventDefault(); setApplied(draft); setPage(1) }}>
          <label><span aria-hidden="true">⌕</span><input aria-label="편성 인원 검색" placeholder="이름, 군번을 입력하세요."
            value={draft.query} onChange={event => setDraft(p => ({ ...p, query: event.target.value }))} /></label>
          <select aria-label="편성 상태" value={draft.status} onChange={event => setDraft(p => ({ ...p, status: event.target.value }))}>
            <option value="">전체 상태</option><option value="active">복무 중</option><option value="on_leave">휴가 중</option>
          </select>
          <select aria-label="인원 구분" value={draft.category} onChange={event => setDraft(p => ({ ...p, category: event.target.value }))}>
            <option value="">전체 구분</option>{['병사', '부사관', '장교', '기타'].map(value => <option key={value}>{value}</option>)}
          </select>
          <select aria-label="병과/직책" value={draft.position} onChange={event => setDraft(p => ({ ...p, position: event.target.value }))}>
            <option value="">전체 병과</option>{positions.map(value => <option key={value}>{value}</option>)}
          </select>
          <button type="submit" className="rm-org-primary">검색</button>
          <button type="button" onClick={() => { setDraft({ query: '', status: '', category: '', position: '' }); setApplied({ query: '', status: '', category: '', position: '' }); setPage(1) }}>↶ 초기화</button>
        </form>
        <section className="rm-org-roster" aria-label="편성 인원 목록">
          <div className="rm-org-table-scroll"><table>
            <thead><tr><th>번호</th><th>성명</th><th>군번</th><th>구분</th><th>소속 분대</th><th>병과·직책</th><th>상태</th><th>편성 여부</th></tr></thead>
            <tbody>{pageRows.map((person, index) => <tr key={person.military_number}>
              <td>{(actualPage - 1) * 10 + index + 1}</td><td><b>{person.name}</b></td><td>{person.military_number}</td>
              <td>{person.category}</td><td>{person.squadName}</td><td>{person.position ?? '—'}</td>
              <td><span className="rm-org-badge rm-org-badge--green">{person.status === 'active' ? '복무 중' : person.status === 'on_leave' ? '휴가 중' : person.status}</span></td>
              <td><span className="rm-org-badge rm-org-badge--blue">편성</span></td>
            </tr>)}</tbody>
          </table>{filtered.length === 0 && <p className="rm-org-message">해당 단위에 편성된 인원이 없습니다.</p>}</div>
          <footer><span>총 {filtered.length}명 중 {filtered.length ? (actualPage - 1) * 10 + 1 : 0}–{Math.min(actualPage * 10, filtered.length)}명 표시</span>
            <div><button type="button" disabled={actualPage === 1} onClick={() => setPage(p => p - 1)}>‹</button>
              {Array.from({ length: Math.min(pageCount, 5) }, (_, index) => {
                const number = Math.max(1, Math.min(actualPage - 2, pageCount - 4)) + index
                return <button key={number} type="button" className={actualPage === number ? 'is-current' : ''}
                  onClick={() => setPage(number)}>{number}</button>
              })}
              <button type="button" disabled={actualPage === pageCount} onClick={() => setPage(p => p + 1)}>›</button>
            </div>
          </footer>
        </section>
        <details className="rm-org-manual">
          <summary>기존 수동 편성안 작성 · 검토 · 전체 편성 초기화</summary>
          {children}
        </details>
      </>}
      {!loading && !selected && <p className="rm-org-message">왼쪽에서 편제 단위를 선택하세요.</p>}
      {error && <p className="rm-org-error" role="alert">{error}</p>}
    </main>

    {selected && <aside className="rm-org-detail" aria-label="편제 상세 정보">
      <header><strong>{unitNames[selected.kind]} 상세 정보</strong></header>
      <div className="rm-org-detail-body">
        <div className="rm-org-unit-icon" aria-hidden="true">◇</div>
        <h2>{selected.name}</h2>
        <p>{breadcrumb.map(node => node.name).join(' · ')}</p>
        <div className="rm-org-small-metrics"><span>계획 인원 <b>{selected.planned_strength === null ? '미설정' : `${selected.planned_strength}명`}</b></span>
          <span>편성 인원 <b>{selected.person_count}명</b></span></div>
        <p className="rm-org-shortfall">편성 부족인원 <b>{selected.shortfall === null ? '미설정' : `${selected.shortfall}명`}</b></p>
        {selected.planned_strength !== null && <div className="rm-org-rate">분대 정원 기준 편성률 <b>{selected.planned_strength > 0 ? Math.round((selected.planned_actual ?? 0) / selected.planned_strength * 100) : 0}%</b>
          <div><i style={{ width: `${Math.min(100, selected.planned_strength > 0 ? (selected.planned_actual ?? 0) / selected.planned_strength * 100 : 0)}%` }} /></div></div>}
        <section className="rm-org-assistant"><div><h3>AI 어시스턴트</h3><button type="button" disabled={working || !canAutoFill} onClick={() => void autoFill()}>자동편성</button>{selected.kind === 'root' && <button type="button" disabled={working} onClick={() => void expandFormation()}>소대·분대 추가</button>}</div>
          <p>자동편성은 기존 분대의 빈 자리만 채웁니다. 소대와 분대를 늘리려면 별도 확장 버튼을 사용하세요.</p>
          {result && <p className="rm-org-success" role="status">{result.total_assigned}명 추가 편성 · 잔여 부족 {result.total_shortfall}명</p>}
          {expansionResult && <p className="rm-org-success" role="status">현재 소대 {expansionResult.total_platoons}개 · 분대 {expansionResult.total_squads}개</p>}
          {!canAutoFill && <p>이 단위에 분대가 없습니다. 편제 관리에서 분대를 추가하세요.</p>}
        </section>
        <section className="rm-org-breakdown"><h3>편성 요약</h3>
          {Object.entries(roster.reduce<Record<string, number>>((acc, person) => {
            const position = person.position || '미지정'
            acc[position] = (acc[position] ?? 0) + 1
            return acc
          }, {})).map(([position, count]) => <div key={position}><span>{position}</span><b>{count}명</b></div>)}
          {roster.length === 0 && <p>편성 인원이 없습니다.</p>}
        </section>
        <section className="rm-org-edit"><h3>편제 관리</h3>
          {mayAdd.map(kind => <button key={kind} type="button" disabled={working} onClick={() => addUnit(kind)}>+ {unitNames[kind]} 추가</button>)}
          {candidateParents.length > 0 && <label>상위 단위 이동
            <select value={selected.parent_id ?? ''} disabled={working}
              onChange={event => moveSelected(Number(event.target.value))}>
              {candidateParents.map(node => <option value={node.id} key={node.id}>{node.name} ({unitNames[node.kind]})</option>)}
            </select>
          </label>}
          {selected.kind !== 'root' && <button type="button" className="rm-org-delete" disabled={working} onClick={deleteSelected}>선택 단위 삭제</button>}
          <small>하위 단위나 인원이 있는 편제는 삭제할 수 없습니다. 먼저 다른 곳으로 이동하세요.</small>
        </section>
      </div>
    </aside>}
  </div>
}

function AssignmentReviewView({ squads, candidates, squadId, setSquadId, quotas, setQuotas, result, proposal, setProposal, tab, setTab, loading, error, onPrepare, onToggleCandidate, onConfirm, onReset }: {
  squads: Squad[]; candidates: AssignmentCandidates; squadId: string; setSquadId: (v: string) => void; quotas: AssignmentQuotas; setQuotas: (v: AssignmentQuotas) => void;
  result: AssignmentResult | null; proposal: ProposedAssignment[]; setProposal: Dispatch<SetStateAction<ProposedAssignment[]>>; tab: string; setTab: (v: string) => void; loading: boolean; error: string; onPrepare: () => void; onToggleCandidate: (candidate: AssignmentCandidate) => void; onConfirm: () => void; onReset: () => void
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
      <section className="assignment-panel"><div className="assignment-toolbar"><button className="button secondary" disabled={loading} onClick={onReset}>편성 초기화</button></div><label className="assignment-select">대상 분대<select value={squadId} onChange={e => setSquadId(e.target.value)}>{squads.map(s => <option key={s.id} value={s.id}>{s.name} · 현재 {s.person_count}명</option>)}</select></label>{selectedSquad && <SquadProfile squad={selectedSquad} />}</section>
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
