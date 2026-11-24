import { useCallback, useEffect, useRef, useState } from 'react'
import {
  categoryNames, displayDate, displayTime, displayTimestamp, errorText, WorkLogError,
  workLogPdf, workLogRequest, type WorkLogDetail, type WorkLogEvent, type WorkLogSummary,
} from './api'
import './WorkLogManagement.css'
import WorkLogPreview from './WorkLogPreview'

function detailValue(value: unknown): string {
  if (value == null) return ''
  if (Array.isArray(value)) return value.map(detailValue).filter(Boolean).join(', ')
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${key}: ${detailValue(item)}`).join(' · ')
  return String(value)
}

function EventRows({ events }: { events: WorkLogEvent[] }) {
  return <table className="worklog-events-table">
    <colgroup><col style={{ width: '12%' }} /><col style={{ width: '14%' }} /><col style={{ width: '29%' }} /><col style={{ width: '30%' }} /><col style={{ width: '15%' }} /></colgroup>
    <thead><tr><th>처리 시각</th><th>업무</th><th>처리 내용</th><th>대상자 정보</th><th>처리자</th></tr></thead>
    <tbody>{events.map(event => <tr key={event.id}>
      <td><time dateTime={event.occurred_at}>{displayTime(event.occurred_at)}</time></td>
      <td><span className="worklog-category">{categoryNames[event.category] ?? event.category}</span></td>
      <td><strong>{event.summary}</strong>
        {Object.keys(event.details ?? {}).length > 0 && <details className="worklog-event-details"><summary>상세 내용</summary>
          <dl>{Object.entries(event.details).filter(([, value]) => value != null && value !== '').map(([key, value]) =>
            <div key={key}><dt>{key}</dt><dd>{detailValue(value)}</dd></div>)}</dl>
        </details>}
      </td>
      <td>{event.people.length ? event.people.map((person, index) => <div className="worklog-person" key={`${person.military_number ?? ''}-${index}`}>
        {person.name && <strong>{person.name}</strong>}{person.military_number && <span>{person.military_number}</span>}
        <small>{[person.branch, person.rank, person.unit].filter(Boolean).join(' · ')}</small>
      </div>) : <span className="worklog-muted">—</span>}</td>
      <td>{event.actor}</td>
    </tr>)}</tbody>
  </table>
}

function PdfView({ path, filename }: { path: string; filename: string }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl = ''
    setUrl(''); setError('')
    workLogPdf(path, controller.signal).then(blob => {
      if (controller.signal.aborted) return
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl)
    }).catch(cause => { if (!controller.signal.aborted) setError(errorText(cause)) })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [path])
  return <div className="worklog-pdf-view">
    {error ? <p className="worklog-error" role="alert">{error}</p>
      : !url ? <p className="worklog-message">PDF를 불러오는 중입니다…</p>
        : <><div className="worklog-pdf-actions"><a className="worklog-btn" href={url} download={filename}>PDF 다운로드</a></div>
          <iframe title={filename} className="worklog-pdf" src={url} /></>}
  </div>
}

export default function WorkLogManagement() {
  const [today, setToday] = useState('')
  const [index, setIndex] = useState<WorkLogSummary[]>([])
  const [selectedDate, setSelectedDate] = useState('')
  const [detail, setDetail] = useState<WorkLogDetail | null>(null)
  const [notes, setNotes] = useState('')
  const [expanded, setExpanded] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [view, setView] = useState<'events' | 'pdf' | 'template'>('events')
  const [revision, setRevision] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const notesDirty = useRef(false)
  const selectedRef = useRef(selectedDate)
  selectedRef.current = selectedDate
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])

  const refreshIndex = useCallback(async (signal?: AbortSignal) => {
    const current = await workLogRequest<WorkLogDetail>('/today', { signal })
    const list = await workLogRequest<WorkLogSummary[]>('', { signal })
    if (signal?.aborted || !alive.current) return
    setToday(current.date); setIndex(list)
    setSelectedDate(previous => previous || current.date)
    if (!selectedRef.current) setExpanded([current.date.slice(0, 4), current.date.slice(0, 7)])
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    refreshIndex(controller.signal).catch(cause => { if (!controller.signal.aborted) setError(errorText(cause)) })
    return () => controller.abort()
  }, [refreshIndex, refreshKey])

  useEffect(() => {
    if (!selectedDate) return
    const controller = new AbortController()
    let running = false
    const refresh = async () => {
      if (running || saving) return
      running = true
      try {
        const value = await workLogRequest<WorkLogDetail>(`/${selectedDate}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setDetail(value)
        if (!notesDirty.current) setNotes(value.notes)
        setRevision(previous => previous && value.revisions.some(item => item.revision === previous) ? previous : (value.revisions[0]?.revision ?? null))
        setError('')
        await refreshIndex(controller.signal)
      } catch (cause) { if (!controller.signal.aborted) setError(errorText(cause)) }
      finally { running = false }
    }
    void refresh()
    const timer = window.setInterval(() => { if (!document.hidden) void refresh() }, 8000)
    window.addEventListener('focus', refresh)
    return () => { controller.abort(); window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [selectedDate, refreshKey, saving, refreshIndex])

  useEffect(() => {
    const guard = (event: Event) => {
      if (saving || (notesDirty.current && !window.confirm('저장하지 않은 비고가 있습니다. 이동하시겠습니까?'))) event.preventDefault()
    }
    const unload = (event: BeforeUnloadEvent) => { if (notesDirty.current || saving) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('app-before-page-change', guard)
    window.addEventListener('beforeunload', unload)
    return () => { window.removeEventListener('app-before-page-change', guard); window.removeEventListener('beforeunload', unload) }
  }, [saving])

  const selectDate = (date: string) => {
    if (saving) return
    if (date === selectedDate) { setView('events'); return }
    if (notesDirty.current && !window.confirm('저장하지 않은 비고가 있습니다. 다른 일지를 열겠습니까?')) return
    notesDirty.current = false
    setSelectedDate(date); setDetail(null); setNotes(''); setRevision(null); setView('events'); setError(''); setActionError(''); setMessage('')
    setExpanded(previous => [...new Set([...previous, date.slice(0, 4), date.slice(0, 7)])])
  }
  const confirm = async () => {
    if (!detail || saving) return
    const date = detail.date
    setSaving(true); setActionError(''); setMessage('')
    try {
      const value = await workLogRequest<WorkLogDetail>(`/${date}/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notes, expected_event_id: detail.last_event_id }) })
      if (!alive.current || selectedRef.current !== date) return
      notesDirty.current = false
      setDetail(value); setNotes(value.notes); setRevision(value.revisions[0]?.revision ?? null); setView('pdf')
      setMessage('업무일지 PDF를 저장했습니다.')
      await refreshIndex()
    } catch (cause) {
      if (!alive.current) return
      setActionError(cause instanceof WorkLogError && cause.status === 409
        ? '확인 중 새 업무가 추가되었습니다. 최신 내역을 확인한 뒤 다시 확인해 주세요.' : errorText(cause))
      if (cause instanceof WorkLogError && cause.status === 409) {
        try { const value = await workLogRequest<WorkLogDetail>(`/${date}`); if (alive.current && selectedRef.current === date) setDetail(value) } catch { /* 원래 오류를 유지합니다. */ }
      }
    } finally { if (alive.current) setSaving(false) }
  }

  const dates = index.filter(item => `${item.date} ${displayDate(item.date)}`.includes(search.trim()))
  const years = [...new Set(dates.map(item => item.date.slice(0, 4)))].sort().reverse()
  const toggle = (key: string) => setExpanded(previous => previous.includes(key) ? previous.filter(item => item !== key) : [...previous, key])
  const savedRevision = detail?.revisions.find(item => item.revision === revision)
  const changed = !!detail && (!detail.revisions.length || detail.has_unconfirmed_changes || notes !== detail.notes)

  return <section className="worklog">
    <header className="worklog-heading"><div><h1>일일 업무일지</h1><p>처리한 업무를 확인하고 PDF 기록으로 보관합니다.</p></div>
      <div className="worklog-heading-actions"><button type="button" className="worklog-btn" disabled={!today || saving} onClick={() => selectDate(today)}>오늘 업무</button>
        <button type="button" className="worklog-btn" disabled={saving} onClick={() => setRefreshKey(value => value + 1)}>새로고침</button>
        <button type="button" className="worklog-btn" onClick={() => setView('template')}>원본 양식</button></div>
    </header>
    {error && <div className="worklog-error" role="alert">{error}</div>}
    {actionError && <div className="worklog-error" role="alert">{actionError}</div>}
    {message && <div className="worklog-success" role="status">{message}</div>}
    <div className="worklog-layout">
      <aside className="worklog-explorer" aria-label="업무일지 탐색기"><div className="worklog-search"><input type="search" aria-label="업무일지 날짜 검색" placeholder="날짜 검색 (YYYY-MM-DD)" value={search} onChange={event => setSearch(event.target.value)} /></div>
        <nav className="worklog-tree" aria-label="연도 및 월">{years.map(year => <div key={year}>
          <button type="button" className="worklog-tree-row worklog-tree-year" onClick={() => toggle(year)} aria-expanded={expanded.includes(year)}><span>{year}년</span><span>{expanded.includes(year) ? '▲' : '▼'}</span></button>
          {expanded.includes(year) && [...new Set(dates.filter(item => item.date.startsWith(year)).map(item => item.date.slice(0, 7)))].sort().reverse().map(month => <div key={month} className="worklog-month-group">
            <button type="button" className="worklog-tree-row worklog-tree-month" onClick={() => toggle(month)} aria-expanded={expanded.includes(month)}><span>{Number(month.slice(5))}월</span><span>{expanded.includes(month) ? '▲' : '▼'}</span></button>
            {expanded.includes(month) && <div className="worklog-month-entries">{dates.filter(item => item.date.startsWith(month)).sort((a, b) => b.date.localeCompare(a.date)).map(item => <button type="button" key={item.date} disabled={saving}
              className={`worklog-tree-file ${selectedDate === item.date ? 'is-selected' : ''}`} aria-current={selectedDate === item.date ? 'page' : undefined} onClick={() => selectDate(item.date)}>
              <span className="worklog-file-icon" aria-hidden="true" /><span><strong>{displayDate(item.date)}{item.date === today ? ' · 오늘' : ''}</strong><small>{item.event_count}건 · {item.has_unconfirmed_changes ? '확인 대기' : 'PDF 저장됨'}</small></span>
            </button>)}</div>}
          </div>)}
        </div>)}{!years.length && <p className="worklog-message">{search ? '검색 결과가 없습니다.' : '목록을 불러오는 중입니다…'}</p>}</nav>
        <p className="worklog-explorer-note">업무 기록과 저장한 PDF는 재실행 후에도 보관됩니다.</p>
      </aside>
      <main className="worklog-content" aria-busy={saving || (!detail && !error)}>
        <div className="worklog-content-head"><h2>{selectedDate ? `${displayDate(selectedDate)} 업무일지` : '업무일지'}</h2><span className="worklog-count">총 {detail?.events.length ?? 0}건</span></div>
        {!detail ? <p className="worklog-message">{error ? '업무일지를 불러오지 못했습니다. 새로고침해 주세요.' : '업무일지를 불러오는 중입니다…'}</p>
              : <><div className="worklog-events-scroll"><EventRows events={detail.events} />{!detail.events.length && <p className="worklog-message">아직 처리한 업무가 없습니다. 업무가 완료되면 자동으로 기록됩니다.</p>}</div>
                <div className="worklog-confirm"><label htmlFor="worklog-notes">비고</label><textarea id="worklog-notes" maxLength={20000} rows={3} value={notes} disabled={saving}
                  onChange={event => { notesDirty.current = event.target.value !== detail.notes; setNotes(event.target.value) }} placeholder="추가로 기록할 내용을 입력하세요." />
                  <div><span>{detail.revisions.length ? `저장한 PDF ${detail.revisions.length}개${changed ? ' · 추가 확인 필요' : ''}` : '확인하면 업무 내역과 비고를 PDF로 저장합니다.'}</span>
                    <button type="button" className="worklog-btn worklog-btn--primary" disabled={saving || !changed} onClick={() => void confirm()}>{saving ? 'PDF 저장 중…' : '확인'}</button></div>
                </div></>}
      </main>
      <aside className="worklog-preview-pane" aria-label="업무일지 PDF">
        <div className="worklog-content-head"><h2>{view === 'template' ? '원본 양식' : view === 'pdf' ? '저장한 PDF' : 'PDF 미리보기'}</h2></div>
        <div className="worklog-document-toolbar"><div className="worklog-view-tabs">
          <button type="button" className={view === 'events' ? 'is-active' : ''} onClick={() => setView('events')}>현재 작성본</button>
          <button type="button" className={view === 'pdf' ? 'is-active' : ''} disabled={!detail?.revisions.length} onClick={() => setView('pdf')}>저장한 PDF</button>
        </div></div>
        {view === 'template' ? <PdfView path="/template" filename="일일 업무일지 양식.pdf" />
          : !detail ? <p className="worklog-message">{error ? '업무일지를 불러오지 못했습니다.' : '업무일지를 불러오는 중입니다…'}</p>
            : view === 'pdf' && savedRevision ? <>
              <div className="worklog-document-toolbar"><select aria-label="저장한 업무일지 버전" value={revision ?? ''} onChange={event => setRevision(Number(event.target.value))}>
                {detail.revisions.map(item => <option key={item.revision} value={item.revision}>{item.revision}차 · {displayTimestamp(item.confirmed_at)} · {item.event_count}건</option>)}
              </select></div>
              <p className="worklog-saved-note">{displayTimestamp(savedRevision.confirmed_at)} 확인 · {savedRevision.event_count}건{detail.has_unconfirmed_changes ? ' · 추가 업무 확인 필요' : ''}</p>
              <PdfView path={`/${detail.date}/revisions/${savedRevision.revision}/pdf`} filename={`${detail.date}_업무일지_${savedRevision.revision}차.pdf`} />
            </> : <WorkLogPreview key={detail.date} date={detail.date} notes={notes} eventId={detail.last_event_id} refreshKey={refreshKey} />}
      </aside>
    </div>
  </section>
}
