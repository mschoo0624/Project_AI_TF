import { useEffect, useState } from 'react'
import { errorText, workLogPdf } from './api'

type Props = { date: string; notes: string; eventId: number; refreshKey: number }

export default function WorkLogPreview({ date, notes, eventId, refreshKey }: Props) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    const timer = window.setTimeout(() => {
      workLogPdf(`/${date}/preview`, controller.signal, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes, expected_event_id: eventId }),
      }).then(blob => {
        if (!controller.signal.aborted) setUrl(URL.createObjectURL(blob))
      }).catch(cause => { if (!controller.signal.aborted) setError(errorText(cause)) })
        .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    }, 500)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [date, notes, eventId, refreshKey])

  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])

  return <div className="worklog-live-preview" aria-busy={loading}>
    {error && <p className="worklog-error" role="alert">{error}</p>}
    {loading && <p className="worklog-preview-loading" role="status">PDF 미리보기를 갱신하는 중입니다…</p>}
    {url && <iframe src={`${url}#view=Fit`} title="업무일지 PDF 미리보기" className="worklog-pdf" />}
  </div>
}
