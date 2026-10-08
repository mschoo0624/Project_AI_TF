import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { API_BASE, CLASSIFIER_BASE, analysisComplete, analysisLabel, submissionTitle, formatApprovalTime, fieldValue, jsonRequest, linkSubmission, loadSubmissions, notifyReviewChanged, pdfUrl, request, verifySubmission,
  type ApplicationType, type Fact, type FieldDefinitions, type MatchedPerson, type Rule, type RuleCatalog, type Submission } from './classifierApi'
import VerificationResult from './VerificationResult'
import './PostponementModule.css'

type ContextInput = { key: string; label: string; kind: 'boolean' | 'date' | 'number' | 'text' }
const contextLabels: Record<string, string> = {
  training_start: '훈련 시작일', training_end: '훈련 종료일', applicant_birth_date: '본인 생년월일',
  application_date: '신청일', assessment_date: '판단 기준일', rank_group: '계급 구분',
  exam_lifetime_count: '시험 통산 연기 횟수(병무청 포함)', work_lifetime_count: '주요업무 통산 연기 횟수(병무청 포함)', agriculture_annual_count: '올해 농어업 연기 횟수',
}
function contextInputs(rules: Rule[]): ContextInput[] {
  const found = new Map<string, ContextInput>()
  const walk = (rule: Rule) => {
    for (const field of rule.fields ?? []) {
      if (!field.startsWith('context.')) continue
      const key = field.slice(8)
      if (['applicant_name', 'applicant_service_number'].includes(key)) continue
      const kind = typeof rule.value === 'boolean' ? 'boolean' : rule.op === 'less_than' ? 'number' : /date|training_start|training_end/.test(key) ? 'date' : 'text'
      found.set(key, { key, kind, label: contextLabels[key] ?? rule.label })
    }
    rule.children?.forEach(walk)
  }
  rules.forEach(walk)
  return [...found.values()]
}

function SubmissionDetails({ item, rules, definitions, refresh }: { item: Submission; rules: RuleCatalog | null; definitions: FieldDefinitions; refresh: () => Promise<void> }) {
  const [context, setContext] = useState<Record<string, Fact>>(item.context)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [identityNumber, setIdentityNumber] = useState('')
  const inputs = rules ? contextInputs([...(rules.types[item.application_type]?.common ?? rules.common), ...(rules.types[item.application_type]?.checks ?? [])]) : []
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true); setError('')
    try { await action(); await refresh() } catch (e) { setError(e instanceof Error ? e.message : '처리하지 못했습니다.') }
    finally { setBusy(false) }
  }
  const verify = async () => {
    const facts = Object.fromEntries(Object.entries(context).filter(([, fact]) => fact.value !== null && fact.value !== ''))
    if (Object.values(facts).some(fact => !fact.source.trim())) throw new Error('입력한 확인 정보에는 근거 또는 확인 기록을 적어 주세요.')
    await verifySubmission(item, facts)
  }
  if (!analysisComplete(item)) return <section className="review-ai-detail">
    <div className="review-ai-heading"><h3>{submissionTitle(item)}</h3><span className={`review-ai-status ${item.analysis_state}`}>{analysisLabel(item)}</span></div>
    {item.status === 'approved' && <p className="review-ai-subtitle">승인 일시: {formatApprovalTime(item.approved_at ?? item.decided_at)} (한국시간)</p>}
    {(item.analysis_error || item.analysis_state === 'cancelled') && <p>{item.analysis_error ?? '분석을 취소했습니다.'}</p>}
    <div className="review-ai-pdf"><iframe title={`${item.filename} 원본 PDF`} src={pdfUrl(item.id)} /></div>
  </section>
  return <section className="review-ai-detail" aria-label="서류 분석 및 검증 결과">
    <div className="review-ai-heading"><h3>{submissionTitle(item)}</h3><span className="review-ai-status completed">분석 완료</span></div>
    <p className="review-ai-subtitle">{item.applicant_name} · {item.military_number}</p>
    {item.status === 'approved' && <p className="review-ai-subtitle">승인 일시: {formatApprovalTime(item.approved_at ?? item.decided_at)} (한국시간)</p>}
    <div className="review-ai-pdf"><div className="review-ai-pdf-header"><strong>원본 PDF</strong><span>{item.filename}</span><a href={pdfUrl(item.id)} target="_blank" rel="noreferrer">새 탭에서 열기 ↗</a></div><iframe title={`${item.filename} 원본 PDF`} src={pdfUrl(item.id)} /></div>
    <dl className="review-ai-facts"><div><dt>성명</dt><dd>{fieldValue(item, 'subject_name')}</dd></div><div><dt>서류 종류</dt><dd>{fieldValue(item, 'document_title')}</dd></div><div><dt>발급일</dt><dd>{fieldValue(item, 'issued_on')}</dd></div><div><dt>신청 유형</dt><dd>{item.reason_category}</dd></div><div><dt>검증 결과</dt><dd>{item.verification?.result_label ?? '검증 전'}</dd></div><div><dt>문서 진위</dt><dd>별도 확인 필요</dd></div></dl>
    <VerificationResult result={item.verification} />
    {!item.military_number && <div className="review-context-row"><label>대상자 연결<input value={identityNumber} onChange={e => setIdentityNumber(e.target.value)} placeholder="등록된 대상자의 군번" /></label><button type="button" disabled={busy || !identityNumber.trim()} onClick={() => void run(async () => {
      const result = await request<{ submission: Submission; message: string }>(`${API_BASE}/postponements/resolve-applicant`, jsonRequest('POST', { submission_id: item.id, military_number: identityNumber.trim() }))
      if (!result.submission.military_number) throw new Error(result.message)
      await linkSubmission(result.submission); await verifySubmission(result.submission, {})
    })}>연결 및 검증</button></div>}
    <details className="review-extracted"><summary>추출 항목과 원문 근거 ▼</summary><dl>{Object.entries(item.extraction.fields).map(([key, field]) => <div key={key}><dt>{definitions[key]?.label ?? key}</dt><dd>{fieldValue(item, key)} {['invalid', 'conflicting', 'unresolved'].includes(field.status) && <strong> · 확인 필요</strong>}{field.evidence.map((proof, i) => <small key={i}>{proof.page}쪽 · {proof.quote}</small>)}</dd></div>)}</dl></details>
    {item.status === 'pending' && <>
      <details className="review-context"><summary>추가 확인 정보 입력·재검증 ▼</summary><p>확인한 항목만 입력하세요. 빈 항목은 미확인으로 유지합니다. 모든 대체 요건을 채울 필요는 없습니다.</p>
        {inputs.map(input => <div key={input.key} className="review-context-row"><label>{input.label}
          {input.kind === 'boolean' ? <select disabled={busy} value={context[input.key]?.value == null ? '' : String(context[input.key].value)} onChange={e => setContext(prev => ({ ...prev, [input.key]: { source: prev[input.key]?.source ?? '', value: e.target.value === '' ? null : e.target.value === 'true' } }))}><option value="">미확인</option><option value="true">예</option><option value="false">아니오</option></select>
            : <input disabled={busy} type={input.kind} min={input.kind === 'number' ? 0 : undefined} step={input.kind === 'number' ? 1 : undefined} value={String(context[input.key]?.value ?? '')} onChange={e => setContext(prev => ({ ...prev, [input.key]: { source: prev[input.key]?.source ?? '', value: e.target.value === '' ? null : input.kind === 'number' ? Number(e.target.value) : e.target.value } }))} />}
        </label><label>확인 근거<input disabled={busy} placeholder="조회 자료·담당자 확인 기록" value={context[input.key]?.source ?? ''} onChange={e => setContext(prev => ({ ...prev, [input.key]: { value: prev[input.key]?.value ?? null, source: e.target.value } }))} /></label></div>)}
        <button type="button" className="review-ai-secondary" disabled={busy || !rules} onClick={() => void run(verify)}>{busy ? '처리 중…' : '정보 저장 및 재검증'}</button>
      </details>
      <p className="review-ai-notice">분석 결과를 검토함에 전달했습니다. 근거별 확인과 최종 승인·반려는 검토함에서 진행하세요.</p>
    </>}
    {item.status !== 'pending' && item.note && <p className="review-ai-notice">검토 의견: {item.note}</p>}
    {error && <p role="alert" className="review-ai-feedback error">{error}</p>}
  </section>
}

async function loadPendingSubmissions() {
  return (await loadSubmissions()).filter(item => item.status === 'pending')
}

export default function PostponementModule({ initialSelectedId }: { initialSelectedId?: string | null }) {
  const [file, setFile] = useState<File | null>(null)
  const [militaryNumber, setMilitaryNumber] = useState('')
  const [person, setPerson] = useState<MatchedPerson | null>(null)
  const [matching, setMatching] = useState(false)
  const [types, setTypes] = useState<ApplicationType[]>([])
  const [type, setType] = useState('')
  const [rules, setRules] = useState<RuleCatalog | null>(null)
  const [definitions, setDefinitions] = useState<FieldDefinitions>({})
  const [items, setItems] = useState<Submission[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const requestId = useRef(0)
  const fileInput = useRef<HTMLInputElement>(null)
  const selected = items.find(item => item.id === selectedId)
  const refresh = useCallback(async () => {
    const [loaded, types, rules, definitions] = await Promise.all([loadPendingSubmissions(), request<ApplicationType[]>(`${CLASSIFIER_BASE}/application-types`), request<RuleCatalog>(`${CLASSIFIER_BASE}/verification-rules`), request<FieldDefinitions>(`${CLASSIFIER_BASE}/field-definitions`)])
    setItems(loaded); setTypes(types); setRules(rules); setDefinitions(definitions)
    setSelectedId(current => loaded.some(item => item.id === current) ? current : loaded[0]?.id ?? null)
  }, [])
  useEffect(() => {
    let active = true
    const timer = window.setInterval(() => {
      loadPendingSubmissions().then(loaded => { if (active) {
        setItems(loaded)
        setSelectedId(current => loaded.some(item => item.id === current) ? current : loaded[0]?.id ?? null)
      } }).catch(() => { /* the next poll or manual refresh can recover */ })
    }, 3000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])
  useEffect(() => {
    let cancelled = false
    Promise.all([loadPendingSubmissions(), request<ApplicationType[]>(`${CLASSIFIER_BASE}/application-types`), request<RuleCatalog>(`${CLASSIFIER_BASE}/verification-rules`), request<FieldDefinitions>(`${CLASSIFIER_BASE}/field-definitions`)]).then(([submissions, types, rules, definitions]) => {
      if (cancelled) return
      setItems(submissions); setSelectedId(submissions.find(item => item.id === initialSelectedId)?.id ?? submissions[0]?.id ?? null); setTypes(types); setRules(rules); setDefinitions(definitions)
    }).catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : '연결 실패') }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [initialSelectedId])
  const findPerson = async (value: string) => {
    const id = ++requestId.current; setMilitaryNumber(value); setPerson(null); setMatching(!!value.trim())
    if (!value.trim()) return
    try { const person = await request<MatchedPerson>(`${API_BASE}/persons/${encodeURIComponent(value.trim())}`); if (id === requestId.current) setPerson(person) }
    catch { /* missing person is shown below */ }
    finally { if (id === requestId.current) setMatching(false) }
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!file || !type || matching || (militaryNumber.trim() && !person)) return
    setBusy(true); setError(''); setNotice('')
    let saved: Submission | null = null
    try {
      const form = new FormData(); form.append('file', file); form.append('application_type', type)
      if (person) { form.append('military_number', person.military_number); form.append('applicant_name', person.name) }
      const uploaded = await request<Submission>(`${CLASSIFIER_BASE}/submissions`, { method: 'POST', body: form }); saved = uploaded
      setSelectedId(uploaded.id); setItems(prev => [uploaded, ...prev]); setFile(null); if (fileInput.current) fileInput.current.value = ''
    } catch (e) { setError(`${saved ? '문서는 저장되었습니다. 목록에서 연결·검증을 다시 시도할 수 있습니다. ' : ''}${e instanceof Error ? e.message : '처리 실패'}`) }
    finally { setBusy(false); if (saved) { notifyReviewChanged(); try { await refresh() } catch { /* retain saved submission */ } } }
  }
  return <div className="review-ai-module">
    <header className="review-ai-top"><div><h2>서류 AI 판정</h2><p>신청 유형에 따라 PDF를 읽고, 근거와 관련 조항을 확인합니다.</p></div><button type="button" className="review-ai-secondary" disabled={busy || loading} onClick={() => void refresh().catch(e => setError(String(e)))}>목록 새로고침</button></header>
    <form className="review-ai-form" onSubmit={submit}>
      <label>군번 (선택)<small>생략하면 PDF의 성명으로 대상자를 찾습니다.</small><input disabled={busy} value={militaryNumber} onChange={e => void findPerson(e.target.value)} placeholder="군번 입력 또는 생략" /></label>
      <div className="review-ai-file-field" role="group" aria-labelledby="submission-file-label">
        <span id="submission-file-label">제출 서류</span><small>전자 PDF · 최대 20MB</small>
        <div className="review-ai-file-control">
          <button type="button" disabled={busy} onClick={() => fileInput.current?.click()}>찾아보기</button>
          <span title={file?.name} aria-live="polite">{file?.name ?? '선택된 서류 없음'}</span>
        </div>
        <input hidden ref={fileInput} disabled={busy} type="file" aria-label="제출 서류 선택" accept="application/pdf,.pdf" onChange={e => { const candidate = e.target.files?.[0] ?? null; const valid = !candidate || (candidate.name.toLowerCase().endsWith('.pdf') && candidate.size <= 20 * 1024 * 1024); setFile(valid ? candidate : null); setError(valid ? '' : '20MB 이하의 PDF를 선택하세요.'); if (!valid) e.target.value = '' }} />
      </div>
      <label>신청 유형<small>신청한 항목을 선택하세요.</small><select disabled={busy || loading} required value={type} onChange={e => setType(e.target.value)}><option value="">신청 유형 선택 ▼</option>{['statutory.', 'policy.', 'postponement.'].map((prefix, i) => <optgroup key={prefix} label={['법규보류', '방침보류', '연기'][i]}>{types.filter(t => t.id.startsWith(prefix)).map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</optgroup>)}</select></label>
      <div className={`review-ai-match ${person ? 'matched' : ''}`}>{matching ? '군번 조회 중…' : person ? `확인됨: ${person.name} · ${person.military_number} · ${person.branch}` : militaryNumber.trim() ? '등록된 군번을 확인하세요.' : 'PDF에서 추출한 성명과 정확히 일치하는 인원이 한 명이면 자동 연결합니다.'}</div>
      <div className="review-ai-form-actions"><span>{busy ? '문서를 업로드하고 있습니다.' : file?.name ?? 'PDF 파일을 선택하세요.'}</span><button disabled={busy || matching || !file || (!!militaryNumber.trim() && !person) || !type} type="submit">{busy ? '업로드 중…' : 'PDF 업로드 및 AI 분석'}</button></div>
    </form>
    {error && <p role="alert" className="review-ai-feedback error">{error}</p>}{notice && <p role="status" className="review-ai-feedback">{notice}</p>}
    <div className="review-ai-layout"><section className="review-ai-list"><header><h3>제출 목록</h3><span>분석중 {items.filter(i => ['queued', 'analyzing'].includes(i.analysis_state ?? '')).length}건</span></header><div className="review-ai-list-scroll">{loading ? <p className="review-ai-empty">불러오는 중…</p> : !items.length ? <p className="review-ai-empty">제출된 PDF가 없습니다.</p> : items.map(item => <div key={item.id} className={`review-ai-item ${item.id === selectedId ? 'selected' : ''}`}>
      <button className="review-ai-select-document" type="button" onClick={() => setSelectedId(item.id)}><strong>{item.applicant_name || '성명 확인 중'}</strong><small>{item.filename}</small>{item.status === 'approved' && <small>승인: {formatApprovalTime(item.approved_at ?? item.decided_at)} (한국시간)</small>}</button>
      <div className="review-ai-job-actions">{['queued', 'analyzing'].includes(item.analysis_state ?? '') && <button type="button" className="review-ai-cancel" onClick={() => void request<Submission>(`${CLASSIFIER_BASE}/submissions/${item.id}/cancel`, jsonRequest('POST', {})).then(() => refresh()).catch(e => setError(String(e)))}>취소</button>}
      {analysisComplete(item) && <button type="button" className="review-ai-secondary" onClick={() => void request(`${CLASSIFIER_BASE}/submissions/${item.id}/reanalyze`, jsonRequest('POST', {})).then(() => { notifyReviewChanged(); return refresh() }).catch(e => setError(String(e)))}>재검토</button>}
      {(item.analysis_state === 'failed' || (item.reanalysis && item.analysis_state === 'cancelled')) && <button type="button" onClick={() => void request(`${CLASSIFIER_BASE}/submissions/${item.id}/retry`, jsonRequest('POST', {})).then(() => refresh()).catch(e => setError(String(e)))}>다시 분석</button>}
      <span className={`review-ai-status ${item.analysis_state ?? 'completed'}`}>{analysisLabel(item)}</span></div>
    </div>)}</div></section>
      {selected ? <SubmissionDetails key={selected.id} item={selected} rules={rules} definitions={definitions} refresh={refresh} /> : <section className="review-ai-detail review-ai-empty">왼쪽에서 제출 건을 선택하세요.</section>}
    </div>
  </div>
}
