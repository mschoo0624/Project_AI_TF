import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import Mascot from './Mascot'

// 업무 Copilot (main app /copilot/chat). Copilot은 조회·제안만 하고,
// 저장은 제안 카드의 [승인]을 눌렀을 때 이 화면이 기존 API를 직접 호출합니다.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

const EXAMPLES = [
  '1소대 육군 간부 보여줘',
  '미편성 전입자 명단',
  '방금 등록한 전입자 어디 편성하면 돼?',
  '미편성 인원들 편성해줘',
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
  kind: 'assign_squad' | 'assign_bulk'
  title: string
  person_id: string | null
  options: SquadOption[]
  assignments: PlannedAssignment[]
  notes: string[]
}
type ChatResponse = { message: string; ui_actions: CopilotAction[]; proposal: Proposal | null; trace_id: string }
type ProposalState = { status: 'open' | 'saving' | 'approved' | 'cancelled'; selected: number; error?: string }

type Message =
  | { id: number; role: 'user'; text: string }
  | { id: number; role: 'assistant'; text: string; pending: boolean; error?: string; proposal?: Proposal; proposalState?: ProposalState }

async function errorDetail(response: Response) {
  try {
    const body = await response.json() as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
  } catch {
    return `HTTP ${response.status}`
  }
}

// 승인 시 보낼 편성 목록: 한 사람이면 고른 분대, 여러 명이면 안 전체
function selectionsFor(proposal: Proposal, state: ProposalState) {
  return proposal.kind === 'assign_bulk'
    ? proposal.assignments.map(item => ({ person_id: item.person_id, squad_id: item.squad_id }))
    : [{ person_id: proposal.person_id!, squad_id: state.selected }]
}

function BulkPlan({ proposal }: { proposal: Proposal }) {
  const bySquad = new Map<string, PlannedAssignment[]>()
  proposal.assignments.forEach(item => bySquad.set(item.squad_name, [...(bySquad.get(item.squad_name) ?? []), item]))
  return <div className="copilot-bulk">
    {[...bySquad.entries()].map(([squad, items]) => <details key={squad}>
      <summary>{squad} <small>+{items.length}명</small></summary>
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
  const doneText = proposal.kind === 'assign_bulk' ? `${proposal.assignments.length}명을 편성했습니다.` : `${chosen?.squad_name}에 편성했습니다.`
  return <div className="copilot-proposal">
    <strong>{proposal.title}</strong>
    {proposal.kind === 'assign_bulk' ? <BulkPlan proposal={proposal} /> : <fieldset disabled={state.status !== 'open'}>
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
        {state.status === 'saving' ? '저장 중…' : proposal.kind === 'assign_bulk' ? `${proposal.assignments.length}명 승인` : '승인'}
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

  // 승인: 사용자의 클릭으로만 기존 편성 확정 API를 호출합니다.
  const approve = async (id: number, proposal: Proposal, state: ProposalState) => {
    updateProposal(id, { status: 'saving', error: undefined })
    try {
      const response = await fetch(`${API_BASE}/squads/assignments/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assignments: selectionsFor(proposal, state) }),
      })
      if (!response.ok) throw new Error(await errorDetail(response))
      updateProposal(id, { status: 'approved' })
      onDataChanged()
    } catch (error) {
      updateProposal(id, { status: 'open', error: `편성 실패: ${error instanceof Error ? error.message : String(error)}` })
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
        <h3>업무 Copilot이에요</h3>
        <p>인원을 조건으로 찾거나, 전입자를 어느 분대에 편성할지 추천해 드려요.<br />데이터 변경은 [승인]을 눌렀을 때만 일어나요.</p>
        <div className="legal-chat-chips">
          {EXAMPLES.map(example => <button key={example} type="button" disabled={busy} onClick={() => ask(example)}>{example}</button>)}
        </div>
      </div>}
      {messages.map(message => message.role === 'user'
        ? <div key={message.id} className="legal-chat-bubble is-user">{message.text}</div>
        : <div key={message.id} className="legal-chat-row">
          <span className="legal-chat-avatar"><Mascot size={30} mood={message.pending ? 'thinking' : 'idle'} /></span>
          <div className="legal-chat-bubble is-assistant">
            {message.text.split('\n').map((line, index) => <p key={index}>{line}</p>)}
            {message.error && <p className="is-error">{message.error}</p>}
            {message.pending && <p className="legal-chat-pending">
              <span className="legal-chat-dots" aria-hidden="true"><i /><i /><i /></span>확인하는 중
            </p>}
            {message.proposal && message.proposalState && <ProposalCard
              proposal={message.proposal}
              state={message.proposalState}
              onSelect={squadId => updateProposal(message.id, { selected: squadId })}
              onApprove={() => approve(message.id, message.proposal!, message.proposalState!)}
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
