import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { API_BASE, CLASSIFIER_BASE, decide, fieldValue, jsonRequest, linkSubmission, loadSubmissions, notifyReviewChanged, pdfUrl, request, verifySubmission,
  type ApplicationType, type Fact, type FieldDefinitions, type MatchedPerson, type Rule, type RuleCatalog, type Submission } from './classifierApi'
import VerificationResult from './VerificationResult'
import './PostponementModule.css'

const statusLabel = (item: Submission) => item.status === 'approved' ? '승인' : item.status === 'declined' ? '반려' : item.confirmation_requested ? '확인요청' : '검토대기'
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
  const [note, setNote] = useState(item.note ?? '')
  const [identityNumber, setIdentityNumber] = useState('')
  const inputs = rules ? contextInputs([...rules.common, ...(rules.types[item.application_type]?.checks ?? [])]) : []
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
  return <section className="review-ai-detail" aria-label="서류 분석 및 검증 결과">
    <div className="review-ai-heading"><h3>AI 분석 결과</h3><span className={`review-ai-status ${item.status}`}>{statusLabel(item)}</span></div>
    <p className="review-ai-subtitle">{item.applicant_name} · {item.military_number}</p>
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
      <label className="review-decision-note">검토 의견<textarea disabled={busy} value={note} maxLength={2000} onChange={e => setNote(e.target.value)} placeholder="승인·반려 의견 또는 추가 확인할 내용" /></label>
      {!item.projectPostponementId && <p className="review-ai-alert">업무 신청 연결이 필요합니다. 승인·반려 시 연결을 다시 시도합니다.</p>}
      <div className="review-ai-actions"><button type="button" disabled={busy} onClick={() => void run(() => decide(item, 'approved', note))}>승인</button><button type="button" className="reject" disabled={busy} onClick={() => void run(() => decide(item, 'declined', note))}>반려</button><button type="button" className="reject" disabled={busy || !note.trim()} onClick={() => void run(async () => { await request(`${CLASSIFIER_BASE}/submissions/${item.id}/request-confirmation`, jsonRequest('POST', { note })); notifyReviewChanged() })}>확인요청</button></div>
    </>}
    {item.status !== 'pending' && item.note && <p className="review-ai-notice">검토 의견: {item.note}</p>}
    {error && <p role="alert" className="review-ai-feedback error">{error}</p>}
  </section>
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
    const [loaded, types, rules, definitions] = await Promise.all([loadSubmissions(), request<ApplicationType[]>(`${CLASSIFIER_BASE}/application-types`), request<RuleCatalog>(`${CLASSIFIER_BASE}/verification-rules`), request<FieldDefinitions>(`${CLASSIFIER_BASE}/field-definitions`)])
    setItems(loaded); setTypes(types); setRules(rules); setDefinitions(definitions)
    setSelectedId(current => loaded.some(item => item.id === current) ? current : loaded[0]?.id ?? null)
  }, [])
  useEffect(() => {
    let cancelled = false
    Promise.all([loadSubmissions(), request<ApplicationType[]>(`${CLASSIFIER_BASE}/application-types`), request<RuleCatalog>(`${CLASSIFIER_BASE}/verification-rules`), request<FieldDefinitions>(`${CLASSIFIER_BASE}/field-definitions`)]).then(([submissions, types, rules, definitions]) => {
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
      const resolved = uploaded.military_number ? uploaded : (await request<{ submission: Submission }>(`${API_BASE}/postponements/resolve-applicant`, jsonRequest('POST', { submission_id: uploaded.id }))).submission
      if (!resolved.military_number) { await verifySubmission(resolved, {}); setNotice('PDF 분석·검증 결과를 저장했습니다. 이름으로 대상자를 확정하지 못했습니다. 상세 화면에서 군번으로 연결하세요.'); return }
      await linkSubmission(resolved); await verifySubmission(resolved, {})
      setNotice('PDF 추출과 근거 검증을 완료했습니다. 추가 확인 정보가 있으면 입력 후 재검증할 수 있습니다.')
    } catch (e) { setError(`${saved ? '문서는 저장되었습니다. 목록에서 연결·검증을 다시 시도할 수 있습니다. ' : ''}${e instanceof Error ? e.message : '처리 실패'}`) }
    finally { if (saved) { notifyReviewChanged(); try { await refresh() } catch { /* retain saved submission */ } } setBusy(false) }
  }
  return <div className="review-ai-module">
    <header className="review-ai-top"><div><h2>서류 AI 판정</h2><p>신청 유형에 따라 PDF를 읽고, 근거와 관련 조항을 확인합니다.</p></div><button type="button" className="review-ai-secondary" disabled={busy || loading} onClick={() => void refresh().catch(e => setError(String(e)))}>목록 새로고침</button></header>
    <form className="review-ai-form" onSubmit={submit}>
      <label>군번 (선택)<small>생략하면 PDF의 성명으로 대상자를 찾습니다.</small><input disabled={busy} value={militaryNumber} onChange={e => void findPerson(e.target.value)} placeholder="군번 입력 또는 생략" /></label>
      <label>신청 유형<small>신청한 항목을 선택하세요.</small><select disabled={busy || loading} required value={type} onChange={e => setType(e.target.value)}><option value="">신청 유형 선택 ▼</option>{['statutory.', 'policy.', 'postponement.'].map((prefix, i) => <optgroup key={prefix} label={['법규보류', '방침보류', '연기'][i]}>{types.filter(t => t.id.startsWith(prefix)).map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</optgroup>)}</select></label>
      <label>제출 서류<small>전자 PDF · 최대 20MB</small><input ref={fileInput} disabled={busy} type="file" accept="application/pdf,.pdf" onChange={e => { const candidate = e.target.files?.[0] ?? null; const valid = !candidate || (candidate.name.toLowerCase().endsWith('.pdf') && candidate.size <= 20 * 1024 * 1024); setFile(valid ? candidate : null); setError(valid ? '' : '20MB 이하의 PDF를 선택하세요.') }} /></label>
      <div className={`review-ai-match ${person ? 'matched' : ''}`}>{matching ? '군번 조회 중…' : person ? `확인됨: ${person.name} · ${person.military_number} · ${person.branch}` : militaryNumber.trim() ? '등록된 군번을 확인하세요.' : 'PDF에서 추출한 성명과 정확히 일치하는 인원이 한 명이면 자동 연결합니다.'}</div>
      <div className="review-ai-form-actions"><span>{busy ? '문서를 분석하고 있습니다. 유형별 항목 수에 따라 수 분 걸릴 수 있습니다.' : file?.name ?? 'PDF 파일을 선택하세요.'}</span><button disabled={busy || matching || !file || (!!militaryNumber.trim() && !person) || !type} type="submit">{busy ? '처리 중…' : 'PDF 업로드 및 AI 분석'}</button></div>
    </form>
    {error && <p role="alert" className="review-ai-feedback error">{error}</p>}{notice && <p role="status" className="review-ai-feedback">{notice}</p>}
    <div className="review-ai-layout"><section className="review-ai-list"><header><h3>제출 목록</h3><span>검토대기 {items.filter(i => i.status === 'pending').length}건</span></header><div className="review-ai-list-scroll">{loading ? <p className="review-ai-empty">불러오는 중…</p> : !items.length ? <p className="review-ai-empty">제출된 PDF가 없습니다.</p> : items.map(item => <button key={item.id} disabled={busy} type="button" className={`review-ai-item ${item.id === selectedId ? 'selected' : ''}`} onClick={() => setSelectedId(item.id)}><strong>{item.applicant_name}</strong><span className={`review-ai-status ${item.status}`}>{statusLabel(item)}</span><small>{item.military_number} · {item.filename}</small></button>)}</div></section>
      {selected ? <SubmissionDetails key={selected.id} item={selected} rules={rules} definitions={definitions} refresh={refresh} /> : <section className="review-ai-detail review-ai-empty">왼쪽에서 제출 건을 선택하세요.</section>}
    </div>
  </div>
}
