import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import Mascot from './Mascot'
import { useStickToBottom } from './useStickToBottom'

// 업무 Copilot (main app /copilot/chat). Copilot은 조회·제안만 하고,
// 저장은 제안 카드의 [승인]을 눌렀을 때 이 화면이 기존 API를 직접 호출합니다.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

const EXAMPLES = [
  '오늘 현황',
  '미편성 인원들 편성해줘',
  '0년차 편성된 사람 빼줘',
  '교육 미달자 보여줘',
  '이상 데이터 점검해줘',
  '최근 변경 기록',
]

export type CopilotAction = {
  type: 'navigate' | 'filter' | 'highlight'
  tab: string
  subtab: 'people' | 'transfers' | null
  label: string | null
  ids: string[]
}

type SquadOption = { squad_id: number; squad_name: string; current_count: number; reason: string }
type PlannedAssignment = { person_id: string; name: string; squad_id: number; squad_name: string }
type Proposal = {
  kind: 'assign_squad' | 'assign_bulk' | 'release' | 'move'
  title: string
  person_id: string | null
  options: SquadOption[]
  assignments: PlannedAssignment[]
  notes: string[]
}
type ChatResponse = {
  message: string
  ui_actions: CopilotAction[]
  proposal: Proposal | null
  conditions: string[]
  unparsed: string[]
  trace_id: string
  conversation_id: string | null
}
type ApplyResponse = { message: string }
// expired: 다시 연 대화에서 승인하지 않았던 카드. 그사이 데이터가 바뀌었을 수 있어 다시 요청하게 합니다.
type ProposalState = {
  status: 'open' | 'saving' | 'approved' | 'cancelled' | 'expired'
  selected: number
  error?: string
  done?: ApplyResponse
  doneAt?: string
  undo?: UndoState
}
type UndoSkip = { person_id: string; name: string; reason: string }
type UndoPreview = { steps: { person_id: string; name: string; now: string; after: string }[]; skipped: UndoSkip[] }
// 되돌리기: [되돌리기] → 미리 보기(loading → preview) → [확인] → saving → done
type UndoState = {
  status: 'loading' | 'preview' | 'saving' | 'done'
  preview?: UndoPreview
  error?: string
  message?: string
  at?: string
  skipped?: UndoSkip[]
}
type ConversationSummary = { id: string; title: string; updated_at: string; changes: number; undone: number }
type ConversationDetail = {
  id: string
  title: string
  messages: {
    question: string; response: ChatResponse; created_at: string
    applied_at: string | null; applied_summary: string | null; undone_at: string | null; undone_summary: string | null
  }[]
}

type Message =
  | { id: number; role: 'user'; text: string }
  | {
    id: number; role: 'assistant'; text: string; pending: boolean; error?: string
    proposal?: Proposal; proposalState?: ProposalState; traceId?: string
    conditions?: string[]; unparsed?: string[]
  }

// 로그인이 생기기 전까지 대화는 브라우저별 무작위 ID로 구분합니다. 저장소를 못 쓰면 이 창에서만 유지됩니다.
const CLIENT_KEY = 'copilot-client-id'
const CONVERSATION_KEY = 'copilot-conversation-id'

function readStorage(key: string) {
  try { return window.localStorage.getItem(key) } catch { return null }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch { /* 저장소를 못 쓰면 새로고침 때 대화가 이어지지 않을 뿐입니다. */ }
}

let memoryClientId: string | null = null
function clientId() {
  const saved = readStorage(CLIENT_KEY) ?? memoryClientId
  if (saved) return saved
  // crypto.randomUUID는 https에서만 되므로, 내부망 http에서도 되는 getRandomValues를 씁니다.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  const created = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  memoryClientId = created
  writeStorage(CLIENT_KEY, created)
  return created
}

function dayGroup(iso: string) {
  const day = new Date(iso)
  const today = new Date()
  const startOf = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const days = Math.round((startOf(today) - startOf(day)) / 86_400_000)
  if (days <= 0) return '오늘'
  if (days === 1) return '어제'
  if (days < 7) return '지난 7일'
  return '이전'
}

const formatTime = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })

// 답변의 명단: "저 인원들 편성해줘"가 가리키는 대상
function listOf(result: ChatResponse) {
  const action = [...result.ui_actions].reverse().find(item => item.type !== 'navigate' && item.ids.length > 0)
  return action ? { label: action.label ?? action.ids.join(', '), ids: action.ids } : null
}

async function errorDetail(response: Response) {
  try {
    const body = await response.json() as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
  } catch {
    return `HTTP ${response.status}`
  }
}

// 없거나 다른 브라우저의 대화면 null
async function fetchConversation(id: string) {
  const response = await fetch(`${API_BASE}/copilot/conversations/${encodeURIComponent(id)}?client_id=${clientId()}`)
  if (response.status === 404) return null
  if (!response.ok) throw new Error(await errorDetail(response))
  return await response.json() as ConversationDetail
}

// 분대를 하나 고르는 카드: 한 사람 편성, 재편성(이동)
const picksOneSquad = (proposal: Proposal) => proposal.kind === 'assign_squad' || proposal.kind === 'move'

// 승인 시 보낼 내용: 편성·재편성은 (인원, 분대) 목록, 해제는 인원 목록
function applyBody(proposal: Proposal, state: ProposalState, traceId?: string) {
  const assignments = picksOneSquad(proposal)
    ? [{ person_id: proposal.person_id!, squad_id: state.selected }]
    : proposal.kind === 'assign_bulk' ? proposal.assignments.map(item => ({ person_id: item.person_id, squad_id: item.squad_id })) : []
  return {
    kind: proposal.kind,
    trace_id: traceId ?? null,
    assignments,
    person_ids: proposal.kind === 'release' ? proposal.assignments.map(item => item.person_id) : [],
  }
}

function approveLabel(proposal: Proposal) {
  if (proposal.kind === 'assign_bulk') return `${proposal.assignments.length}명 승인`
  if (proposal.kind === 'release') return `${proposal.assignments.length}명 해제`
  if (proposal.kind === 'move') return '옮기기 승인'
  return '승인'
}

function BulkPlan({ proposal }: { proposal: Proposal }) {
  const bySquad = new Map<string, PlannedAssignment[]>()
  proposal.assignments.forEach(item => bySquad.set(item.squad_name, [...(bySquad.get(item.squad_name) ?? []), item]))
  return <div className="copilot-bulk">
    {[...bySquad.entries()].map(([squad, items]) => <details key={squad}>
      <summary>{squad} <small>{proposal.kind === 'release' ? '-' : '+'}{items.length}명</small></summary>
      <p>{items.map(item => `${item.name}(${item.person_id})`).join(', ')}</p>
    </details>)}
    {proposal.notes.map(note => <p key={note} className="copilot-bulk-note">{note}</p>)}
  </div>
}

function SkippedList({ skipped }: { skipped: UndoSkip[] }) {
  if (!skipped.length) return null
  return <details className="copilot-undo-skipped">
    <summary>그대로 두는 인원 {skipped.length}명</summary>
    <ul>{skipped.map(item => <li key={item.person_id}>{item.name}({item.person_id}): {item.reason}</li>)}</ul>
  </details>
}

// 승인한 카드 아래: [되돌리기] → 무엇이 바뀌는지 미리 보여 주고 확인을 받은 뒤에만 실행합니다.
function UndoBox({ undo, onStart, onConfirm, onClose }: {
  undo?: UndoState
  onStart: () => void
  onConfirm: () => void
  onClose: () => void
}) {
  if (!undo) return <div className="copilot-proposal-actions">
    <button type="button" onClick={onStart}>↩ 되돌리기</button>
  </div>
  if (undo.status === 'done') return <div className="copilot-undo is-done">
    <p>↩ 되돌림{undo.at && <small> · {formatTime(undo.at)}</small>}</p>
    {undo.message && <p>{undo.message}</p>}
    <SkippedList skipped={undo.skipped ?? []} />
  </div>
  if (undo.status === 'loading') return <p className="copilot-undo">되돌릴 내용을 확인하는 중…</p>
  const steps = undo.preview?.steps ?? []
  return <div className="copilot-undo">
    {undo.error && <p className="is-error">{undo.error}</p>}
    {steps.length > 0 ? <>
      <p><b>되돌리면 {steps.length}명이 이렇게 바뀌어요.</b></p>
      <ul className="copilot-undo-steps">
        {steps.map(step => <li key={step.person_id}>{step.name}({step.person_id}) <small>{step.now} → {step.after}</small></li>)}
      </ul>
    </> : <p><b>되돌릴 수 있는 인원이 없어요.</b> 모두 이후에 다시 바뀌었거나 원래 자리로 돌아갈 수 없어요.</p>}
    <SkippedList skipped={undo.preview?.skipped ?? []} />
    <div className="copilot-proposal-actions">
      <button type="button" onClick={onClose} disabled={undo.status === 'saving'}>{steps.length ? '취소' : '닫기'}</button>
      {steps.length > 0 && <button type="button" className="is-primary" onClick={onConfirm} disabled={undo.status === 'saving'}>
        {undo.status === 'saving' ? '되돌리는 중…' : `${steps.length}명 되돌리기`}
      </button>}
    </div>
  </div>
}

function ProposalCard({ proposal, state, onSelect, onApprove, onCancel, onUndoStart, onUndoConfirm, onUndoClose }: {
  proposal: Proposal
  state: ProposalState
  onSelect: (squadId: number) => void
  onApprove: () => void
  onCancel: () => void
  onUndoStart: () => void
  onUndoConfirm: () => void
  onUndoClose: () => void
}) {
  const chosen = proposal.options.find(option => option.squad_id === state.selected)
  // 다시 연 대화에서는 어느 분대를 골랐는지 모르므로 서버가 저장한 결과 문장을 씁니다.
  const doneText = chosen && proposal.kind === 'assign_squad' ? `${chosen.squad_name}에 편성했습니다.`
    : chosen && proposal.kind === 'move' ? `${chosen.squad_name}(으)로 옮겼습니다.` : state.done?.message
  return <div className="copilot-proposal">
    <strong>{proposal.title}</strong>
    {!picksOneSquad(proposal) ? <BulkPlan proposal={proposal} /> : <fieldset disabled={state.status !== 'open'}>
      <legend hidden>편성할 분대</legend>
      {proposal.options.map((option, index) => <label key={option.squad_id}>
        <input type="radio" name={`proposal-${proposal.person_id}`} checked={state.selected === option.squad_id}
          onChange={() => onSelect(option.squad_id)} />
        <span>{index === 0 && <em>추천</em>}{option.squad_name} <small>현재 {option.current_count}명 · {option.reason}</small></span>
      </label>)}
    </fieldset>}
    {state.error && <p className="is-error">{state.error}</p>}
    {state.status === 'approved' && <p className="copilot-proposal-done">
      ✓ {doneText}{state.doneAt && <small> · {formatTime(state.doneAt)}</small>}
    </p>}
    {state.status === 'approved' && <UndoBox undo={state.undo} onStart={onUndoStart} onConfirm={onUndoConfirm} onClose={onUndoClose} />}
    {state.status === 'cancelled' && <p className="copilot-proposal-done">취소했습니다. 변경된 내용은 없습니다.</p>}
    {state.status === 'expired' && <p className="copilot-proposal-done">승인하지 않은 제안이에요. 지금 데이터로 다시 요청해 주세요.</p>}
    {(state.status === 'open' || state.status === 'saving') && <div className="copilot-proposal-actions">
      <button type="button" onClick={onCancel} disabled={state.status === 'saving'}>취소</button>
      <button type="button" className="is-primary" onClick={onApprove} disabled={state.status === 'saving'}>
        {state.status === 'saving' ? '저장 중…' : approveLabel(proposal)}
      </button>
    </div>}
  </div>
}

function HistoryPanel({ items, error, currentId, onOpen, onClose }: {
  items: ConversationSummary[] | null
  error: string | null
  currentId: string | null
  onOpen: (id: string) => void
  onClose: () => void
}) {
  const groups = new Map<string, ConversationSummary[]>()
  items?.forEach(item => groups.set(dayGroup(item.updated_at), [...(groups.get(dayGroup(item.updated_at)) ?? []), item]))
  return <div className="copilot-history" role="dialog" aria-label="지난 대화">
    <div className="copilot-history-head">
      <strong>지난 대화</strong>
      <button type="button" onClick={onClose} aria-label="지난 대화 닫기">✕</button>
    </div>
    {error && <p className="is-error">{error}</p>}
    {!error && items === null && <p className="copilot-history-empty">불러오는 중…</p>}
    {items?.length === 0 && <p className="copilot-history-empty">아직 대화가 없어요.</p>}
    {[...groups.entries()].map(([group, conversations]) => <section key={group}>
      <h4>{group}</h4>
      {conversations.map(item => <button key={item.id} type="button" onClick={() => onOpen(item.id)}
        aria-current={item.id === currentId ? 'true' : undefined} title={formatTime(item.updated_at)}>
        <span>{item.title}</span>
        {item.changes > 0 && <em title="승인해서 데이터를 바꾼 횟수">변경 {item.changes}건</em>}
        {item.undone > 0 && <em className="is-undone" title="되돌린 횟수">되돌림 {item.undone}</em>}
      </button>)}
    </section>)}
    <p className="copilot-history-note">대화는 이 브라우저에만 보이고, 90일 뒤 지워져요. 데이터 변경은 변경 기록에 계속 남아요.</p>
  </div>
}

export default function CopilotChat({ onAction, onDataChanged }: {
  onAction: (action: CopilotAction) => void
  onDataChanged: () => void
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const nextMessageId = useRef(1)
  // 직전 답변이 보여준 명단. "저 인원들 편성해줘"가 이 명단을 가리킵니다.
  const lastList = useRef<{ label: string; ids: string[] } | null>(null)
  // 지금 대화. 새로고침하거나 법령 탭에 다녀와도 이어서 보이도록 브라우저에 기억합니다.
  const [conversationId, setConversationId] = useState<string | null>(() => readStorage(CONVERSATION_KEY))
  const [title, setTitle] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyItems, setHistoryItems] = useState<ConversationSummary[] | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)

  const { ref: logRef, onScroll: onLogScroll, follow: followLog } = useStickToBottom(messages)

  const remember = (id: string | null) => {
    setConversationId(id)
    writeStorage(CONVERSATION_KEY, id)
  }

  const reset = () => {
    remember(null)
    setTitle(null)
    setMessages([])
    lastList.current = null
    setHistoryOpen(false)
  }
  const startNew = () => { if (!busy) reset() }

  // 저장된 대화를 화면 메시지로 바꿉니다. 화면 이동(ui_actions)은 다시 실행하지 않습니다.
  const show = (detail: ConversationDetail) => {
    const restored: Message[] = detail.messages.flatMap(item => {
      const userId = nextMessageId.current
      nextMessageId.current += 2
      const result = item.response
      const proposalState: ProposalState | undefined = result.proposal ? item.applied_at
        ? {
          status: 'approved', selected: 0, done: { message: item.applied_summary ?? '승인했습니다.' }, doneAt: item.applied_at,
          undo: item.undone_at ? { status: 'done', at: item.undone_at, message: item.undone_summary ?? undefined } : undefined,
        }
        : { status: 'expired', selected: 0 } : undefined
      return [
        { id: userId, role: 'user', text: item.question },
        {
          id: userId + 1, role: 'assistant', text: result.message, pending: false, traceId: result.trace_id,
          proposal: result.proposal ?? undefined, proposalState, conditions: result.conditions, unparsed: result.unparsed,
        },
      ]
    })
    const last = detail.messages.at(-1)
    lastList.current = last ? listOf(last.response) : null
    remember(detail.id)
    setTitle(detail.title)
    followLog()
    setMessages(restored)
  }

  const open = async (id: string) => {
    if (busy) return
    setHistoryOpen(false)
    setBusy(true)
    try {
      const detail = await fetchConversation(id)
      if (detail) show(detail)
      else reset()  // 90일이 지나 지워진 대화
    } catch (error) {
      setHistoryError(`대화를 열지 못했어요: ${error instanceof Error ? error.message : String(error)}`)
      setHistoryOpen(true)
    } finally {
      setBusy(false)
    }
  }

  const showHistory = async () => {
    setHistoryOpen(true)
    setHistoryItems(null)
    setHistoryError(null)
    try {
      const response = await fetch(`${API_BASE}/copilot/conversations?client_id=${clientId()}`)
      if (!response.ok) throw new Error(await errorDetail(response))
      setHistoryItems(await response.json() as ConversationSummary[])
    } catch (error) {
      setHistoryError(`목록을 불러오지 못했어요: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  // 처음 열 때 지난번 대화를 이어서 보여 줍니다.
  useEffect(() => {
    const saved = readStorage(CONVERSATION_KEY)
    if (!saved) return
    let cancelled = false
    fetchConversation(saved)
      .then(detail => { if (!cancelled) { if (detail) show(detail); else reset() } })
      .catch(() => { /* 서버가 꺼져 있으면 빈 화면에서 시작합니다. 다음 질문이 대화를 이어 갑니다. */ })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const updateAssistant = (id: number, update: Partial<Extract<Message, { role: 'assistant' }>>) =>
    setMessages(current => current.map(message => message.id === id && message.role === 'assistant' ? { ...message, ...update } : message))
  const updateProposal = (id: number, update: Partial<ProposalState>) =>
    setMessages(current => current.map(message => message.id === id && message.role === 'assistant' && message.proposalState
      ? { ...message, proposalState: { ...message.proposalState, ...update } } : message))

  const ask = async (question: string) => {
    if (!question || busy) return
    const answerId = nextMessageId.current + 1
    nextMessageId.current += 2
    followLog()
    setMessages(current => [...current,
      { id: answerId - 1, role: 'user', text: question },
      { id: answerId, role: 'assistant', text: '', pending: true }])
    setDraft('')
    setBusy(true)
    try {
      const response = await fetch(`${API_BASE}/copilot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, context: lastList.current, client_id: clientId(), conversation_id: conversationId }),
      })
      if (!response.ok) throw new Error(await errorDetail(response))
      const result = await response.json() as ChatResponse
      if (result.conversation_id && result.conversation_id !== conversationId) {
        remember(result.conversation_id)
        setTitle(question)
      }
      updateAssistant(answerId, {
        text: result.message,
        pending: false,
        proposal: result.proposal ?? undefined,
        traceId: result.trace_id,
        conditions: result.conditions,
        unparsed: result.unparsed,
        proposalState: result.proposal ? { status: 'open', selected: result.proposal.options[0]?.squad_id ?? 0 } : undefined,
      })
      lastList.current = listOf(result) ?? lastList.current
      result.ui_actions.forEach(onAction)
    } catch (error) {
      updateAssistant(answerId, { pending: false, error: `오류: ${error instanceof Error ? error.message : String(error)}` })
    } finally {
      setBusy(false)
    }
  }

  // 승인: 사용자의 클릭으로만 /copilot/apply를 호출합니다. 서버가 기존 서비스로 검증·저장하고 변경 기록을 남깁니다.
  const approve = async (id: number, proposal: Proposal, state: ProposalState, traceId?: string) => {
    updateProposal(id, { status: 'saving', error: undefined })
    try {
      const response = await fetch(`${API_BASE}/copilot/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(applyBody(proposal, state, traceId)),
      })
      if (!response.ok) throw new Error(await errorDetail(response))
      updateProposal(id, { status: 'approved', done: await response.json() as ApplyResponse, doneAt: new Date().toISOString() })
      onDataChanged()
    } catch (error) {
      updateProposal(id, { status: 'open', error: `실패: ${error instanceof Error ? error.message : String(error)}` })
    }
  }

  // 되돌리기 1단계: 서버가 지금 데이터로 무엇이 바뀔지 계산해 보여 줍니다. 아직 아무것도 바뀌지 않습니다.
  const startUndo = async (id: number, traceId?: string) => {
    if (!traceId) return
    updateProposal(id, { undo: { status: 'loading' } })
    try {
      const response = await fetch(`${API_BASE}/copilot/undo/${traceId}?client_id=${clientId()}`)
      if (!response.ok) throw new Error(await errorDetail(response))
      updateProposal(id, { undo: { status: 'preview', preview: await response.json() as UndoPreview } })
    } catch (error) {
      updateProposal(id, { undo: { status: 'preview', preview: { steps: [], skipped: [] },
        error: `확인하지 못했어요: ${error instanceof Error ? error.message : String(error)}` } })
    }
  }

  // 되돌리기 2단계: [N명 되돌리기]를 눌렀을 때만 실행합니다. 변경 기록에도 남습니다.
  const confirmUndo = async (id: number, undo: UndoState, traceId?: string) => {
    if (!traceId) return
    updateProposal(id, { undo: { ...undo, status: 'saving', error: undefined } })
    try {
      const response = await fetch(`${API_BASE}/copilot/undo/${traceId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId() }),
      })
      if (!response.ok) throw new Error(await errorDetail(response))
      const result = await response.json() as { message: string; undone_at: string; skipped: UndoSkip[] }
      updateProposal(id, { undo: { status: 'done', message: result.message, at: result.undone_at, skipped: result.skipped } })
      onDataChanged()
    } catch (error) {
      updateProposal(id, { undo: { ...undo, status: 'preview', error: `되돌리지 못했어요: ${error instanceof Error ? error.message : String(error)}` } })
    }
  }

  const submit = (event: FormEvent) => { event.preventDefault(); ask(draft.trim()) }
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중 Enter는 무시해야 마지막 글자가 중복 전송되지 않습니다.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); ask(draft.trim()) }
  }

  return <>
    <div className="copilot-bar">
      <button type="button" onClick={() => historyOpen ? setHistoryOpen(false) : showHistory()} aria-expanded={historyOpen}
        title="지난 대화">☰ 지난 대화</button>
      <span title={title ?? undefined}>{title ?? '새 대화'}</span>
      <button type="button" onClick={startNew} disabled={busy || (messages.length === 0 && !conversationId)} title="새 대화 시작">+ 새 대화</button>
    </div>
    <div className="copilot-main">
    {historyOpen && <HistoryPanel items={historyItems} error={historyError} currentId={conversationId}
      onOpen={open} onClose={() => setHistoryOpen(false)} />}
    <div className="legal-chat-log" ref={logRef} onScroll={onLogScroll} aria-live="polite">
      {messages.length === 0 && <div className="legal-chat-empty">
        <Mascot size={88} mood="wave" />
        <h3>업무 Chatbot이에요.</h3>
        <p>인원 조회, 편성·해제 제안, 현황·교육 미달·이상 데이터 점검을 도와드려요.<br />데이터 변경은 [승인]을 눌렀을 때만 일어나고, 변경 기록에 남아요.</p>
        <div className="legal-chat-chips">
          {EXAMPLES.map(example => <button key={example} type="button" disabled={busy} onClick={() => ask(example)}>{example}</button>)}
        </div>
      </div>}
      {messages.map(message => message.role === 'user'
        ? <div key={message.id} className="legal-chat-bubble is-user">{message.text}</div>
        : <div key={message.id} className="legal-chat-row">
          <span className="legal-chat-avatar"><Mascot size={30} mood={message.pending ? 'thinking' : 'idle'} /></span>
          <div className="legal-chat-bubble is-assistant">
            {(message.conditions?.length || message.unparsed?.length) ? <div className="copilot-conditions" aria-label="적용한 조건">
              <span>조건</span>
              {message.conditions?.map(condition => <b key={condition}>{condition}</b>)}
              {message.unparsed?.map(word => <b key={word} className="is-unparsed" title="이해하지 못한 말">{word}?</b>)}
            </div> : null}
            {message.text.split('\n').map((line, index) => <p key={index}>{line}</p>)}
            {message.error && <p className="is-error">{message.error}</p>}
            {message.pending && <p className="legal-chat-pending">
              <span className="legal-chat-dots" aria-hidden="true"><i /><i /><i /></span>확인하는 중
            </p>}
            {message.proposal && message.proposalState && <ProposalCard
              proposal={message.proposal}
              state={message.proposalState}
              onSelect={squadId => updateProposal(message.id, { selected: squadId })}
              onApprove={() => approve(message.id, message.proposal!, message.proposalState!, message.traceId)}
              onCancel={() => updateProposal(message.id, { status: 'cancelled' })}
              onUndoStart={() => startUndo(message.id, message.traceId)}
              onUndoConfirm={() => confirmUndo(message.id, message.proposalState!.undo!, message.traceId)}
              onUndoClose={() => updateProposal(message.id, { undo: undefined })}
            />}
          </div>
        </div>)}
    </div>
    </div>

    <form className="legal-chat-form" onSubmit={submit}>
      <textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={onKeyDown} rows={2} maxLength={500}
        placeholder="예: 2소대 해군 병사 보여줘 (Shift+Enter 줄바꿈)" aria-label="Copilot 요청" />
      <button type="submit" disabled={busy || !draft.trim()} aria-label="요청 보내기">{busy ? '…' : '➤'}</button>
    </form>
  </>
}
