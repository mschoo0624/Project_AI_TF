import { useEffect, useRef, useState } from 'react'
import { documentTime, errorMessage, prosecutionRequest } from './api'
import type { SavedDocumentSummary } from './types'

export default function ProsecutionSavedDocuments({ onClose, onOpen, onPrint }: {
  onClose: () => void; onOpen: (id: string) => Promise<void>; onPrint: (id: string) => Promise<void>
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [items, setItems] = useState<SavedDocumentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => { dialog.current?.showModal() }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    prosecutionRequest<SavedDocumentSummary[]>('/prosecution-documents', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setItems(data) })
      .catch(cause => { if (!controller.signal.aborted) setError(errorMessage(cause)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [revision])
  const act = async (action: (id: string) => Promise<void>, id: string) => {
    setBusy(true); setError('')
    try { await action(id) } catch (cause) { setError(errorMessage(cause)) } finally { setBusy(false) }
  }
  const filtered = items.filter(item => `${item.name} ${item.person_id} ${item.document_number}`.includes(query.trim()))
  return <dialog ref={dialog} className="prosecution-modal prosecution-saved-dialog" aria-labelledby="prosecution-saved-title"
    onCancel={event => { event.preventDefault(); if (!busy) onClose() }}>
    <header><h2 id="prosecution-saved-title">저장된 고발장</h2><button type="button" disabled={busy} onClick={onClose}>닫기</button></header>
    <div className="prosecution-saved-search"><input aria-label="저장된 고발장 검색" placeholder="성명, 군번, 문서번호 검색" value={query} onChange={event => setQuery(event.target.value)} /><button type="button" disabled={loading || busy} onClick={() => setRevision(value => value + 1)}>새로고침</button></div>
    {error && <p role="alert" className="rm-org-error">{error}</p>}
    <div className="prosecution-saved-table">
      {loading ? <p>저장된 고발장을 불러오는 중…</p> : <table><thead><tr><th>성명 / 군번</th><th>문서번호</th><th>최종 저장 (한국시간)</th><th>작업</th></tr></thead><tbody>
        {filtered.map(item => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.person_id}</small></td><td>{item.document_number}</td><td>{documentTime(item.updated_at)}</td><td><button type="button" disabled={busy} onClick={() => void act(onOpen, item.id)}>열기</button><button type="button" disabled={busy} onClick={() => void act(onPrint, item.id)}>인쇄</button></td></tr>)}
        {!filtered.length && <tr><td colSpan={4}>{query ? '검색 결과가 없습니다.' : '저장된 고발장이 없습니다.'}</td></tr>}
      </tbody></table>}
    </div>
  </dialog>
}
