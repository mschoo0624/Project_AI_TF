import { useEffect, useRef, useState } from 'react'
import './HoldButton.css'

type HoldButtonProps = {
  children: string
  doneLabel?: string
  disabled?: boolean
  holdTime?: number
  onHold: () => void
}

export default function HoldButton({
  children,
  doneLabel = '완료',
  disabled = false,
  holdTime = 2000,
  onHold,
}: HoldButtonProps) {
  const [progress, setProgress] = useState(0)
  const [done, setDone] = useState(false)
  const start = useRef<number | null>(null)
  const frame = useRef<number | null>(null)

  const stop = () => {
    start.current = null
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
    setProgress(0)
  }

  const complete = () => {
    if (start.current === null) return
    start.current = null
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
    setProgress(1)
    setDone(true)
    onHold()
    window.setTimeout(() => { setDone(false); setProgress(0) }, 1200)
  }

  const tick = (now: number) => {
    if (start.current === null) return
    const next = Math.min(1, (now - start.current) / holdTime)
    setProgress(next)
    if (next >= 1) complete()
    else frame.current = requestAnimationFrame(tick)
  }

  const begin = () => {
    if (disabled || start.current !== null || done) return
    start.current = performance.now()
    frame.current = requestAnimationFrame(tick)
  }

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
  }, [])

  return <button
    type="button"
    className={`hold-button ${done ? 'is-done' : ''}`}
    style={{ '--hold-progress': progress } as React.CSSProperties}
    disabled={disabled}
    aria-label={`${children}. ${Math.round(holdTime / 100) / 10}초 동안 길게 눌러 확인`}
    onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); begin() }}
    onPointerUp={stop}
    onPointerCancel={stop}
    onPointerLeave={stop}
    onKeyDown={event => {
      if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); begin() }
    }}
    onKeyUp={event => {
      if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); stop() }
    }}
  >
    <span className="hold-button__fill" aria-hidden="true"><span>{done ? doneLabel : children}</span></span>
    <span className="hold-button__label">{done ? doneLabel : children}</span>
  </button>
}
