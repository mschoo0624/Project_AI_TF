import { useEffect, useMemo, useState } from 'react'
import {
  acceptDocument, fetchBootstrap, rejectDocument, verifyDocument,
  type Bootstrap, type Person, type QueueItem,
} from './api'
import './ReviewManagement.css'

// Only the appearance of the existing review feature is changed here.
// Its data source and document-action implementations remain in ./api.ts.
type ReviewTab = 'roster' | 'inbox'
type QueuedRow = QueueItem & { done: string | null }
type DatedQueueItem = QueueItem & {
  application_date?: string | null
  applied_at?: string | null
  submitted_at?: string | null
}

function applicationDate(item: QueueItem): string {
  const dated = item as DatedQueueItem
  // The current API exports `issued`, not the date of an application.
  const value = dated.application_date ?? dated.applied_at ?? dated.submitted_at
  return value ? value.slice(0, 10).replace(/-/g, '.') : '—'
}

function reviewReason(item: QueueItem): string {
  const classification = item.if_accepted_classification || item.current_classification || ''
  if (classification.includes('연기')) return '연기자'
  if (classification.includes('보류') || classification.includes('후순위')) return '보류자'
  return item.type
}

function ClassChip({ label }: { label: string }) {
  const tone = label.includes('연기') ? 'postponed' : label.includes('보류') || label.includes('후순위') ? 'deferred' : 'normal'
  return <span className={`review-class-chip ${tone}`}>{label}</span>
}

function Tabs({ tab, setTab }: { tab: ReviewTab; setTab: (tab: ReviewTab) => void }) {
  return (
    <nav className="review-inner-tabs" aria-label="보류·연기 페이지">
      <button type="button" className={`review-inner-tab ${tab === 'roster' ? 'active' : ''}`}
        aria-current={tab === 'roster' ? 'page' : undefined} onClick={() => setTab('roster')}>
        보류/연기자 명부
      </button>
      <button type="button" className={`review-inner-tab ${tab === 'inbox' ? 'active' : ''}`}
        aria-current={tab === 'inbox' ? 'page' : undefined} onClick={() => setTab('inbox')}>
        검토함
      </button>
    </nav>
  )
}

function ReasonList({ title, items, alert = false }: { title: string; items: string[]; alert?: boolean }) {
  if (!items.length) return null
  return <section className={`review-reasons ${alert ? 'alert' : ''}`}>
    <h3>{title}</h3>
    <ul>{items.map((reason, index) => <li key={index}>{alert ? '! ' : '· '}{reason}</li>)}</ul>
  </section>
}

function PersonDetail({ person, onClose }: { person: Person; onClose: () => void }) {
  return (
    <div className="review-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
      <section className="review-person-modal" role="dialog" aria-modal="true" aria-label={`${person.name} 상세 정보`}>
        <header className="review-person-modal-header">
          <div><p className="review-modal-eyebrow">RESERVIST</p><h2>{person.name}</h2>
            <p className="review-muted">{person.person_id} · {person.occupation ?? '직업 미상'} · {person.branch}</p></div>
          <button type="button" className="review-close" aria-label="상세창 닫기" onClick={onClose}>×</button>
        </header>
        <div className="review-person-modal-body">
          <div className="review-person-summary"><ClassChip label={person.classification} />
            {person.rule_code && <span className="review-muted">{person.rule_code}</span>}
            <span className="review-muted">{person.resource_year}년차 · 동원지정 {person.mobilization_designated ? 'O' : 'X'}</span>
          </div>
          <div className="review-stat-grid">
            {[
              ['동원훈련', person.mobilization],
              ['교육훈련', person.training],
              ['부과 시간', `${person.hours}h${person.makeup_hours ? ` +보충${person.makeup_hours}` : ''}`],
              ['이월', `${person.carryover}h`],
            ].map(([label, value]) => <div className="review-stat" key={label}><small>{label}</small><strong>{value}</strong></div>)}
          </div>
          <ReasonList title="판정 근거" items={person.reasons} />
          <ReasonList title="알람" items={person.alerts} alert />
          {person.documents.length > 0 && <section className="review-person-documents"><h3>제출 서류</h3>
            <div className="review-document-list">{person.documents.map(doc => <div className="review-document-row" key={doc.id}>
              <div><strong>{doc.type}</strong><span className="review-muted">{doc.owner}</span></div>
              <div><span className="review-muted">발급 {doc.issued}</span><span className="review-document-status">{doc.status}</span></div>
            </div>)}</div>
          </section>}
        </div>
      </section>
    </div>
  )
}

function RosterView({ people, onSelect }: { people: Person[]; onSelect: (person: Person) => void }) {
  const [search, setSearch] = useState('')
  const [classification, setClassification] = useState('')
  const [onlyPending, setOnlyPending] = useState(false)
  const filtered = useMemo(() => people.filter(person => {
    const term = search.trim().toLowerCase()
    if (term && !person.name.toLowerCase().includes(term) && !person.person_id.toLowerCase().includes(term)) return false
    if (classification && person.classification !== classification) return false
    if (onlyPending && person.pending_count === 0) return false
    return true
  }), [people, search, classification, onlyPending])

  return <section className="review-roster">
    <div className="review-roster-filters">
      <input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="성명 또는 군번 검색" aria-label="성명 또는 군번 검색" />
      <select value={classification} onChange={event => setClassification(event.target.value)} aria-label="분류">
        <option value="">전체 분류</option>
        {['법규보류', '방침보류', '후순위조정', '연기', '일반'].map(value => <option key={value}>{value}</option>)}
      </select>
      <label><input type="checkbox" checked={onlyPending} onChange={event => setOnlyPending(event.target.checked)} /> 검토 대기만</label>
      <span className="review-roster-total">{filtered.length}명 표시 / 전체 {people.length}명</span>
    </div>
    <div className="review-roster-table-wrap"><table className="review-roster-table"><thead><tr>
      {['군번', '성명', '직업', '연차', '분류', '훈련', '시간', '검토'].map(label => <th key={label}>{label}</th>)}
    </tr></thead><tbody>{filtered.map(person => <tr key={person.person_id} tabIndex={0}
      onClick={() => onSelect(person)} onKeyDown={event => { if (event.key === 'Enter') onSelect(person) }}>
      <td>{person.person_id}</td><td><strong>{person.name}</strong></td><td>{person.occupation ?? '—'}</td>
      <td>{person.resource_year}년차</td><td><ClassChip label={person.classification} /></td>
      <td>{person.training}</td><td>{person.total_hours}h</td>
      <td>{person.pending_count > 0 ? `대기 ${person.pending_count}` : '—'}</td>
    </tr>)}</tbody></table>
      {!filtered.length && <p className="review-empty-state">검색 결과가 없습니다.</p>}
    </div>
  </section>
}

function ReviewPanel({ item, reasons, verifyReasons, onDone }: {
  item: QueueItem
  reasons: Bootstrap['reject_reasons']
  verifyReasons: Bootstrap['verify_reasons']
  onDone: (label: string, changed: boolean, message?: string) => void
}) {
  const [mode, setMode] = useState<'none' | 'reject' | 'verify'>('none')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const runAccept = async () => {
    setBusy(true); setError('')
    try {
      await acceptDocument(item.id, {})
      onDone('승인', item.current_classification !== item.if_accepted_classification)
    } catch (e) { setError(e instanceof Error ? e.message : '승인하지 못했습니다.') }
    finally { setBusy(false) }
  }
  const runReject = async (code: string, message?: string) => {
    setBusy(true); setError('')
    try { await rejectDocument(item.id, code, message); onDone('반려', false, message) }
    catch (e) { setError(e instanceof Error ? e.message : '반려하지 못했습니다.') }
    finally { setBusy(false) }
  }
  const runVerify = async (code: string, message?: string) => {
    setBusy(true); setError('')
    try { await verifyDocument(item.id, code, message); onDone('확인요청', false, message) }
    catch (e) { setError(e instanceof Error ? e.message : '확인을 요청하지 못했습니다.') }
    finally { setBusy(false) }
  }

  return <div className="review-action-body">
    <dl className="review-person-fields">
      <dt>성명</dt><dd>{item.person_name}</dd>
      <dt>군번</dt><dd>{item.person_id}</dd>
      <dt>직업</dt><dd>{item.occupation ?? '—'}</dd>
      <dt>구분</dt><dd>{item.owner}</dd>
      <dt>현재</dt><dd><ClassChip label={item.current_classification} /></dd>
    </dl>
    <div className={`review-verify-notice ${item.verify_number ? 'has-number' : 'no-number'}`}>
      <strong>{item.verify_number ? `문서확인번호 ${item.verify_number}` : '문서확인번호 없음'}</strong>
      <span>{item.verify_number ? '발급처에서 진위를 확인할 수 있습니다.' : '발급처 대조가 불가능합니다. 의심되면 확인요청으로 넘기세요.'}</span>
    </div>
    {item.file_path && <a className="review-document-link" href={item.file_path} target="_blank" rel="noopener noreferrer">원본 서류 열기 ↗</a>}
    <div className="review-actions">
      <button type="button" className="approve" disabled={busy} onClick={runAccept}>승인</button>
      <button type="button" className="reject" disabled={busy} onClick={() => setMode(current => current === 'reject' ? 'none' : 'reject')}>반려</button>
      <button type="button" className="verify" disabled={busy} onClick={() => setMode(current => current === 'verify' ? 'none' : 'verify')}>확인요청</button>
    </div>
    {mode === 'reject' && <div className="review-reason-picker">
      <p>사유를 고르면 안내 문구가 함께 발송됩니다.</p>
      {reasons.map(reason => <button type="button" key={reason.code} disabled={busy || reason.code === 'OTHER'}
        onClick={() => void runReject(reason.code, reason.message)}>
        <span>{reason.label}</span><small>{reason.can_resubmit ? '재제출 가능' : '재제출 불가'}</small>
        {reason.message && <em>{reason.message}</em>}
      </button>)}
      <textarea rows={2} value={note} onChange={event => setNote(event.target.value)} placeholder="기타 사유 설명" aria-label="기타 반려 사유" />
      <button type="button" disabled={busy || !note.trim()} onClick={() => void runReject('OTHER', note)}>기타 사유로 반려</button>
    </div>}
    {mode === 'verify' && <div className="review-reason-picker">
      <p>판단하지 않고 발급기관 확인 대상으로 넘깁니다.</p>
      {verifyReasons.map(reason => <button type="button" key={reason.code} disabled={busy || reason.code === 'OTHER'}
        onClick={() => void runVerify(reason.code)}>{reason.label}</button>)}
    </div>}
    {error && <p role="alert" className="review-action-error">{error}</p>}
  </div>
}

function InboxView({ queue, bootstrap }: { queue: QueueItem[]; bootstrap: Bootstrap }) {
  const [items, setItems] = useState<QueuedRow[]>(() => queue.map(item => ({ ...item, done: null })))
  const [selectedId, setSelectedId] = useState<string | null>(queue[0]?.id ?? null)
  const [search, setSearch] = useState('')
  const [checkedIds, setCheckedIds] = useState<string[]>([])
  const [page, setPage] = useState(1)
  const [showReview, setShowReview] = useState(false)
  const pageSize = 20
  const selected = items.find(item => item.id === selectedId) ?? null
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    return term ? items.filter(item => item.person_name.toLowerCase().includes(term) || item.person_id.toLowerCase().includes(term)) : items
  }, [items, search])
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, pageCount)
  const pageRows = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const allChecked = pageRows.length > 0 && pageRows.every(item => checkedIds.includes(item.id))
  const left = items.filter(item => !item.done).length
  const onDone = (label: string, changed: boolean, message?: string) => {
    if (!selectedId) return
    setItems(prev => prev.map(item => item.id === selectedId ? { ...item, done: label } : item))
    const next = items.find(item => item.id !== selectedId && !item.done)
    window.setTimeout(() => setSelectedId(next?.id ?? null), 700)
    if (message) console.log('발송 안내:', message)
    void changed
  }
  const chooseRow = (id: string) => { setSelectedId(id); setShowReview(true) }

  return <div className="review-inbox-grid">
    <section className="review-list-panel" aria-label="검토 대상자 목록">
      <header className="review-list-title">
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><rect x="2.5" y="3" width="19" height="18" rx="1.5"/><path d="M3 16h5l2 3h4l2-3h5"/></svg>
        <h2>검토 대상자 목록</h2>
      </header>
      <label className="review-search-box">
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"><circle cx="10.8" cy="10.8" r="6.2"/><path d="m15.7 15.7 4.5 4.5"/></svg>
        <input type="search" value={search} onChange={event => { setSearch(event.target.value); setPage(1) }} placeholder="이름,군번을 입력하세요." aria-label="이름, 군번 검색" />
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"><circle cx="10.8" cy="10.8" r="6.2"/><path d="m15.7 15.7 4.5 4.5"/></svg>
      </label>
      <div className="review-list-scroll"><table className="review-list-table">
        <colgroup><col className="review-col-check"/><col className="review-col-number"/><col className="review-col-name"/><col className="review-col-reason"/><col className="review-col-date"/></colgroup>
        <thead><tr>
          <th><input type="checkbox" checked={allChecked} aria-label="현재 페이지 전체 선택" onChange={event => setCheckedIds(prev => event.target.checked ? [...new Set([...prev, ...pageRows.map(item => item.id)])] : prev.filter(id => !pageRows.some(item => item.id === id)))} /></th>
          <th>No.</th><th>이름</th><th>검토 사유</th><th>신청일자</th>
        </tr></thead>
        <tbody>{pageRows.map((item, index) => <tr key={item.id} className={`${selectedId === item.id ? 'selected' : ''} ${item.done ? 'done' : ''}`}
          onClick={() => chooseRow(item.id)} onKeyDown={event => { if (event.key === 'Enter') chooseRow(item.id) }} tabIndex={0} aria-selected={selectedId === item.id}>
          <td><input type="checkbox" checked={checkedIds.includes(item.id)} aria-label={`${item.person_name} 체크`} onClick={event => event.stopPropagation()} onChange={event => setCheckedIds(prev => event.target.checked ? [...new Set([...prev, item.id])] : prev.filter(id => id !== item.id))} /></td>
          <td>{(currentPage - 1) * pageSize + index + 1}</td>
          <td title={`${item.person_name} · ${item.person_id}`}>{item.person_name}</td>
          <td title={reviewReason(item)}>{reviewReason(item)}</td>
          <td title={applicationDate(item)}>{applicationDate(item)}</td>
        </tr>)}</tbody>
      </table>{!pageRows.length && <p className="review-empty-state">{items.length ? '검색 결과가 없습니다.' : '검토 대기 중인 서류가 없습니다.'}</p>}</div>
      <footer className="review-list-footer"><span>전체 {filtered.length}명{checkedIds.length ? ` · 선택 ${checkedIds.length}명` : ''}</span>
        <nav aria-label="검토 목록 페이지"><button type="button" aria-label="이전 페이지" disabled={currentPage === 1} onClick={() => setPage(current => current - 1)}>‹</button>
          <span className="review-page-number">{currentPage}</span>
          <button type="button" aria-label="다음 페이지" disabled={currentPage === pageCount} onClick={() => setPage(current => current + 1)}>›</button></nav>
      </footer>
    </section>
    <section className="review-pdf-panel" aria-label="제출 서류 미리보기">
      <div className="review-pdf-cap" />
      {selected?.file_path ? <iframe key={selected.id} title={`${selected.person_name} 제출 서류`} src={selected.file_path} /> :
        <div className="review-pdf-empty">{selected ? '이 서류에는 PDF 경로가 등록되어 있지 않습니다.' : '왼쪽에서 서류를 선택하세요.'}</div>}
    </section>
    <aside className="review-confirm-panel" aria-label="검토 대상자 확인">
      <button type="button" className="review-confirm-title" aria-expanded={showReview} onClick={() => setShowReview(current => !current)}>
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"><path d="M6 2.5h8l5 5V21H6z"/><path d="M14 2.5V8h5M9 14l2 2 4-5"/></svg>
        <span>검토대상자확인</span><small>{showReview ? '접기' : '펼치기'}</small>
      </button>
      {showReview && (selected ? <ReviewPanel key={selected.id} item={selected} reasons={bootstrap.reject_reasons} verifyReasons={bootstrap.verify_reasons} onDone={onDone} /> :
        <p className="review-empty-state">검토 대기 서류가 없습니다.</p>)}
    </aside>
    <span className="review-visually-hidden" aria-live="polite">검토 대기 {left}건</span>
  </div>
}

export default function ReviewManagement() {
  const [data, setData] = useState<Bootstrap | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<ReviewTab>('inbox')
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null)

  useEffect(() => {
    fetchBootstrap().then(setData).catch((e: unknown) => setError(e instanceof Error ? e.message : '불러오지 못했습니다'))
  }, [])

  if (error) return <div className="review-management review-loading"><div role="alert" className="review-load-error"><strong>데이터를 불러오지 못했습니다</strong><p>{error}</p></div></div>
  if (!data) return <div className="review-management review-loading">불러오는 중…</div>

  return <div className="review-management">
    <Tabs tab={tab} setTab={setTab} />
    <main className="review-main-content">
      {tab === 'roster' ? <RosterView people={data.people} onSelect={setSelectedPerson} /> : <InboxView queue={data.queue} bootstrap={data} />}
    </main>
    {selectedPerson && <PersonDetail person={selectedPerson} onClose={() => setSelectedPerson(null)} />}
  </div>
}
