import { useEffect, useState } from 'react'
import { API_BASE, CLASSIFIER_BASE, analysisComplete, decide, fieldValue, jsonRequest, notifyReviewChanged, request,
  type FieldDefinitions, type Proof, type Submission } from './classifierApi'
import ProvisionDialog from './ProvisionDialog'

const labels: Record<string, string> = { subject_name: '성명', subject_birth_date: '생년월일', patient_resident_number: '주민등록번호' }
const DEMO_TRAINING_DATES = '2026년 5월 11일 ~ 5월 13일'
const DEMO_TRAINING_START = '2026-05-11'
const DEMO_TRAINING_END = '2026-05-13'
const compact = (value: string) => value.replace(/\s+/g, '')
function displayValue(item: Submission, key: string) {
  const value = fieldValue(item, key)
  return ['medical_institution', 'doctor_license', 'certificate_registration_number', 'certificate_serial_number'].includes(key) ? compact(value) : value
}

type Comparison = { person: { name: string; military_number: string; branch: string } | null; trainings: { id: number; scheduled_date: string | null }[] }

export default function EvidenceReviewPanel({ submission, onHighlight, onDone, onOpenAnalysis }: {
  submission: Submission; onHighlight: (proof: Proof[]) => void; onDone: (label: string, changed: boolean) => void; onOpenAnalysis: (id: string) => void
}) {
  const [item, setItem] = useState(submission)
  const [definitions, setDefinitions] = useState<FieldDefinitions>({})
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [number, setNumber] = useState('')
  const [showProvisions, setShowProvisions] = useState(false)
  const [trainingOverlap, setTrainingOverlap] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    setTrainingOverlap(false)
    if (analysisComplete(item)) {
      request<{ overlaps: boolean }>(`${CLASSIFIER_BASE}/submissions/${item.id}/training-overlap?start=${DEMO_TRAINING_START}&end=${DEMO_TRAINING_END}`, { signal: controller.signal })
        .then(result => { if (!controller.signal.aborted) setTrainingOverlap(result.overlaps) })
        .catch(() => { /* Missing or unavailable date evidence remains 확인 필요. */ })
    }
    return () => controller.abort()
  }, [item.id, item.extraction, item.analysis_state])
  const trainingDates = <div className="review-db-comparison"><strong>확인된 훈련 날짜</strong><p>{DEMO_TRAINING_DATES} <span className={trainingOverlap ? 'review-match' : 'review-institution-unverified'}>{trainingOverlap ? '날짜 겹침' : '확인 필요'}</span></p></div>
  useEffect(() => {
    setItem(current => submission.review_revision > current.review_revision || submission.analysis_state !== current.analysis_state || submission.status !== current.status || (!current.military_number && submission.military_number) ? submission : current)
  }, [submission])
  useEffect(() => {
    let active = true
    Promise.all([request<FieldDefinitions>(`${CLASSIFIER_BASE}/field-definitions`), request<Comparison>(`${API_BASE}/postponements/submissions/${item.id}/review-context`)])
      .then(([fields, profile]) => { if (active) { setDefinitions(fields); setComparison(profile) } })
      .catch(e => { if (active) setError(String(e)) })
    return () => { active = false }
  }, [item.id, item.military_number])
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }
  const check = (id: string, value: boolean) => run(async () => {
    const saved = await request<Submission>(`${CLASSIFIER_BASE}/submissions/${item.id}/review-checks`, jsonRequest('PATCH', {
      checks: { ...item.review_checks, [id]: value }, revision: item.review_revision,
    }))
    setItem({ ...item, ...saved })
  })
  const allChecked = item.review_items.length > 0 && item.review_items.every(entry => item.review_checks[entry.id])
  const finalDecision = (decision: 'approved' | 'declined') => {
    if (!window.confirm(`${item.applicant_name || '선택한 신청자'}의 신청을 ${decision === 'approved' ? '최종 승인' : '반려'}하시겠습니까?\n처리 후에는 검토 내용을 수정할 수 없습니다.`)) return
    void run(async () => { await decide(item, decision, note); onDone(decision === 'approved' ? '승인' : '반려', true) })
  }
  if (item.reanalysis && !analysisComplete(item)) return <div className="review-action-body" role="status">
    {['queued', 'analyzing'].includes(item.analysis_state ?? '') ? 'AI가 문서를 재검토 중입니다' : item.analysis_state === 'cancelled' ? '문서 재검토가 취소되었습니다.' : '문서 재검토에 실패했습니다.'}
    {['failed', 'cancelled'].includes(item.analysis_state ?? '') && <button type="button" onClick={() => onOpenAnalysis(item.id)}>서류 AI 판정에서 다시 분석</button>}
  </div>
  return <div className="review-action-body">
    <h3>{item.applicant_name || '성명 미확인'} · {item.reason_category}</h3>
    {!item.military_number && <div className="review-reason-picker"><p>본인확인을 위해 대상자를 연결하세요.</p><input aria-label="연결할 군번" value={number} onChange={e => setNumber(e.target.value)} placeholder="군번" /><button type="button" disabled={busy || !number.trim()} onClick={() => void run(async () => {
      const result = await request<{ submission: Submission; message: string }>(`${API_BASE}/postponements/resolve-applicant`, jsonRequest('POST', { submission_id: item.id, military_number: number.trim() }))
      if (!result.submission.military_number) throw new Error(result.message)
      setItem(result.submission); notifyReviewChanged()
    })}>대상자 연결</button></div>}
    <p>각 근거를 원본과 대조한 뒤 직접 체크하세요. 항목에 마우스를 올리거나 초점을 두면 PDF의 근거 위치가 표시됩니다.</p>
    {item.review_items.map(entry => {
      const birthLink = entry.fields.includes('subject_birth_date') ? item.verification?.checks.find(check => check.id === 'birth_information_link') : undefined
      const fields = entry.fields.includes('subject_birth_date') ? [...entry.fields, 'patient_resident_number'] : entry.fields
      const proofs = fields.flatMap(key => item.extraction.fields[key]?.evidence ?? [])
      return <section key={entry.id} className="review-evidence-check" onMouseEnter={() => onHighlight(proofs)} onMouseLeave={() => onHighlight([])} onFocus={() => onHighlight(proofs)} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) onHighlight([]) }}>
        <label><input type="checkbox" checked={!!item.review_checks[entry.id]} disabled={busy || item.status !== 'pending'} onChange={e => void check(entry.id, e.target.checked)} />{entry.label}</label>
        {!item.review_checks[entry.id] && <>
        <table className="review-evidence-table" aria-label={`${entry.label} 근거 대조`}>
          <colgroup><col style={{ width: '40%' }} /><col style={{ width: '60%' }} /></colgroup>
          <thead><tr><th scope="col">항목</th><th scope="col">문서 내용</th></tr></thead>
          <tbody>{fields.length ? fields.map(key => <tr key={key} tabIndex={0}
            onMouseEnter={e => { e.stopPropagation(); onHighlight(key === 'subject_birth_date' ? birthLink?.evidence ?? item.extraction.fields[key]?.evidence ?? [] : item.extraction.fields[key]?.evidence ?? []) }}
            onMouseLeave={e => {
              const section = e.currentTarget.closest('.review-evidence-check')
              onHighlight(e.relatedTarget instanceof Node && section?.contains(e.relatedTarget) ? proofs : [])
            }}
            onFocus={e => { e.stopPropagation(); onHighlight(key === 'subject_birth_date' ? birthLink?.evidence ?? item.extraction.fields[key]?.evidence ?? [] : item.extraction.fields[key]?.evidence ?? []) }}>
            <th scope="row">{labels[key] ?? definitions[key]?.label ?? key}</th>
            <td><span className={key === 'subject_birth_date' ? 'review-birth-value' : undefined}>{displayValue(item, key)}{key === 'subject_birth_date' && birthLink?.values?.subject_birth_date != null && item.extraction.fields.patient_resident_number?.value != null && <> (주민번호로 연결: {String(birthLink.values.subject_birth_date).replace('??', '세기 미확인 · ')})</>}</span>{item.extraction.fields[key]?.value != null && String(item.extraction.fields[key].value).trim() !== '' && ['invalid', 'conflicting', 'unresolved'].includes(item.extraction.fields[key]?.status) && <strong className="review-evidence-warning"> · 확인 필요</strong>}</td>
          </tr>) : <tr><th scope="row">{entry.label}</th><td>별도 추출 정보 없음 — 원본 확인 필요</td></tr>}</tbody>
        </table>
        {entry.description && <p>{entry.description}</p>}
        {entry.id === 'issuer' && <div className="review-db-comparison">
          <p onMouseEnter={() => onHighlight(item.extraction.fields.medical_institution?.evidence ?? item.extraction.fields.issuer_name?.evidence ?? [])} onMouseLeave={() => onHighlight(proofs)}>기관이름: {item.extraction.fields.medical_institution?.value ? displayValue(item, 'medical_institution') : fieldValue(item, 'issuer_name')} <span className="review-institution-unverified">(확인 필요)</span></p>
          <p onMouseEnter={() => onHighlight([])} onMouseLeave={() => onHighlight(proofs)}>주소: —</p>
          <p onMouseEnter={() => onHighlight([])} onMouseLeave={() => onHighlight(proofs)}>링크: —</p>
        </div>}
        {birthLink?.status === 'review' && <p className="review-evidence-warning" role="alert">{birthLink.message}</p>}
        {entry.person_fields && <div className="review-db-comparison"><strong>등록 병사 정보</strong>{comparison?.person ? <>
          <p>성명: {comparison.person.name} {item.extraction.fields.subject_name?.value && <span className={compact(String(item.extraction.fields.subject_name.value)) === compact(comparison.person.name) ? 'review-match' : 'review-mismatch'}>{compact(String(item.extraction.fields.subject_name.value)) === compact(comparison.person.name) ? '일치' : '불일치'}</span>}</p>
          <p>군번: {comparison.person.military_number}</p><p>군별: {comparison.person.branch}</p>
          {/* Demo-only display; never supplied to verification or persisted as identity evidence. */}
          <p>생년월일: {String(birthLink?.values?.subject_birth_date ?? item.extraction.fields.subject_birth_date?.value ?? '—')} <span className="review-match">일치</span></p>
        </> : <p>연결된 병사 정보가 없습니다.</p>}</div>}
        {(entry.id === 'dates' || entry.context_fields?.length) ? trainingDates : null}
        {entry.id === 'eligibility' && <p>신청 사유: {item.reason_category}<br />AI 검증: {item.verification?.result_label ?? '미검증'}</p>}
        {!proofs.some(proof => proof.bbox) && <small>위치 정보가 없는 항목은 원본을 직접 확인하세요.</small>}
        </>}
      </section>
    })}
    {!item.review_items.some(entry => entry.id === 'dates' || entry.context_fields?.length) && trainingDates}
    <div className="review-reference-actions"><button type="button" className="review-document-link" onClick={() => setShowProvisions(true)}>검증 결과·관련 조항</button><button type="button" className="review-document-link" onClick={() => onOpenAnalysis(item.id)}>서류 AI 판정 재검증</button></div>
    {showProvisions && <ProvisionDialog applicationType={item.application_type} result={item.verification} onClose={() => setShowProvisions(false)} />}
    <label className="review-decision-note">비고<textarea value={note} maxLength={2000} onChange={e => setNote(e.target.value)} /></label>
    <div className="review-actions"><button className="approve" type="button" disabled={busy || !analysisComplete(item) || !allChecked || !item.military_number} onClick={() => finalDecision('approved')}>최종승인</button><button className="reject" type="button" disabled={busy} onClick={() => finalDecision('declined')}>반려</button><button className="verify" type="button" disabled={busy || !note.trim()} onClick={() => void run(async () => {
      await request(`${CLASSIFIER_BASE}/submissions/${item.id}/request-confirmation`, jsonRequest('POST', { note })); notifyReviewChanged(); onDone('확인요청', false)
    })}>확인요청</button></div>
    {error && <p role="alert" className="review-action-error">{error}<button type="button" onClick={() => void run(async () => setItem(await request<Submission>(`${CLASSIFIER_BASE}/submissions/${item.id}`)))}>검토 상태 새로고침</button></p>}
  </div>
}
