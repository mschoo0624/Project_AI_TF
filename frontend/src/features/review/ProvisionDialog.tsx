import { useEffect, useRef, useState } from 'react'
import { CLASSIFIER_BASE, request, type Citation, type Verification } from './classifierApi'
import VerificationResult from './VerificationResult'

type Page = Citation & { reason_number?: string | null; width: number; height: number; boxes: number[][] }
export default function ProvisionDialog({ applicationType, result, onClose }: { applicationType: string; result: Verification | null; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [page, setPage] = useState<Page | null>(null)
  const [error, setError] = useState('')
  const [zoom, setZoom] = useState(100)
  useEffect(() => {
    dialog.current?.showModal()
    const controller = new AbortController()
    request<Page>(`${CLASSIFIER_BASE}/verification-view/${encodeURIComponent(applicationType)}`, { signal: controller.signal }).then(setPage).catch(e => { if (!controller.signal.aborted) setError(String(e)) })
    return () => controller.abort()
  }, [applicationType])
  return <dialog ref={dialog} className="review-provision-dialog" onCancel={onClose} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
    <header><strong>검증 결과·관련 조항</strong><button autoFocus type="button" onClick={onClose}>닫기</button></header>
    <div className="review-provision-controls"><span>{page ? `${page.provision} · ${page.page}쪽 · ${page.reason_number ? `${page.reason_number} ` : ''}${page.item}` : '불러오는 중…'}</span><label>배율 <select value={zoom} onChange={e => setZoom(Number(e.target.value))}>{[75, 100, 125, 150, 200].map(value => <option key={value} value={value}>{value}%</option>)}</select></label></div>
    {error && <p role="alert">{error}</p>}
    <div className="review-provision-scroll">{page && <>
      {!page.boxes.length && <p role="status">해당 항목의 위치를 찾지 못했습니다. 원문을 확인하세요.</p>}
      <div className="review-provision-sheet" style={{ width: `${zoom}%` }}>
        <img src={`${CLASSIFIER_BASE}/verification-sources/${page.table}/pages/${page.page}/image?render=antialias300`} alt={`${page.provision} ${page.page}쪽`} onError={() => setError('기준표 이미지를 불러오지 못했습니다.')} />
        {page.boxes.map(([x0, y0, x1, y1], index) => <span key={index} className="review-evidence-highlight" style={{ left: `${x0/page.width*100}%`, top: `${y0/page.height*100}%`, width: `${(x1-x0)/page.width*100}%`, height: `${(y1-y0)/page.height*100}%` }} />)}
      </div>
      <a href={`${CLASSIFIER_BASE}/verification-sources/${page.table}#page=${page.page}`} target="_blank" rel="noreferrer">기준표 PDF 원본 열기</a>
    </>}
    <VerificationResult result={result} /></div>
  </dialog>
}
