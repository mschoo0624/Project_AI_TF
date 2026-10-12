import { Fragment, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './messenger.css'
import { formatClock, formatDay, formatListTime } from './messengerData'
import type { Conversation } from './messengerData'

type MessengerProps = {
  open: boolean
  conversations: Conversation[]
  roomId: number | null
  onRoomChange: (roomId: number | null) => void
  onSend: (roomId: number, text: string) => void
  onClose: () => void
}

export function MessengerLauncher({ open, unread, onToggle }: { open: boolean; unread: number; onToggle: () => void }) {
  return <button type="button" className={`messenger-launcher${open ? ' is-open' : ''}`} onClick={onToggle} aria-expanded={open} aria-label="메신저 열기">
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12Z" />
    </svg>
    <span>메신저</span>
    {unread > 0 && <b className="messenger-badge">{unread}</b>}
  </button>
}

export default function Messenger({ open, conversations, roomId, onRoomChange, onSend, onClose }: MessengerProps) {
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const room = conversations.find(item => item.id === roomId) ?? null

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [room?.messages.length, roomId])

  if (!open) return null

  const goRoom = (id: number | null) => { setDraft(''); onRoomChange(id) }
  const lastTime = (item: Conversation) => item.messages[item.messages.length - 1]?.sentAt ?? 0
  const keyword = query.trim()
  const visible = [...conversations]
    .filter(item => !keyword || item.name.includes(keyword) || item.unit.includes(keyword) || item.messages.some(message => message.text.includes(keyword)))
    .sort((a, b) => lastTime(b) - lastTime(a))

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const text = draft.trim()
    if (!room || !text) return
    onSend(room.id, text)
    setDraft('')
  }

  return <aside className="messenger" aria-label="메신저">
    <header className="messenger-head">
      {room && <button type="button" className="messenger-icon-btn" aria-label="대화 목록으로" onClick={() => goRoom(null)}>‹</button>}
      <div className="messenger-title">
        <strong>{room ? room.name : '메시지'}</strong>
        {room && <small>{room.unit}</small>}
      </div>
      <button type="button" className="messenger-icon-btn" aria-label="메신저 닫기" onClick={onClose}>✕</button>
    </header>

    {room ? <>
      <div className="messenger-thread">
        {room.messages.map((message, index) => {
          const previous = room.messages[index - 1]
          const newDay = !previous || formatDay(previous.sentAt) !== formatDay(message.sentAt)
          return <Fragment key={message.id}>
            {newDay && <div className="messenger-day">{formatDay(message.sentAt)}</div>}
            <div className={`messenger-row ${message.from}`}>
              <p className="messenger-bubble">{message.text}</p>
              <time>{formatClock(message.sentAt)}</time>
            </div>
          </Fragment>
        })}
        <div ref={endRef} />
      </div>
      <form className="messenger-compose" onSubmit={submit}>
        <input value={draft} onChange={event => setDraft(event.target.value)} placeholder="메시지 입력" aria-label="메시지 입력" />
        <button type="submit" disabled={!draft.trim()} aria-label="보내기">↑</button>
      </form>
    </> : <>
      <div className="messenger-search">
        <input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="이름, 부서, 내용 검색" aria-label="대화 검색" />
      </div>
      <ul className="messenger-list">
        {visible.map(item => {
          const last = item.messages[item.messages.length - 1]
          return <li key={item.id}>
            <button type="button" className="messenger-item" onClick={() => goRoom(item.id)}>
              <span className="messenger-avatar">{item.name.slice(0, 1)}</span>
              <span className="messenger-item-main">
                <strong>{item.name}<small>{item.unit}</small></strong>
                <span>{last?.text}</span>
              </span>
              <span className="messenger-item-meta">
                {last && <time>{formatListTime(last.sentAt)}</time>}
                {item.unread > 0 && <b className="messenger-badge">{item.unread}</b>}
              </span>
            </button>
          </li>
        })}
        {visible.length === 0 && <li className="messenger-empty">검색 결과가 없습니다.</li>}
      </ul>
    </>}
  </aside>
}
