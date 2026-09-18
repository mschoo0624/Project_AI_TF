import { useEffect, useRef, useState } from 'react'
import './WorkLogManagement.css'

type Entry = { id: string; year: number; month: number; day: number; pdf?: string }
const STORAGE_KEY = 'aitf-worklog-index-v1'
const initialEntries: Entry[] = [1, 2, 3, 4, 5].map(day => ({
  id: `2026-01-${String(day).padStart(2, '0')}`, year: 2026, month: 1, day,
}))
const initialMonths = ['2026-01', '2026-02']
const keyOf = (year: number, month: number) => `${year}-${String(month).padStart(2, '0')}`
const titleOf = (entry: Entry) => `${entry.year}년 ${entry.month}월 ${entry.day}일 업무일지`
const safeRead = <T,>(key: string, fallback: T): T => {
  try { const value = localStorage.getItem(key); return value ? JSON.parse(value) as T : fallback }
  catch { return fallback }
}

export default function WorkLogManagement() {
  const [months, setMonths] = useState<string[]>(() => safeRead(`${STORAGE_KEY}-months`, initialMonths))
  const [entries, setEntries] = useState<Entry[]>(() => safeRead(`${STORAGE_KEY}-entries`, initialEntries))
  const [expanded, setExpanded] = useState<number[]>([])
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [pdfOverrides, setPdfOverrides] = useState<Record<string, string>>({})
  const [pdfError, setPdfError] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const blobUrls = useRef<string[]>([])
  useEffect(() => { localStorage.setItem(`${STORAGE_KEY}-months`, JSON.stringify(months)) }, [months])
  useEffect(() => { localStorage.setItem(`${STORAGE_KEY}-entries`, JSON.stringify(entries)) }, [entries])
  useEffect(() => () => { blobUrls.current.forEach(url => URL.revokeObjectURL(url)) }, [])

  const years = [...new Set(months.map(month => Number(month.slice(0, 4))))].sort((a, b) => a - b)
  const selected = entries.find(entry => entry.id === selectedId) ?? null
  const monthEntries = entries.filter(entry => keyOf(entry.year, entry.month) === selectedMonth)
    .sort((a, b) => a.day - b.day)
  const selectedPdf = selected ? pdfOverrides[selected.id] ?? selected.pdf : undefined
  const selectMonth = (month: string) => { setSelectedMonth(month); setSelectedId(null); setPdfError(false) }
  const selectEntry = (id: string) => { setSelectedId(id); setPdfError(false) }

  const create = () => {
    if (!selectedMonth) {
      const answer = window.prompt('생성할 연월을 입력하세요. (예: 2026-03)')?.trim()
      if (!answer || !/^\d{4}-(0[1-9]|1[0-2])$/.test(answer)) return
      if (months.includes(answer)) { selectMonth(answer); return }
      setMonths(prev => [...prev, answer].sort())
      setExpanded(prev => [...new Set([...prev, Number(answer.slice(0, 4))])])
      selectMonth(answer)
      return
    }
    const answer = window.prompt(`${selectedMonth}에 추가할 날짜를 입력하세요. (1~31)`)?.trim()
    if (!answer) return
    const day = Number(answer)
    const [year, month] = selectedMonth.split('-').map(Number)
    const date = new Date(year, month - 1, day)
    if (!Number.isInteger(day) || date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
      window.alert('유효한 날짜를 입력하세요.'); return
    }
    const id = `${selectedMonth}-${String(day).padStart(2, '0')}`
    if (entries.some(entry => entry.id === id)) { selectEntry(id); return }
    setEntries(prev => [...prev, { id, year, month, day }])
    selectEntry(id)
  }
  const remove = () => {
    if (selectedId) {
      if (!window.confirm('선택한 업무일지를 목록에서 삭제하시겠습니까? PDF 원본 파일은 삭제되지 않습니다.')) return
      setEntries(prev => prev.filter(entry => entry.id !== selectedId))
      setSelectedId(null)
    } else if (selectedMonth) {
      if (!window.confirm('선택한 월과 해당 월의 업무일지 목록을 삭제하시겠습니까? PDF 원본 파일은 삭제되지 않습니다.')) return
      setMonths(prev => prev.filter(month => month !== selectedMonth))
      setEntries(prev => prev.filter(entry => keyOf(entry.year, entry.month) !== selectedMonth))
      setSelectedMonth(null)
    }
  }
  const edit = () => {
    if (!selected) { window.alert('먼저 수정할 업무일지를 선택하세요.'); return }
    const answer = window.prompt('변경할 날짜를 입력하세요. (1~31)', String(selected.day))?.trim()
    if (!answer) return
    const day = Number(answer)
    const date = new Date(selected.year, selected.month - 1, day)
    if (!Number.isInteger(day) || date.getMonth() !== selected.month - 1 || date.getDate() !== day) {
      window.alert('유효한 날짜를 입력하세요.'); return
    }
    const id = `${keyOf(selected.year, selected.month)}-${String(day).padStart(2, '0')}`
    if (id !== selected.id && entries.some(entry => entry.id === id)) { window.alert('같은 날짜의 일지가 이미 있습니다.'); return }
    setEntries(prev => prev.map(entry => entry.id === selected.id ? { ...entry, id, day } : entry))
    if (pdfOverrides[selected.id]) setPdfOverrides(prev => ({ ...prev, [id]: prev[selected.id] }))
    setSelectedId(id)
  }
  const savePdf = () => {
    if (!selectedPdf || !selected) return
    const link = document.createElement('a')
    link.href = selectedPdf
    link.download = `${selected.id}.pdf`
    link.click()
  }
  const upload = (file?: File) => {
    if (!selected || !file) return
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      window.alert('PDF 파일만 선택할 수 있습니다.'); return
    }
    const url = URL.createObjectURL(file)
    blobUrls.current.push(url)
    setPdfOverrides(prev => ({ ...prev, [selected.id]: url }))
    setPdfError(false)
  }

  return <section className="worklog">
    <h1 className="worklog-title">업무일지</h1>
    <div className="worklog-layout">
      <aside className="worklog-explorer" aria-label="업무일지 탐색기">
        <div className="worklog-tree">
          {years.map(year => <div key={year}>
            <button className="worklog-tree-row" onClick={() => setExpanded(prev => prev.includes(year) ? prev.filter(y => y !== year) : [...prev, year])}>
              <span className="worklog-caret">{expanded.includes(year) ? '▼' : '▶'}</span><span className="worklog-folder">📁</span>{year}년
            </button>
            {expanded.includes(year) && months.filter(month => month.startsWith(`${year}-`)).map(month => <button
              key={month} className={`worklog-tree-row worklog-month ${selectedMonth === month ? 'is-selected' : ''}`}
              onClick={() => selectMonth(month)}><span className="worklog-folder">📁</span>{Number(month.slice(5))}월</button>)}
          </div>)}
        </div>
        <div className="worklog-explorer-actions">
          <div className="worklog-action-row">
            <button onClick={create}>생성</button><button onClick={remove} disabled={!selectedMonth}>삭제</button><button onClick={edit} disabled={!selectedId}>수정</button>
          </div>
          <input aria-label="업무일지 검색" placeholder="입력하시오." readOnly title="검색은 추후 데이터 연동 시 제공됩니다." />
        </div>
      </aside>
      <div className="worklog-content">
        {!selectedMonth ? <div className="worklog-empty-heading" /> : !selected ? <>
          <div className="worklog-content-head"><h2>{Number(selectedMonth.slice(0, 4))}년 {Number(selectedMonth.slice(5))}월</h2><div><button onClick={create}>생성</button><button onClick={edit} disabled>수정</button></div></div>
          <div className="worklog-list">{monthEntries.map(entry => <button key={entry.id} onClick={() => selectEntry(entry.id)}>{`${entry.year}.${String(entry.month).padStart(2, '0')}.${String(entry.day).padStart(2, '0')} 업무일지`}</button>)}</div>
        </> : <>
          <div className="worklog-content-head"><h2>{titleOf(selected)}</h2><div>
            <button onClick={savePdf} disabled={!selectedPdf}>저장</button>
            <button onClick={() => fileInput.current?.click()}>불러오기</button>
            <button onClick={() => selectedPdf && window.open(selectedPdf, '_blank', 'noopener,noreferrer')} disabled={!selectedPdf}>출력</button>
          </div></div>
          <input ref={fileInput} className="worklog-hidden-input" type="file" accept="application/pdf,.pdf" onChange={event => { upload(event.target.files?.[0]); event.target.value = '' }} />
          {selectedPdf && !pdfError ? <iframe key={selectedPdf} title={titleOf(selected)} src={selectedPdf} className="worklog-pdf" onError={() => setPdfError(true)} />
            : <div className="worklog-no-pdf">PDF 파일이 없습니다. ‘불러오기’를 눌러 PDF를 선택하세요.</div>}
          {selectedPdf && <p className="worklog-pdf-note">‘저장’은 PDF 다운로드, ‘출력’은 PDF를 새 창에서 여는 기능입니다.</p>}
        </>}
      </div>
    </div>
    <p className="worklog-storage-note">시범 화면: 목록 변경은 이 브라우저에만 저장됩니다. 불러온 PDF는 새로고침 후 유지되지 않으며 서버에 업로드되지 않습니다.</p>
  </section>
}
