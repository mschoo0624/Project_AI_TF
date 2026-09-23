import { useEffect, useRef, useState } from 'react'

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
  rank: string | null
  category: string
  position: string | null
  specialty: string | null
  service_year: number | null
  status: string
}

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
type RosterSortKey = 'name' | 'military_number' | 'branch' | 'rank' | 'position' | 'squadName'
const rosterColumns: { key: RosterSortKey; label: string }[] = [
  { key: 'name', label: '이름' }, { key: 'military_number', label: '군번' },
  { key: 'branch', label: '군별' }, { key: 'rank', label: '계급' },
  { key: 'position', label: '직책(병과)' }, { key: 'squadName', label: '소속 분대(편성 부대)' },
]
const rosterCollator = new Intl.Collator('ko', { numeric: true })
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
  const [rosterError, setRosterError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/squads`, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(await responseError(response, '분대 목록을 불러오지 못했습니다.'))
      return response.json() as Promise<Squad[]>
    }).then(nextSquads => {
      if (controller.signal.aborted) return
      setSquads(nextSquads)
      setRosterError('')
    }).catch(cause => {
      if (!controller.signal.aborted) {
        setRosterError(cause instanceof Error ? cause.message : '편성 자료를 불러오지 못했습니다.')
      }
    })
    return () => controller.abort()
  }, [revision])

  return <OrganizationView squads={squads} refreshKey={revision} onRefresh={onDataChanged} rosterError={rosterError} />
}

function OrganizationView({ squads, refreshKey, onRefresh, rosterError }: {
  squads: Squad[]; refreshKey: number; onRefresh: () => void; rosterError: string;
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
  const [sort, setSort] = useState<{ key: RosterSortKey; direction: 'ascending' | 'descending' }>({ key: 'military_number', direction: 'ascending' })
  const [checkedMembers, setCheckedMembers] = useState<Set<string>>(() => new Set())
  const [releaseTarget, setReleaseTarget] = useState<{ id: number; name: string; personIds: string[] } | null>(null)
  const [releaseError, setReleaseError] = useState('')
  const releaseDialog = useRef<HTMLDialogElement>(null)
  const unitDialog = useRef<HTMLDialogElement>(null)
  const [unitEditor, setUnitEditor] = useState<{ mode: 'add' | 'rename'; node: OrganizationNode } | null>(null)
  const [unitKind, setUnitKind] = useState<OrganizationNode['kind']>('squad')
  const [unitName, setUnitName] = useState('')
  const [unitError, setUnitError] = useState('')

  useEffect(() => {
    if (unitEditor) unitDialog.current?.showModal()
    else unitDialog.current?.close()
  }, [unitEditor])

  useEffect(() => {
    if (releaseTarget) releaseDialog.current?.showModal()
    else releaseDialog.current?.close()
  }, [releaseTarget])

  const releaseMembers = async (nodeId: number, personIds: string[]) => {
    if (working || !personIds.length) return
    setWorking(true); setError(''); setReleaseError(''); setResult(null)
    try {
      const response = await fetch(`${API_BASE}/organization/${nodeId}/release-members`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_ids: personIds }),
      })
      if (!response.ok) throw new Error(await responseError(response, '편성 해제에 실패했습니다.'))
      setReleaseTarget(null)
      setCheckedMembers(new Set())
      onRefresh()
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : '편성 해제에 실패했습니다.'
      setReleaseError(message)
    } finally { setWorking(false) }
  }

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
  const pageSize = 15
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const actualPage = Math.min(page, pageCount)
  const sorted = [...filtered].sort((a, b) => {
    const left = a[sort.key], right = b[sort.key]
    if (left == null && right != null) return 1
    if (left != null && right == null) return -1
    const comparison = rosterCollator.compare(left ?? '', right ?? '')
    return (sort.direction === 'ascending' ? comparison : -comparison)
      || rosterCollator.compare(a.military_number, b.military_number)
  })
  const pageRows = sorted.slice((actualPage - 1) * pageSize, actualPage * pageSize)
  const selectedMembers = roster.filter(person => checkedMembers.has(person.military_number))
  const allMembersChecked = roster.length > 0 && selectedMembers.length === roster.length
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
  const openUnitEditor = (mode: 'add' | 'rename') => {
    if (!selected || working || (mode === 'add' && !mayAdd.length)) return
    setUnitName(mode === 'rename' ? selected.name : '')
    setUnitKind(mayAdd[0] ?? 'squad')
    setUnitError('')
    setUnitEditor({ mode, node: selected })
  }
  const saveUnit = async () => {
    if (!unitEditor || working || !unitName.trim()) return
    const { mode, node } = unitEditor
    setWorking(true); setUnitError('')
    try {
      const response = await fetch(`${API_BASE}/organization${mode === 'rename' ? `/${node.id}/name` : ''}`, {
        method: mode === 'rename' ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mode === 'rename' ? { name: unitName.trim() }
          : { parent_id: node.id, kind: unitKind, name: unitName.trim() }),
      })
      if (!response.ok) throw new Error(await responseError(response, '편제 저장에 실패했습니다.'))
      if (mode === 'add') setExpanded(current => new Set([...current, node.id]))
      setUnitEditor(null)
      onRefresh()
    } catch (cause) { setUnitError(cause instanceof Error ? cause.message : '편제 저장에 실패했습니다.') }
    finally { setWorking(false) }
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
            setSelectedId(node.id); setPage(1); setResult(null); setCheckedMembers(new Set())
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
      <div className="rm-org-tree" tabIndex={0} aria-label="편제 목록">{treeRows(null, 0)}
      <div className="rm-org-nav-footer">
        <strong>편성 기준</strong>
        <p>분대 계획 정원 <b>11명</b></p>
        <p>소속 분대 총수 <b>{nodes.filter(node => node.kind === 'squad').length}개</b></p>
        <p>이전 예시 분대에 배정된 인원은 미편성으로 전환됩니다.</p>
        <p>상위 단위 정원은 하위 분대 정원을 합산합니다.</p>
      </div>
      </div>
      <footer className="rm-org-toolbar" aria-label="편제 관리 도구">
        <button type="button" title="하위 편제 추가" aria-label="하위 편제 추가" disabled={working || !mayAdd.length} onClick={() => openUnitEditor('add')}><span aria-hidden="true">+</span></button>
        <button type="button" className="rm-org-toolbar-delete" title="선택 단위 삭제" aria-label="선택 단위 삭제" disabled={working || !selected || selected.kind === 'root'} onClick={deleteSelected}><span aria-hidden="true">−</span></button>
        <button type="button" title="이름 바꾸기" aria-label="이름 바꾸기" disabled={working || !selected} onClick={() => openUnitEditor('rename')}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 20h16M5 15l-1 4 4-1L19 7l-3-3L5 15ZM14 6l3 3" /></svg>
        </button>
        <span>편제 관리</span>
      </footer>
    </aside>

    <main className="rm-org-main">
      {loading && <p className="rm-org-message">편제 정보를 불러오는 중입니다.</p>}
      {selected && <>
        <div className="rm-org-breadcrumb">{breadcrumb.map((node, index) =>
          <span key={node.id}>{index > 0 ? ' › ' : ''}{node.name}</span>)}</div>
        <div className="rm-org-metrics">
          <section><span>계획인원</span><b>{selected.planned_strength === null ? '미설정' : `${selected.planned_strength}명`}</b></section>
          <section><span>편성인원</span><b>{selected.person_count}명</b></section>
          <section><span>편성부족인원</span><b>{selected.shortfall === null ? '미설정' : `${selected.shortfall}명`}</b></section>
        </div>
        <form className="rm-org-filters" onSubmit={event => { event.preventDefault(); setApplied(draft); setPage(1); setCheckedMembers(new Set()) }}>
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
          <button type="button" onClick={() => { setDraft({ query: '', status: '', category: '', position: '' }); setApplied({ query: '', status: '', category: '', position: '' }); setPage(1); setCheckedMembers(new Set()) }}>↶ 초기화</button>
          <button type="button" className="rm-org-release" disabled={working || selectedMembers.length === 0}
            onClick={() => { setReleaseError(''); setReleaseTarget({ id: selected.id, name: breadcrumb.map(node => node.name).join('>'), personIds: selectedMembers.map(person => person.military_number) }) }}>편성 해제{selectedMembers.length > 0 ? ` (${selectedMembers.length})` : ''}</button>
        </form>
        <section className="rm-org-roster" aria-label="편성 인원 목록">
          <div className="rm-org-table-scroll"><table>
            <colgroup>{[4, 5, 15, 18, 9, 10, 17, 22].map((width, index) => <col key={index} style={{ width: `${width}%` }} />)}</colgroup>
            <thead><tr><th className="rm-org-check-column"><input type="checkbox" aria-label="선택한 부대 전체 인원 선택" title="페이지·검색 조건과 관계없이 부대 전체 인원 선택" checked={allMembersChecked} disabled={working || roster.length === 0}
              ref={element => { if (element) element.indeterminate = !allMembersChecked && selectedMembers.length > 0 }}
              onChange={event => setCheckedMembers(event.target.checked ? new Set(roster.map(person => person.military_number)) : new Set())} /></th><th>번호</th>
              {rosterColumns.map(column => <th key={column.key} scope="col" aria-sort={sort.key === column.key ? sort.direction : 'none'}>
                <button type="button" className="rm-sort-button"
                  aria-label={`${column.label}, ${sort.key === column.key && sort.direction === 'ascending' ? '내림차순' : '오름차순'} 정렬`}
                  onClick={() => { setSort(current => ({ key: column.key, direction: current.key === column.key && current.direction === 'ascending' ? 'descending' : 'ascending' })); setPage(1) }}>
                  <span>{column.label}</span><span className="rm-sort-indicator" aria-hidden="true">{sort.key === column.key ? (sort.direction === 'ascending' ? '▼' : '▲') : ''}</span>
                </button>
              </th>)}
            </tr></thead>
            <tbody>{pageRows.map((person, index) => <tr key={person.military_number}>
              <td className="rm-org-check-column"><input type="checkbox" aria-label={`${person.name} 선택`} checked={checkedMembers.has(person.military_number)} disabled={working}
                onChange={event => { const checked = event.target.checked; setCheckedMembers(previous => { const next = new Set(previous); if (checked) next.add(person.military_number); else next.delete(person.military_number); return next }) }} /></td>
              <td>{(actualPage - 1) * pageSize + index + 1}</td><td><b>{person.name}</b></td><td>{person.military_number}</td>
              <td>{person.branch}</td><td>{person.rank ?? '—'}</td><td title={person.position ?? undefined}>{person.position ?? '—'}</td><td title={person.squadName}>{person.squadName}</td>
            </tr>)}</tbody>
          </table>{filtered.length === 0 && <p className="rm-org-message">해당 단위에 편성된 인원이 없습니다.</p>}</div>
          <footer><span>총 {filtered.length}명 중 {filtered.length ? (actualPage - 1) * pageSize + 1 : 0}–{Math.min(actualPage * pageSize, filtered.length)}명 표시</span>
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
      </>}
      {!loading && !selected && <p className="rm-org-message">왼쪽에서 편제 단위를 선택하세요.</p>}
      {rosterError && <p className="rm-org-error" role="alert">{rosterError}</p>}
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
          {!canAutoFill && <p>이 단위에 분대가 없습니다. 왼쪽 아래 + 버튼으로 분대를 추가하세요.</p>}
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
          {candidateParents.length > 0 && <label>상위 단위 이동
            <select value={selected.parent_id ?? ''} disabled={working}
              onChange={event => moveSelected(Number(event.target.value))}>
              {candidateParents.map(node => <option value={node.id} key={node.id}>{node.name} ({unitNames[node.kind]})</option>)}
            </select>
          </label>}
          <small>하위 단위나 인원이 있는 편제는 삭제할 수 없습니다. 먼저 다른 곳으로 이동하세요.</small>
        </section>
      </div>
    </aside>}
    <dialog ref={unitDialog} className="rm-org-release-dialog rm-org-unit-dialog" aria-labelledby="rm-unit-title"
      onCancel={event => { if (working) event.preventDefault(); else setUnitEditor(null) }}>
      <form onSubmit={event => { event.preventDefault(); void saveUnit() }}>
        <h2 id="rm-unit-title">{unitEditor?.mode === 'add' ? '하위 편제 추가' : '이름 바꾸기'}</h2>
        <p>{unitEditor?.node.name}{unitEditor?.mode === 'add' ? ' 아래에 새 편제를 추가합니다.' : '의 이름을 변경합니다.'}</p>
        {unitEditor?.mode === 'add' && <label>편제 종류<select value={unitKind} disabled={working}
          onChange={event => setUnitKind(event.target.value as OrganizationNode['kind'])}>
          {(['company', 'platoon', 'squad'] as const).map(kind => <option key={kind} value={kind} disabled={!canAdd[unitEditor.node.kind].includes(kind)}>{unitNames[kind]}</option>)}
        </select></label>}
        <label>이름<input autoFocus required maxLength={100} value={unitName} disabled={working} placeholder="편제 이름을 입력하세요"
          onChange={event => setUnitName(event.target.value)} /></label>
        {unitError && <p className="rm-org-error" role="alert">{unitError}</p>}
        <div className="rm-org-release-actions">
          <button type="submit" className="rm-org-save" disabled={working || !unitName.trim()}>{working ? '저장 중…' : unitEditor?.mode === 'add' ? '추가' : '저장'}</button>
          <button type="button" disabled={working} onClick={() => setUnitEditor(null)}>취소</button>
        </div>
      </form>
    </dialog>
    <dialog ref={releaseDialog} className="rm-org-release-dialog" aria-labelledby="rm-release-question"
      onCancel={event => { if (working) event.preventDefault(); else setReleaseTarget(null) }}>
      <p id="rm-release-question">선택된 {releaseTarget?.personIds.length ?? 0}명을 <strong>{releaseTarget?.name}</strong> 편성에서 해제하시겠습니까?</p>
      {releaseError && <p className="rm-org-error" role="alert">{releaseError}</p>}
      <div className="rm-org-release-actions">
        <button type="button" className="rm-org-release" disabled={working}
          onClick={() => { if (releaseTarget) void releaseMembers(releaseTarget.id, releaseTarget.personIds) }}>{working ? '해제 중…' : '확인'}</button>
        <button type="button" autoFocus disabled={working} onClick={() => setReleaseTarget(null)}>취소</button>
      </div>
    </dialog>
  </div>
}
