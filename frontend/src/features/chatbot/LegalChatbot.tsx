import { Fragment, useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent, ReactNode } from 'react'
import './LegalChatbot.css'

// 예비군 법령 RAG 서버 (backend/RAG, 기본 포트 8004). vite.config.ts의 /rag-api 프록시를 거칩니다.
const RAG_API_BASE = import.meta.env.VITE_RAG_API_BASE_URL ?? '/rag-api'

const EXAMPLES = [
  '예비군 훈련은 1년에 최대 며칠까지 받을 수 있나요?',
  '훈련 소집에 응하지 않으면 처벌이 있나요?',
  '예비군 훈련 때문에 회사에서 불이익을 받으면 어떻게 하나요?',
  '예비군법 시행령 제14조 내용 알려줘',
]

type Hit = {
  id: string
  title: string
  law_type: string
  promulgation_no: string
  effective_date: string
  status: string
  chapter: string | null
  text: string
  via: string
}

type RagStatus = { ready: boolean; error: string | null; llm?: string | null; articles?: number; reference_date?: string }

type Message =
  | { id: number; role: 'user'; text: string }
  | { id: number; role: 'assistant'; text: string; hits: Hit[]; phase: 'searching' | 'writing' | 'done'; error?: string }

type StreamEvent =
  | { type: 'hits'; hits: Hit[] }
  | { type: 'token'; text: string }
  | { type: 'error'; text: string }

let nextMessageId = 1

// LLM 답변용 최소 마크다운: **굵게**, "- " 목록, 문단, ※ 안내문
function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*.+?\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <Fragment key={i}>{part}</Fragment>)
}

function renderAnswer(text: string): ReactNode[] {
  const blocks: ReactNode[] = []
  let list: string[] = []
  const flush = () => {
    if (list.length) blocks.push(<ul key={blocks.length}>{list.map((item, i) => <li key={i}>{renderInline(item)}</li>)}</ul>)
    list = []
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (/^[-*•]\s+/.test(line)) { list.push(line.replace(/^[-*•]\s+/, '')); continue }
    flush()
    if (!line) continue
    if (line.startsWith('※')) blocks.push(<p key={blocks.length} className="legal-chat-disclaimer">{renderInline(line)}</p>)
    else blocks.push(<p key={blocks.length}>{renderInline(line.replace(/^#+\s*/, ''))}</p>)
  }
  flush()
  return blocks
}

function HitList({ hits }: { hits: Hit[] }) {
  return <details className="legal-chat-hits">
    <summary>근거 조문 {hits.length}건</summary>
    {hits.map(hit => <details key={hit.id} className="legal-chat-hit">
      <summary>
        <span>{hit.title}</span>
        {hit.status === '시행 예정' && <em className="is-upcoming">시행 예정 {hit.effective_date}</em>}
        {hit.via !== '검색' && <em>{hit.via}</em>}
      </summary>
      <div className="legal-chat-hit-meta">{hit.law_type} {hit.promulgation_no} · 시행 {hit.effective_date}{hit.chapter ? ` · ${hit.chapter}` : ''}</div>
      <div className="legal-chat-hit-body">{hit.text}</div>
    </details>)}
  </details>
}

export default function LegalChatbot({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [status, setStatus] = useState<RagStatus | null>(null)
  const [statusError, setStatusError] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // 패널이 열려 있는 동안 모델 로딩이 끝날 때까지 상태를 확인합니다.
  const ready = status?.ready === true
  useEffect(() => {
    if (!open || ready) return
    let cancelled = false
    let timer: number | undefined
    const check = async () => {
      try {
        const response = await fetch(`${RAG_API_BASE}/api/status`, { cache: 'no-store' })
        if (!response.ok) throw new Error(response.statusText)
        const next = await response.json() as RagStatus
        if (cancelled) return
        setStatus(next)
        setStatusError(false)
        if (!next.ready && !next.error) timer = window.setTimeout(check, 2000)
      } catch {
        if (cancelled) return
        setStatusError(true)
        timer = window.setTimeout(check, 3000)
      }
    }
    check()
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [open, ready])

  useEffect(() => () => abortRef.current?.abort(), [])

  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages])

  const updateAssistant = (id: number, update: (message: Extract<Message, { role: 'assistant' }>) => Partial<Extract<Message, { role: 'assistant' }>>) =>
    setMessages(current => current.map(message => message.id === id && message.role === 'assistant' ? { ...message, ...update(message) } : message))

  const ask = async (question: string) => {
    if (!question || busy || !ready) return
    const answerId = nextMessageId + 1
    nextMessageId += 2
    setMessages(current => [...current,
      { id: answerId - 1, role: 'user', text: question },
      { id: answerId, role: 'assistant', text: '', hits: [], phase: 'searching' }])
    setDraft('')
    setBusy(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const response = await fetch(`${RAG_API_BASE}/api/ask/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      })
      if (!response.ok || !response.body) {
        const detail = await response.json().then(body => body.detail as string).catch(() => response.statusText)
        throw new Error(detail || `HTTP ${response.status}`)
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let newline: number
        while ((newline = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, newline).trim()
          buffer = buffer.slice(newline + 1)
          if (!line) continue
          const event = JSON.parse(line) as StreamEvent
          if (event.type === 'hits') updateAssistant(answerId, () => ({ hits: event.hits, phase: 'writing' }))
          else if (event.type === 'token') updateAssistant(answerId, message => ({ text: message.text + event.text }))
          else updateAssistant(answerId, () => ({ error: event.text }))
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) updateAssistant(answerId, () => ({ error: `오류: ${error instanceof Error ? error.message : String(error)}` }))
    } finally {
      updateAssistant(answerId, () => ({ phase: 'done' }))
      if (abortRef.current === controller) abortRef.current = null
      setBusy(false)
    }
  }

  const submit = (event: FormEvent) => { event.preventDefault(); ask(draft.trim()) }
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중 Enter는 무시해야 마지막 글자가 중복 전송되지 않습니다.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); ask(draft.trim()) }
  }

  const statusText = statusError ? '법령 챗봇 서버에 연결할 수 없습니다. (backend/RAG 실행 확인)'
    : !status ? '연결 중…'
    : status.error ? `로드 실패: ${status.error}`
    : !status.ready ? '모델을 불러오는 중… (처음 실행 시 1~2분)'
    : `${status.articles}개 조문 · 기준일 ${status.reference_date} · ${status.llm ? `LLM ${status.llm}` : 'LLM 없음 (조문 검색만)'}`

  return <aside className="legal-chat" aria-label="예비군 법령 챗봇" hidden={!open}>
    <header className="legal-chat-header">
      <div>
        <h2>예비군 법령 챗봇</h2>
        <p className={statusError || status?.error ? 'is-error' : undefined}>{statusText}</p>
      </div>
      <div className="legal-chat-header-actions">
        {messages.length > 0 && <button type="button" onClick={() => { abortRef.current?.abort(); setMessages([]) }}>새 대화</button>}
        <button type="button" onClick={onClose} aria-label="챗봇 닫기" title="닫기">✕</button>
      </div>
    </header>

    <div className="legal-chat-log" ref={logRef} aria-live="polite">
      {messages.length === 0 && <div className="legal-chat-empty">
        <p>예비군법·시행령·시행규칙 등 법령 조문을 근거로 답변합니다. 질문마다 독립적으로 답변하므로 필요한 내용을 한 번에 적어 주세요.</p>
        {EXAMPLES.map(example => <button key={example} type="button" disabled={!ready || busy} onClick={() => ask(example)}>{example}</button>)}
      </div>}
      {messages.map(message => message.role === 'user'
        ? <div key={message.id} className="legal-chat-bubble is-user">{message.text}</div>
        : <div key={message.id} className="legal-chat-bubble is-assistant">
          {message.text && renderAnswer(message.text)}
          {message.error && <p className="is-error">{message.error}</p>}
          {message.phase !== 'done' && !message.text && <p className="legal-chat-pending">{message.phase === 'searching' ? '조문 검색 중…' : '답변 작성 중…'}</p>}
          {message.hits.length > 0 && <HitList hits={message.hits} />}
        </div>)}
    </div>

    <form className="legal-chat-form" onSubmit={submit}>
      <textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={onKeyDown} rows={3} maxLength={2000}
        placeholder={ready ? '질문을 입력하세요 (Shift+Enter 줄바꿈)' : '챗봇 준비 중…'} disabled={!ready} aria-label="질문" />
      <button type="submit" disabled={!ready || busy || !draft.trim()}>{busy ? '답변 중' : '질문'}</button>
    </form>
  </aside>
}
