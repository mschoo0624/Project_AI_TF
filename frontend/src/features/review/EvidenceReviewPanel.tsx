import { useEffect, useState } from 'react'
import { API_BASE, CLASSIFIER_BASE, analysisComplete, decide, fieldValue, jsonRequest, notifyReviewChanged, request,
  type FieldDefinitions, type Proof, type Submission } from './classifierApi'
import VerificationResult from './VerificationResult'

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
        <table className="review-evidence-table" aria-label={`${entry.label} 근거 대조`}>
          <colgroup><col style={{ width: '40%' }} /><col style={{ width: '60%' }} /></colgroup>
          <thead><tr><th scope="col">항목 이름 / 필요 정보</th><th scope="col">문서에서 추출한 정보</th></tr></thead>
          <tbody>{fields.length ? fields.map(key => <tr key={key} tabIndex={0}
            onMouseEnter={e => { e.stopPropagation(); onHighlight(key === 'subject_birth_date' ? birthLink?.evidence ?? item.extraction.fields[key]?.evidence ?? [] : item.extraction.fields[key]?.evidence ?? []) }}
            onFocus={e => { e.stopPropagation(); onHighlight(key === 'subject_birth_date' ? birthLink?.evidence ?? item.extraction.fields[key]?.evidence ?? [] : item.extraction.fields[key]?.evidence ?? []) }}>
            <th scope="row">{definitions[key]?.label ?? key}</th>
            <td>{fieldValue(item, key)}{key === 'subject_birth_date' && birthLink?.values?.subject_birth_date != null && <small><br />연결된 생년월일: {String(birthLink.values.subject_birth_date).replace('??', '세기 미확인 · ')} </small>}{['invalid', 'conflicting', 'unresolved'].includes(item.extraction.fields[key]?.status) && <strong className="review-evidence-warning"> · 확인 필요</strong>}</td>
          </tr>) : <tr><th scope="row">{entry.label}</th><td>별도 추출 정보 없음 — 원본 확인 필요</td></tr>}</tbody>
        </table>
        {birthLink && <p className={birthLink.status === 'review' ? 'review-evidence-warning' : ''} role={birthLink.status === 'review' ? 'alert' : undefined}>{birthLink.message}</p>}
        {entry.person_fields && <div className="review-db-comparison"><strong>등록 병사 정보</strong>{comparison?.person ? <p>성명: {comparison.person.name}<br />군번: {comparison.person.military_number}<br />군별: {comparison.person.branch}<br />주민등록번호: DB 제공 정보 없음 — 원본 신원 자료 확인 필요</p> : <p>연결된 병사 정보가 없습니다.</p>}</div>}
        {entry.context_fields?.length ? <div className="review-db-comparison"><strong>확인된 훈련 기간</strong>{entry.context_fields.map(key => <p key={key}>{key === 'training_start' ? '시작일' : '종료일'}: {String(item.context[key]?.value ?? '미확인')}</p>)}<strong>DB 등록 훈련일</strong>{comparison?.trainings.length ? comparison.trainings.map(training => <p key={training.id}>훈련 #{training.id}: {training.scheduled_date ?? '날짜 미등록'}</p>) : <p>등록된 훈련일이 없습니다. 해당 훈련 일정을 별도로 확인하세요.</p>}</div> : null}
        {entry.id === 'eligibility' && <p>신청 사유: {item.reason_category}<br />AI 검증: {item.verification?.result_label ?? '미검증'}</p>}
        {!proofs.some(proof => proof.bbox) && <small>위치 정보가 없는 항목은 원본을 직접 확인하세요.</small>}
      </section>
    })}
    <details><summary>검증 결과·관련 조항 ▼</summary><VerificationResult result={item.verification} /></details>
    <button type="button" className="review-document-link" onClick={() => onOpenAnalysis(item.id)}>추출 정보·재검증 열기</button>
    <label className="review-decision-note">검토 의견<textarea value={note} maxLength={2000} onChange={e => setNote(e.target.value)} /></label>
    <div className="review-actions"><button className="approve" type="button" disabled={busy || !analysisComplete(item) || !allChecked || !item.military_number} onClick={() => finalDecision('approved')}>최종승인</button><button className="reject" type="button" disabled={busy} onClick={() => finalDecision('declined')}>반려</button><button className="verify" type="button" disabled={busy || !note.trim()} onClick={() => void run(async () => {
      await request(`${CLASSIFIER_BASE}/submissions/${item.id}/request-confirmation`, jsonRequest('POST', { note })); notifyReviewChanged(); onDone('확인요청', false)
    })}>확인요청</button></div>
    {error && <p role="alert" className="review-action-error">{error}<button type="button" onClick={() => void run(async () => setItem(await request<Submission>(`${CLASSIFIER_BASE}/submissions/${item.id}`)))}>검토 상태 새로고침</button></p>}
  </div>
}
