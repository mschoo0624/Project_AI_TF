import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import Mascot from './Mascot'

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
}
type ApplyResponse = { message: string }
type ProposalState = {
  status: 'open' | 'saving' | 'approved' | 'cancelled'
  selected: number
  error?: string
  done?: ApplyResponse
}

type Message =
  | { id: number; role: 'user'; text: string }
  | {
    id: number; role: 'assistant'; text: string; pending: boolean; error?: string
    proposal?: Proposal; proposalState?: ProposalState; traceId?: string
    conditions?: string[]; unparsed?: string[]
  }

async function errorDetail(response: Response) {
  try {
    const body = await response.json() as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
  } catch {
    return `HTTP ${response.status}`
  }
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

function ProposalCard({ proposal, state, onSelect, onApprove, onCancel }: {
  proposal: Proposal
  state: ProposalState
  onSelect: (squadId: number) => void
  onApprove: () => void
  onCancel: () => void
}) {
  const chosen = proposal.options.find(option => option.squad_id === state.selected)
  const doneText = proposal.kind === 'assign_squad' ? `${chosen?.squad_name}에 편성했습니다.`
    : proposal.kind === 'move' ? `${chosen?.squad_name}(으)로 옮겼습니다.` : state.done?.message
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
    {state.status === 'approved' && <p className="copilot-proposal-done">✓ {doneText}</p>}
    {state.status === 'cancelled' && <p className="copilot-proposal-done">취소했습니다. 변경된 내용은 없습니다.</p>}
    {(state.status === 'open' || state.status === 'saving') && <div className="copilot-proposal-actions">
      <button type="button" onClick={onCancel} disabled={state.status === 'saving'}>취소</button>
      <button type="button" className="is-primary" onClick={onApprove} disabled={state.status === 'saving'}>
        {state.status === 'saving' ? '저장 중…' : approveLabel(proposal)}
      </button>
    </div>}
  </div>
}

export default function CopilotChat({ onAction, onDataChanged }: {
  onAction: (action: CopilotAction) => void
  onDataChanged: () => void
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const nextMessageId = useRef(1)
  // 직전 답변이 보여준 명단. "저 인원들 편성해줘"가 이 명단을 가리킵니다.
  const lastList = useRef<{ label: string; ids: string[] } | null>(null)

  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages])

  const updateAssistant = (id: number, update: Partial<Extract<Message, { role: 'assistant' }>>) =>
    setMessages(current => current.map(message => message.id === id && message.role === 'assistant' ? { ...message, ...update } : message))
  const updateProposal = (id: number, update: Partial<ProposalState>) =>
    setMessages(current => current.map(message => message.id === id && message.role === 'assistant' && message.proposalState
      ? { ...message, proposalState: { ...message.proposalState, ...update } } : message))

  const ask = async (question: string) => {
    if (!question || busy) return
    const answerId = nextMessageId.current + 1
    nextMessageId.current += 2
    setMessages(current => [...current,
      { id: answerId - 1, role: 'user', text: question },
      { id: answerId, role: 'assistant', text: '', pending: true }])
    setDraft('')
    setBusy(true)
    try {
      const response = await fetch(`${API_BASE}/copilot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, context: lastList.current }),
      })
      if (!response.ok) throw new Error(await errorDetail(response))
      const result = await response.json() as ChatResponse
      updateAssistant(answerId, {
        text: result.message,
        pending: false,
        proposal: result.proposal ?? undefined,
        traceId: result.trace_id,
        conditions: result.conditions,
        unparsed: result.unparsed,
        proposalState: result.proposal ? { status: 'open', selected: result.proposal.options[0]?.squad_id ?? 0 } : undefined,
      })
      const listAction = [...result.ui_actions].reverse().find(action => action.type !== 'navigate' && action.ids.length > 0)
      if (listAction) lastList.current = { label: listAction.label ?? listAction.ids.join(', '), ids: listAction.ids }
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
      updateProposal(id, { status: 'approved', done: await response.json() as ApplyResponse })
      onDataChanged()
    } catch (error) {
      updateProposal(id, { status: 'open', error: `실패: ${error instanceof Error ? error.message : String(error)}` })
    }
  }

  const submit = (event: FormEvent) => { event.preventDefault(); ask(draft.trim()) }
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중 Enter는 무시해야 마지막 글자가 중복 전송되지 않습니다.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); ask(draft.trim()) }
  }

  return <>
    <div className="legal-chat-log" ref={logRef} aria-live="polite">
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
            />}
          </div>
        </div>)}
    </div>

    <form className="legal-chat-form" onSubmit={submit}>
      <textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={onKeyDown} rows={2} maxLength={500}
        placeholder="예: 2소대 해군 병사 보여줘 (Shift+Enter 줄바꿈)" aria-label="Copilot 요청" />
      <button type="submit" disabled={busy || !draft.trim()} aria-label="요청 보내기">{busy ? '…' : '➤'}</button>
    </form>
  </>
}
