import { useEffect, useRef, useState } from 'react'
import { CLASSIFIER_BASE, pdfUrl, type Proof, type Submission } from './classifierApi'

export default function EvidencePdf({ item, highlights = [] }: { item: Submission; highlights?: Proof[] }) {
  const [chosenPage, setChosenPage] = useState(1)
  const [failed, setFailed] = useState(false)
  const [zoom, setZoom] = useState<number | null>(null)
  const [viewport, setViewport] = useState({ width: 600, height: 700 })
  const scrollRef = useRef<HTMLDivElement>(null)
  const sheetRef = useRef<HTMLDivElement>(null)
  const pages = item.extraction.pdf?.pages ?? []
  const marked = highlights.filter(proof => proof.bbox && proof.page)
  const page = marked[0]?.page ?? chosenPage
  const size = pages.find(entry => entry.number === page)
  const fitScale = size ? Math.min(Math.max(1, viewport.width-16)/size.width, Math.max(1, viewport.height-16)/size.height) : 1
  const scale = zoom ?? fitScale
  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    const measure = () => setViewport({ width: element.clientWidth, height: element.clientHeight })
    const observer = new ResizeObserver(measure)
    observer.observe(element); measure()
    return () => observer.disconnect()
  }, [size?.number, failed])
  const target = marked.find(proof => proof.page === page)?.bbox
  const targetKey = target?.join(',')
  useEffect(() => {
    const scroller = scrollRef.current, sheet = sheetRef.current
    if (!scroller || !sheet || !targetKey) return
    const frame = requestAnimationFrame(() => {
      const [x0, y0, x1, y1] = targetKey.split(',').map(Number)
      const area = scroller.getBoundingClientRect(), paper = sheet.getBoundingClientRect()
      const left = paper.left+x0*scale, top = paper.top+y0*scale
      const right = paper.left+x1*scale, bottom = paper.top+y1*scale
      if (left < area.left || right > area.right || top < area.top || bottom > area.bottom) {
        scroller.scrollTo({
          left: Math.max(0, scroller.scrollLeft+left-area.left-Math.max(8, (scroller.clientWidth-(x1-x0)*scale)/2)),
          top: Math.max(0, scroller.scrollTop+top-area.top-Math.max(8, (scroller.clientHeight-(y1-y0)*scale)/2)),
          behavior: 'auto',
        })
      }
    })
    return () => cancelAnimationFrame(frame)
  }, [targetKey, page, scale, viewport.width, viewport.height])
  if (!size || failed) return <iframe className="review-evidence-fallback" title={`${item.filename} 원본 PDF`} src={pdfUrl(item.id)} />
  return <div className="review-evidence-pdf">
    <div className="review-evidence-toolbar"><select aria-label="PDF 페이지" value={page} onChange={e => setChosenPage(Number(e.target.value))}>{pages.map(p => <option key={p.number} value={p.number}>{p.number}쪽</option>)}</select>
      <div className="review-evidence-zoom"><button type="button" onClick={() => setZoom(null)}>페이지 맞춤</button><button type="button" aria-label="PDF 축소" disabled={scale <= .25} onClick={() => setZoom(Math.max(.25, scale-.1))}>−</button><label><input aria-label="PDF 배율" type="number" min={25} max={300} value={Math.round(scale*100)} onChange={e => { const value = Number(e.target.value); if (value >= 25 && value <= 300) setZoom(value/100) }} />%</label><button type="button" aria-label="PDF 확대" disabled={scale >= 3} onClick={() => setZoom(Math.min(3, scale+.1))}>+</button></div>
      <a href={pdfUrl(item.id)} target="_blank" rel="noreferrer">원본 열기</a></div>
    <div ref={scrollRef} className="review-evidence-scroll"><div ref={sheetRef} className="review-evidence-page" style={{ width: size.width*scale, height: size.height*scale }}>
      <img src={`${CLASSIFIER_BASE}/submissions/${item.id}/pages/${page}/image`} alt={`${item.filename} ${page}쪽`} onError={() => setFailed(true)} />
      {marked.filter(proof => proof.page === page).map((proof, index) => {
        const [x0, y0, x1, y1] = proof.bbox!
        return <span key={index} className="review-evidence-highlight" title={proof.quote} style={{ left: `${100*x0/size.width}%`, top: `${100*y0/size.height}%`, width: `${100*(x1-x0)/size.width}%`, height: `${100*(y1-y0)/size.height}%` }} />
      })}
    </div></div>
    {highlights.length > 0 && !marked.length && <small>이 근거에는 위치 정보가 없습니다. 원본을 직접 확인하세요.</small>}
  </div>
}
