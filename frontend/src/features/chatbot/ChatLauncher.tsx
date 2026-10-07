import { useEffect, useState } from 'react'
import Mascot from './Mascot'

// 사이드바 맨 아래 법령 도우미 버튼. 페이지를 처음 열면 인사 말풍선이 잠깐 나타납니다.
export default function ChatLauncher({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [hint, setHint] = useState(false)
  const [hovered, setHovered] = useState(false)

  useEffect(() => {
    const show = window.setTimeout(() => setHint(true), 1200)
    const hide = window.setTimeout(() => setHint(false), 8000)
    return () => { window.clearTimeout(show); window.clearTimeout(hide) }
  }, [])

  return <div className="chat-launcher-area">
    {hint && !open && <button type="button" className="chat-launcher-hint" onClick={() => setHint(false)} aria-label="안내 닫기">
      법령이 궁금하면<br />저를 눌러주세요!
    </button>}
    <button type="button" className={`chat-launcher ${open ? 'is-open' : ''}`} aria-expanded={open} aria-controls="legal-chat-panel"
      onClick={() => { setHint(false); onToggle() }} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      <Mascot size={58} mood={hovered || hint ? 'wave' : 'idle'} />
      <strong>AI 온누리</strong>
      <span>{open ? '닫기' : '무엇이든 물어보세요'}</span>
    </button>
  </div>
}
