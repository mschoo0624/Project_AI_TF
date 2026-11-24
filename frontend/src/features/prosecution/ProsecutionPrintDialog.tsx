import { useEffect, useRef, useState } from 'react'
import { errorMessage } from './api'

export default function ProsecutionPrintDialog({ html, title, savedAt, onClose }: { html: string; title: string; savedAt: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const frame = useRef<HTMLIFrameElement>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { dialog.current?.showModal() }, [])
  const print = async () => {
    setError('')
    try {
      const documentWindow = frame.current?.contentWindow
      if (!documentWindow) throw new Error('인쇄 화면이 준비되지 않았습니다.')
      await documentWindow.document.fonts.ready
      documentWindow.focus()
      documentWindow.print()
    } catch (cause) { setError(errorMessage(cause)) }
  }
  return <dialog ref={dialog} className="prosecution-modal prosecution-print-dialog" aria-labelledby="prosecution-print-title" onCancel={event => { event.preventDefault(); onClose() }}>
    <header><div><h2 id="prosecution-print-title">인쇄 미리보기 · {title}</h2><p>저장 시각: {savedAt} · A4 · 인쇄 창에서 프린터 또는 PDF 저장을 선택하세요.</p></div><div><button type="button" disabled={!ready} onClick={() => void print()}>인쇄 / PDF로 저장</button><button type="button" onClick={onClose}>닫기</button></div></header>
    {error && <p role="alert" className="rm-org-error">{error}</p>}
    <iframe ref={frame} title="저장된 고발장 인쇄 미리보기" srcDoc={html} onLoad={() => setReady(true)} />
  </dialog>
}
