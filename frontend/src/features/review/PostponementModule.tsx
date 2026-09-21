import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './PostponementModule.css'

// AITF 백엔드는 /api (8002), Classifier는 /classifier-api (8001) 프록시를 사용합니다.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const CLASSIFIER_BASE = '/classifier-api'

type MatchedPerson = {
  military_number: string
  name: string
  branch: string
  status: string
  service_year: number
}

type Extraction = {
  name?: string | null
  valid_until?: string | null
  document_type?: string | null
  stamp_present?: boolean | null
  confidence?: number | null
  anomaly_flags?: string[]
  error?: string
}

type Submission = {
  id: string
  filename: string
  saved_path: string
  military_number: string | null
  extraction: Extraction
  reason_category: string | null
  status: 'pending' | 'approved' | 'declined'
  note: string | null
  created_at: string
  decided_at: string | null
  projectPostponementId?: number
}

type Postponement = {
  id: number
  person_id: string
  classifier_submission_id: string | null
  status: string
}

async function responseError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json() as { detail?: string | { msg?: string }[] }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map(item => item.msg ?? fallback).join(' ')
  } catch { /* 텍스트 또는 프록시 오류 응답 */ }
  return `${fallback} (HTTP ${response.status})`
}

function statusLabel(status: Submission['status']): string {
  return status === 'pending' ? '검토대기' : status === 'approved' ? '승인' : '반려'
}

function safePdfUrl(path: string): string | null {
  return path.startsWith('/uploads/') && !path.includes('..')
    ? `${CLASSIFIER_BASE}${path}` : null
}

function SubmissionDetails({
  submission, personName, onDecision, onLink, busy,
}: {
  submission: Submission | null
  personName?: string
  onDecision: (submission: Submission, decision: 'approved' | 'declined') => Promise<void>
  onLink: (submission: Submission) => Promise<void>
  busy: boolean
}) {
  if (!submission) return <section className="review-ai-detail review-ai-detail-empty">왼쪽 목록에서 제출 건을 선택하세요.</section>
  const extraction = submission.extraction ?? {}
  const pdfUrl = safePdfUrl(submission.saved_path)

  return <section className="review-ai-detail" aria-label="AI 서류 분석 결과">
    <div className="review-ai-heading">
      <h3>AI 분석 결과</h3>
      <span className={`review-ai-status ${submission.status}`}>{statusLabel(submission.status)}</span>
    </div>
    <p className="review-ai-subtitle">{personName ?? extraction.name ?? '이름 미확인'} · {submission.military_number ?? '군번 미기재'}</p>
    <div className="review-ai-pdf">
      <div className="review-ai-pdf-header"><strong>원본 PDF</strong><span title={submission.filename}>{submission.filename}</span>
        {pdfUrl && <a href={pdfUrl} target="_blank" rel="noreferrer">새 탭에서 열기 ↗</a>}
      </div>
      {pdfUrl ? <iframe title={`${submission.filename} 원본 PDF`} src={pdfUrl} />
        : <p className="review-ai-empty">원본 PDF 경로를 확인할 수 없습니다.</p>}
    </div>
    <dl className="review-ai-facts">
      <div><dt>성명</dt><dd>{extraction.name ?? '—'}</dd></div>
      <div><dt>서류 종류</dt><dd>{extraction.document_type ?? '—'}</dd></div>
      <div><dt>유효기간</dt><dd>{extraction.valid_until ?? '—'}</dd></div>
      <div><dt>사유 분류</dt><dd>{submission.reason_category ?? '미분류'}</dd></div>
      <div><dt>모델 신뢰도</dt><dd>{extraction.confidence != null ? `${Math.round(extraction.confidence * 100)}%` : '—'}</dd></div>
      <div><dt>도장/서명 인식</dt><dd>{extraction.stamp_present == null ? '확인 필요' : extraction.stamp_present ? '감지됨' : '감지되지 않음'}</dd></div>
    </dl>
    {extraction.error && <p className="review-ai-alert" role="alert">AI 분석 오류: {extraction.error}</p>}
    {extraction.anomaly_flags?.length ? <div className="review-ai-alert"><strong>이상 신호</strong>{extraction.anomaly_flags.map((flag, index) => <p key={`${flag}-${index}`}>! {flag}</p>)}</div> :
      <p className="review-ai-notice">자동 추출에서 표시한 이상 신호가 없습니다. 원본 확인과 별개입니다.</p>}
    {submission.status === 'pending' && (submission.projectPostponementId != null
      ? <div className="review-ai-actions"><button type="button" disabled={busy} onClick={() => void onDecision(submission, 'approved')}>승인</button><button type="button" className="reject" disabled={busy} onClick={() => void onDecision(submission, 'declined')}>반려</button></div>
      : <div className="review-ai-unlinked"><p>AITF의 연기 신청과 연결되지 않은 제출 건입니다. 등록된 군번이 있으면 연결 후 검토할 수 있습니다.</p><button type="button" disabled={busy || !submission.military_number} onClick={() => void onLink(submission)}>AITF 신청 연결</button></div>)}
  </section>
}

export default function PostponementModule() {
  const [file, setFile] = useState<File | null>(null)
  const [militaryNumber, setMilitaryNumber] = useState('')
  const [matchedPerson, setMatchedPerson] = useState<MatchedPerson | null>(null)
  const [matching, setMatching] = useState(false)
  const [personNames, setPersonNames] = useState<Record<string, string>>({})
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const personRequest = useRef(0)
  const selected = submissions.find(item => item.id === selectedId) ?? null

  const loadSubmissions = useCallback(async () => {
    setLoadingList(true)
    try {
      const [classifierResponse, aitfResponse] = await Promise.all([
        fetch(`${CLASSIFIER_BASE}/submissions`), fetch(`${API_BASE}/postponements`),
      ])
      if (!classifierResponse.ok) throw new Error(await responseError(classifierResponse, 'Classifier 제출 목록을 불러오지 못했습니다.'))
      if (!aitfResponse.ok) throw new Error(await responseError(aitfResponse, 'AITF 연기 기록을 불러오지 못했습니다.'))
      const loaded = await classifierResponse.json() as Submission[]
      const projectItems = await aitfResponse.json() as Postponement[]
      const links = new Map(projectItems.filter(item => item.classifier_submission_id).map(item => [item.classifier_submission_id, item.id]))
      const linked = loaded.map(item => ({ ...item, projectPostponementId: links.get(item.id) }))
      setSubmissions(linked)
      setSelectedId(current => linked.some(item => item.id === current) ? current : (linked[0]?.id ?? null))
      const numbers = [...new Set(loaded.map(item => item.military_number).filter((value): value is string => !!value))]
      const matches = await Promise.all(numbers.map(async number => {
        try {
          const response = await fetch(`${API_BASE}/persons/${encodeURIComponent(number)}`)
          if (response.ok) return [number, (await response.json() as MatchedPerson).name] as const
        } catch { /* 일부 인원 조회 오류가 제출 목록 전체를 막지 않게 함 */ }
        return null
      }))
      setPersonNames(Object.fromEntries(matches.filter((item): item is readonly [string, string] => item !== null)))
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '제출 목록을 불러오지 못했습니다.')
    } finally {
      setLoadingList(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void Promise.resolve().then(() => { if (!cancelled) return loadSubmissions() })
    return () => { cancelled = true }
  }, [loadSubmissions])

  const findPerson = async (value: string) => {
    const request = ++personRequest.current
    setMilitaryNumber(value)
    setMatchedPerson(null)
    setError('')
    if (!value.trim()) { setMatching(false); return }
    setMatching(true)
    try {
      const response = await fetch(`${API_BASE}/persons/${encodeURIComponent(value.trim())}`)
      if (request !== personRequest.current) return
      if (response.ok) setMatchedPerson(await response.json() as MatchedPerson)
      else if (response.status !== 404) setError(await responseError(response, '군번 조회에 실패했습니다.'))
    } catch {
      if (request === personRequest.current) setError('군번 조회에 실패했습니다. AITF 백엔드를 확인하세요.')
    } finally {
      if (request === personRequest.current) setMatching(false)
    }
  }

  const createPostponement = async (submission: Submission, person: MatchedPerson): Promise<Postponement> => {
    const response = await fetch(`${API_BASE}/postponements`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        person_id: person.military_number,
        reason: submission.reason_category ?? submission.extraction?.document_type ?? '서류 제출',
        category: submission.reason_category,
        training_year: person.service_year,
        source_file: submission.filename,
        classifier_submission_id: submission.id,
      }),
    })
    if (!response.ok) throw new Error(await responseError(response, 'AITF 연기 신청 연결에 실패했습니다.'))
    return response.json() as Promise<Postponement>
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!file || !matchedPerson || matching || matchedPerson.military_number !== militaryNumber.trim()) {
      setError('PDF 파일과 AITF에 등록된 군번을 확인해 주세요.'); return
    }
    setBusy(true); setError(''); setNotice('')
    let submitted: Submission | null = null
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('military_number', matchedPerson.military_number)
      const response = await fetch(`${CLASSIFIER_BASE}/submissions`, { method: 'POST', body: form })
      if (!response.ok) throw new Error(await responseError(response, 'PDF 업로드 및 분석에 실패했습니다.'))
      submitted = await response.json() as Submission
      const projectItem = await createPostponement(submitted, matchedPerson)
      const linked = { ...submitted, projectPostponementId: projectItem.id }
      setSubmissions(items => [linked, ...items.filter(item => item.id !== linked.id)])
      setPersonNames(names => ({ ...names, [matchedPerson.military_number]: matchedPerson.name }))
      setSelectedId(linked.id)
      setFile(null)
      setNotice('서류 업로드와 AITF 연기 신청 연결이 완료됐습니다. 승인 전 원본을 확인해 주세요.')
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'PDF 제출에 실패했습니다.'
      setError(submitted ? `PDF는 Classifier에 저장됐으나 AITF 연결에 실패했습니다: ${message} 아래 목록에서 해당 제출 건을 선택해 다시 연결하세요.` : message)
      if (submitted) {
        const savedSubmission = submitted
        setSubmissions(items => [savedSubmission, ...items.filter(item => item.id !== savedSubmission.id)])
        setSelectedId(savedSubmission.id)
      }
    } finally { setBusy(false) }
  }

  const linkSubmission = async (submission: Submission) => {
    if (!submission.military_number) return
    setBusy(true); setError(''); setNotice('')
    try {
      const response = await fetch(`${API_BASE}/persons/${encodeURIComponent(submission.military_number)}`)
      if (!response.ok) throw new Error(await responseError(response, 'AITF 등록 군번을 확인할 수 없습니다.'))
      const person = await response.json() as MatchedPerson
      const projectItem = await createPostponement(submission, person)
      setSubmissions(items => items.map(item => item.id === submission.id ? { ...item, projectPostponementId: projectItem.id } : item))
      setNotice('AITF 연기 신청과 연결했습니다.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'AITF 연기 신청 연결에 실패했습니다.') }
    finally { setBusy(false) }
  }

  const decide = async (submission: Submission, decision: 'approved' | 'declined') => {
    if (submission.projectPostponementId == null) return
    setBusy(true); setError(''); setNotice('')
    try {
      const action = decision === 'approved' ? 'approve' : 'reject'
      const response = await fetch(`${API_BASE}/postponements/${submission.projectPostponementId}/${action}`, { method: 'PATCH' })
      if (!response.ok) throw new Error(await responseError(response, '제출 건 처리에 실패했습니다.'))
      await response.json()
      setSubmissions(items => items.map(item => item.id === submission.id ? { ...item, status: decision } : item))
      setNotice(`연기 신청이 ${decision === 'approved' ? '승인' : '반려'}됐습니다.`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '제출 건 처리에 실패했습니다.') }
    finally { setBusy(false) }
  }

  return <div className="review-ai-module">
    <header className="review-ai-top">
      <div><h2>서류 AI 판정</h2><p>등록된 인원의 PDF를 제출하고 AI 추출 결과와 원본을 대조해 검토합니다.</p></div>
      <button type="button" className="review-ai-secondary" disabled={busy || loadingList} onClick={() => void loadSubmissions()}>목록 새로고침</button>
    </header>
    <form className="review-ai-form" onSubmit={submit}>
      <label>군번 <small>AITF에 등록된 인원만 제출할 수 있습니다.</small>
        <input value={militaryNumber} onChange={event => void findPerson(event.target.value)} placeholder="군번 입력" autoComplete="off" />
      </label>
      <label>제출 서류 <small>PDF 형식</small>
        <input type="file" accept="application/pdf,.pdf" onChange={event => {
          const candidate = event.target.files?.[0] ?? null
          setFile(candidate?.name.toLowerCase().endsWith('.pdf') ? candidate : null)
          setError(candidate && !candidate.name.toLowerCase().endsWith('.pdf') ? 'PDF 파일만 업로드할 수 있습니다.' : '')
        }} />
      </label>
      <div className={`review-ai-match ${matchedPerson ? 'matched' : ''}`}>
        {matching ? '군번 조회 중…' : matchedPerson ? `확인됨: ${matchedPerson.name} · ${matchedPerson.military_number} · ${matchedPerson.branch}` : militaryNumber ? '등록 인원을 찾지 못했습니다. 군번을 확인해 주세요.' : '군번을 입력하면 등록 인원을 확인합니다.'}
      </div>
      <div className="review-ai-form-actions"><span>{file ? `선택: ${file.name}` : 'PDF 파일을 선택해 주세요.'}</span><button type="submit" disabled={busy || matching || !file || !matchedPerson}>{busy ? '처리 중…' : 'PDF 업로드 및 AI 분석'}</button></div>
    </form>
    {error && <p className="review-ai-feedback error" role="alert">{error}</p>}
    {notice && <p className="review-ai-feedback" role="status">{notice}</p>}
    <div className="review-ai-layout">
      <section className="review-ai-list" aria-label="서류 제출 목록">
        <header><h3>제출 목록</h3><span>검토대기 {submissions.filter(item => item.status === 'pending').length}건</span></header>
        {loadingList ? <p className="review-ai-empty">제출 목록을 불러오는 중입니다…</p> : !submissions.length ? <p className="review-ai-empty">제출된 PDF가 없습니다.</p> :
          <div className="review-ai-list-scroll">{submissions.map(item => <button key={item.id} type="button" className={`review-ai-item ${selectedId === item.id ? 'selected' : ''}`} onClick={() => setSelectedId(item.id)} aria-pressed={selectedId === item.id}>
            <strong>{personNames[item.military_number ?? ''] ?? item.extraction?.name ?? '이름 미확인'}</strong>
            <span className={`review-ai-status ${item.status}`}>{statusLabel(item.status)}</span>
            <small>{item.military_number ?? '군번 미기재'} · {item.filename}</small>
          </button>)}</div>}
      </section>
      <SubmissionDetails submission={selected} personName={selected?.military_number ? personNames[selected.military_number] : undefined} onDecision={decide} onLink={linkSubmission} busy={busy} />
    </div>
  </div>
}
