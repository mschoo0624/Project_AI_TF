import { useEffect, useRef, useState } from 'react'
import './WorkLogManagement.css'

type Entry = { id: string; year: number; month: number; day: number; pdf?: string }
const STORAGE_KEY = 'aitf-worklog-index-v1'

// 기존 시연용 목록과 localStorage 키를 유지합니다.
const initialEntries: Entry[] = [1, 2, 3, 4, 5].map(day => ({
  id: `2026-01-${String(day).padStart(2, '0')}`, year: 2026, month: 1, day,
}))
const initialMonths = ['2026-01', '2026-02']
const sampleStatuses = ['대기', '작성중', '검토중', '승인', '완료'] as const

const keyOf = (year: number, month: number) => `${year}-${String(month).padStart(2, '0')}`
const dateOf = (entry: Entry) =>
  `${entry.year}.${String(entry.month).padStart(2, '0')}.${String(entry.day).padStart(2, '0')}`
const titleOf = (entry: Entry) => `${entry.year}년 ${entry.month}월 ${entry.day}일 업무일지`
const safeRead = <T,>(key: string, fallback: T): T => {
  try { const value = localStorage.getItem(key); return value ? JSON.parse(value) as T : fallback }
  catch { return fallback }
}

export default function WorkLogManagement() {
  const [months, setMonths] = useState<string[]>(() => safeRead(`${STORAGE_KEY}-months`, initialMonths))
  const [entries, setEntries] = useState<Entry[]>(() => safeRead(`${STORAGE_KEY}-entries`, initialEntries))
  const [expanded, setExpanded] = useState<number[]>(() =>
    [...new Set(months.map(month => Number(month.slice(0, 4))))])
  const [expandedMonths, setExpandedMonths] = useState<string[]>([])
  const [selectedMonth, setSelectedMonth] = useState<string | null>(
    () => months.includes('2026-01') ? '2026-01' : (months[0] ?? null),
  )
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [pdfOverrides, setPdfOverrides] = useState<Record<string, string>>({})
  const [pdfError, setPdfError] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const blobUrls = useRef<string[]>([])

  useEffect(() => { localStorage.setItem(`${STORAGE_KEY}-months`, JSON.stringify(months)) }, [months])
  useEffect(() => { localStorage.setItem(`${STORAGE_KEY}-entries`, JSON.stringify(entries)) }, [entries])
  useEffect(() => () => { blobUrls.current.forEach(url => URL.revokeObjectURL(url)) }, [])

  const years = [...new Set([...months, ...entries.map(entry => keyOf(entry.year, entry.month))]
    .map(month => Number(month.slice(0, 4))))].sort((a, b) => a - b)
  const selected = entries.find(entry => entry.id === selectedId) ?? null
  const monthEntries = entries.filter(entry => keyOf(entry.year, entry.month) === selectedMonth)
    .sort((a, b) => a.day - b.day)
  const visibleEntries = monthEntries.filter(entry =>
    `${dateOf(entry)} ${titleOf(entry)}`.toLowerCase().includes(search.trim().toLowerCase()))
  const selectedPdf = selected ? pdfOverrides[selected.id] ?? selected.pdf : undefined
  const monthLabel = selectedMonth
    ? `${Number(selectedMonth.slice(0, 4))}년 ${Number(selectedMonth.slice(5))}월`
    : '업무일지'

  // 프로그래밍으로 월을 선택하는 경우(새 월 생성 등)에는 문서 목록도 펼칩니다.
  const selectMonth = (month: string) => {
    setSelectedMonth(month)
    setExpandedMonths(prev => prev.includes(month) ? prev : [...prev, month])
    setExpanded(prev => {
      const year = Number(month.slice(0, 4))
      return prev.includes(year) ? prev : [...prev, year]
    })
    setSelectedId(null)
    setSearch('')
    setPdfError(false)
  }
  const toggleMonth = (month: string) => {
    setExpandedMonths(prev => prev.includes(month) ? prev.filter(key => key !== month) : [...prev, month])
    setSelectedMonth(month)
    setSelectedId(null)
    setSearch('')
    setPdfError(false)
  }
  const selectEntry = (id: string) => {
    const entry = entries.find(item => item.id === id)
    if (entry) {
      const month = keyOf(entry.year, entry.month)
      setSelectedMonth(month)
      setExpandedMonths(prev => prev.includes(month) ? prev : [...prev, month])
      setExpanded(prev => prev.includes(entry.year) ? prev : [...prev, entry.year])
    }
    setSelectedId(id)
    setPdfError(false)
  }

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
    if (!Number.isInteger(day) || date.getFullYear() !== year ||
      date.getMonth() !== month - 1 || date.getDate() !== day) {
      window.alert('유효한 날짜를 입력하세요.')
      return
    }
    const id = `${selectedMonth}-${String(day).padStart(2, '0')}`
    if (entries.some(entry => entry.id === id)) { selectEntry(id); return }
    // 탐색기는 매년 12개월을 보여주되, 실제로 생성한 월만 저장합니다.
    setMonths(prev => prev.includes(selectedMonth) ? prev : [...prev, selectedMonth].sort())
    setEntries(prev => [...prev, { id, year, month, day }])
    selectEntry(id)
  }

  const remove = () => {
    if (selectedId) {
      if (!window.confirm('선택한 업무일지를 목록에서 삭제하시겠습니까? PDF 원본 파일은 삭제되지 않습니다.')) return
      setEntries(prev => prev.filter(entry => entry.id !== selectedId))
      setSelectedId(null)
    } else if (selectedMonth && months.includes(selectedMonth)) {
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
    if (!Number.isInteger(day) || date.getFullYear() !== selected.year ||
      date.getMonth() !== selected.month - 1 || date.getDate() !== day) {
      window.alert('유효한 날짜를 입력하세요.')
      return
    }
    const id = `${keyOf(selected.year, selected.month)}-${String(day).padStart(2, '0')}`
    if (id !== selected.id && entries.some(entry => entry.id === id)) {
      window.alert('같은 날짜의 일지가 이미 있습니다.')
      return
    }
    setEntries(prev => prev.map(entry => entry.id === selected.id ? { ...entry, id, day } : entry))
    if (pdfOverrides[selected.id]) {
      setPdfOverrides(prev => {
        const next = { ...prev, [id]: prev[selected.id] }
        if (id !== selected.id) delete next[selected.id]
        return next
      })
    }
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
      window.alert('PDF 파일만 선택할 수 있습니다.')
      return
    }
    const url = URL.createObjectURL(file)
    blobUrls.current.push(url)
    setPdfOverrides(prev => ({ ...prev, [selected.id]: url }))
    setPdfError(false)
  }

  return <section className={`worklog ${selected ? 'worklog--pdf' : 'worklog--list'}`}>
    <header className="worklog-heading">
      <div>
        <h1>업무일지</h1>
        <p>{monthLabel} 업무일지 목록</p>
      </div>
      <div className="worklog-heading-actions">
        <button className="worklog-btn worklog-btn--primary" onClick={create}>생성</button>
        <button className="worklog-btn" onClick={edit} disabled={!selected}>수정</button>
      </div>
    </header>

    <div className="worklog-layout">
      <aside className="worklog-explorer" aria-label="업무일지 탐색기">
        <nav className="worklog-tree" aria-label="연도 및 월">
          <div className="worklog-tree-label">
            <strong>연도 / 월</strong>
            <span className="worklog-chevron" aria-hidden="true" />
          </div>
          {years.map(year => <div key={year}>
            <button
              className="worklog-tree-row worklog-tree-year"
              onClick={() => setExpanded(prev => prev.includes(year) ? prev.filter(value => value !== year) : [...prev, year])}
              aria-expanded={expanded.includes(year)}
              aria-controls={`worklog-year-${year}`}
            >
              <span>{year}년</span><span className={`worklog-chevron ${expanded.includes(year) ? '' : 'worklog-chevron--closed'}`} aria-hidden="true" />
            </button>
            {expanded.includes(year) && <div id={`worklog-year-${year}`} className="worklog-year-months">
              {Array.from({ length: 12 }, (_, index) => index + 1).map(month => {
                const key = keyOf(year, month)
                const isOpen = expandedMonths.includes(key)
                const documents = entries.filter(entry => keyOf(entry.year, entry.month) === key)
                  .sort((a, b) => a.day - b.day)
                return <div key={key} className="worklog-month-group">
                  <button
                    className={`worklog-tree-row worklog-tree-month ${selectedMonth === key ? 'is-selected' : ''}`}
                    onClick={() => toggleMonth(key)}
                    aria-expanded={isOpen}
                    aria-controls={`worklog-documents-${key}`}
                  >
                    <span>{month}월</span>
                    <span className={`worklog-chevron ${isOpen ? '' : 'worklog-chevron--closed'}`} aria-hidden="true" />
                  </button>
                  {isOpen && <div id={`worklog-documents-${key}`} className="worklog-month-entries" role="group" aria-label={`${year}년 ${month}월 문서 목록`}>
                    {documents.map(entry => <button
                      key={entry.id}
                      className={`worklog-tree-file ${selectedId === entry.id ? 'is-selected' : ''}`}
                      onClick={() => selectEntry(entry.id)}
                      aria-current={selectedId === entry.id ? 'page' : undefined}
                      title={`${dateOf(entry)} 업무일지`}
                    >
                      <span className="worklog-file-icon" aria-hidden="true" />
                      <span className="worklog-file-name">{dateOf(entry)} 업무일지</span>
                    </button>)}
                    {documents.length === 0 && <p className="worklog-month-empty">등록된 문서가 없습니다.</p>}
                  </div>}
                </div>
              })}
            </div>}
          </div>)}
        </nav>
        <div className="worklog-explorer-actions">
          <div className="worklog-action-row">
            <button className="worklog-btn worklog-btn--primary" onClick={create}>생성</button>
            <button className="worklog-btn" onClick={remove}
              disabled={!selectedId && !(selectedMonth && months.includes(selectedMonth))}>삭제</button>
            <button className="worklog-btn" onClick={edit} disabled={!selected}>수정</button>
          </div>
          <input
            aria-label="업무일지 검색"
            placeholder="검색어 입력"
            value={search}
            onChange={event => setSearch(event.target.value)}
          />
        </div>
      </aside>

      <main className="worklog-content">
        {!selected ? <>
          <div className="worklog-content-head">
            <h2>{selectedMonth ? `${monthLabel} 업무일지` : '업무일지'}</h2>
            <span className="worklog-count">총 {visibleEntries.length}건</span>
          </div>
          <div className="worklog-list">
            {visibleEntries.map(entry => {
              const sampleIndex = initialEntries.findIndex(item => item.id === entry.id)
              const status = sampleIndex >= 0 ? sampleStatuses[sampleIndex] : '대기'
              return <button key={entry.id} className="worklog-list-row" onClick={() => selectEntry(entry.id)}>
                <span className="worklog-entry-name">{dateOf(entry)} 업무일지</span>
                <span className="worklog-entry-meta">
                  <span className="worklog-status">{status}</span>
                  <time>{dateOf(entry)}{sampleIndex >= 0 ? ' 08:00' : ''}</time>
                </span>
              </button>
            })}
            {selectedMonth && visibleEntries.length === 0 &&
              <p className="worklog-empty-list">{search ? '검색 결과가 없습니다.' : '해당 월에 등록된 업무일지가 없습니다.'}</p>}
            {!selectedMonth && <p className="worklog-empty-list">왼쪽에서 연도와 월을 선택하세요.</p>}
          </div>
        </> : <>
          <div className="worklog-content-head">
            <h2>{monthLabel} 업무일지</h2>
            <div className="worklog-document-actions">
              <button className="worklog-btn" onClick={savePdf} disabled={!selectedPdf}>저장</button>
              <button className="worklog-btn" onClick={() => fileInput.current?.click()}>불러오기</button>
              <button className="worklog-btn" onClick={() => selectedPdf && window.open(selectedPdf, '_blank', 'noopener,noreferrer')}
                disabled={!selectedPdf}>출력</button>
            </div>
          </div>
          <input ref={fileInput} className="worklog-hidden-input" type="file" accept="application/pdf,.pdf"
            onChange={event => { upload(event.target.files?.[0]); event.target.value = '' }} />
          {selectedPdf && !pdfError
            ? <iframe key={selectedPdf} title={titleOf(selected)} src={selectedPdf} className="worklog-pdf" onError={() => setPdfError(true)} />
            : <div className="worklog-no-pdf">
                <strong>{titleOf(selected)}</strong>
                <span>연결된 PDF 파일이 없습니다. ‘불러오기’로 PDF를 선택하세요.</span>
              </div>}
          {selectedPdf && <p className="worklog-pdf-note">‘저장’은 PDF 다운로드, ‘출력’은 PDF를 새 창에서 여는 기능입니다.</p>}
        </>}
      </main>
    </div>
    <p className="worklog-storage-note">
      시범 화면: 목록과 상태 표시는 예시이며 목록 변경은 이 브라우저에만 저장됩니다. 불러온 PDF는 새로고침 후 유지되지 않습니다.
    </p>
  </section>
}
