export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
export const CLASSIFIER_BASE = import.meta.env.VITE_CLASSIFIER_API_BASE_URL ?? '/classifier-api'
export type Fact = { value: string | boolean | number | null; source: string }
export type Proof = { quote?: string; page?: number; source?: string; bbox?: [number, number, number, number] | null }
export type ExtractedField = { value: string | boolean | number | null; status: string; evidence: Proof[]; errors: string[] }
export type Extraction = { application_type: string; fields: Record<string, ExtractedField>; status?: string; pdf?: { pages: { number: number; width: number; height: number }[] } }
export type ReviewItem = { id: string; label: string; fields: string[]; description?: string; person_fields?: string[]; context_fields?: string[] }
export type Citation = { table: number; page: number; item: string; provision: string; page_text: string; source_url: string }
export type Check = { id: string; label: string; status: 'pass' | 'fail' | 'missing' | 'review'; message?: string; values?: Record<string, unknown>; children?: Check[]; evidence?: Proof[]; required_for_result?: boolean }
export type Verification = { result: string; result_label: string; checks: Check[]; missing_information: string[]; related_provisions: Citation[] }
export type Submission = {
  id: string; filename: string; saved_path: string; military_number: string; applicant_name: string;
  application_type: string; reason_category: string; extraction: Extraction; verification: Verification | null;
  context: Record<string, Fact>; status: 'pending' | 'approved' | 'declined'; note: string | null;
  confirmation_requested: boolean; created_at: string; decided_at: string | null; projectPostponementId?: number
  analysis_state?: 'queued' | 'analyzing' | 'completed' | 'failed' | 'cancelled'; analysis_error?: string | null;
  review_items: ReviewItem[]; review_checks: Record<string, boolean>; review_revision: number
  reanalysis?: boolean
  approved_at?: string | null
}
export type MatchedPerson = { military_number: string; name: string; branch: string; status: string; service_year: number; position?: string; mobilization_status?: string }
export type Postponement = { id: number; person_id: string; classifier_submission_id: string | null; status: string; type: string; category: string | null; reason: string; approved_at?: string | null }
export type ApplicationType = { id: string; label: string }
export type Rule = { op: string; label: string; fields?: string[]; value?: unknown; children?: Rule[] }
export type RuleCatalog = { common: Rule[]; types: Record<string, { common?: Rule[]; checks: Rule[] }> }
export type FieldDefinitions = Record<string, { label: string; type: string }>

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let message = `요청 실패 (HTTP ${response.status})`
    try { const error = await response.json(); if (typeof error.detail === 'string') message = error.detail
      else if (Array.isArray(error.detail)) message = error.detail.map((e: { msg: string }) => e.msg).join(' ')
    } catch { /* proxy response */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
export const jsonRequest = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const notifyReviewChanged = () => window.dispatchEvent(new Event('review-data-changed'))
export const pdfUrl = (id: string) => `${CLASSIFIER_BASE}/submissions/${encodeURIComponent(id)}/pdf`
export const analysisComplete = (item: Submission) => !item.analysis_state || item.analysis_state === 'completed'
export const analysisLabel = (item: Submission) => analysisComplete(item) ? '분석 완료' : item.analysis_state === 'failed' ? '분석 실패' : item.analysis_state === 'cancelled' ? '취소됨' : '분석중'
export const submissionTitle = (item: Submission) => `${item.applicant_name || '성명 확인 중'} · ${item.application_type.startsWith('postponement.') ? '연기자' : '보류자'} · ${item.reason_category}`
export function formatApprovalTime(value?: string | null): string {
  if (!value) return '기록 없음'
  // The business DB stores UTC without an offset; classifier timestamps include it.
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`)
  if (Number.isNaN(date.getTime())) return '기록 없음'
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(date)
}
export function fieldValue(submission: Submission, key: string): string {
  const value = submission.extraction.fields[key]?.value
  return value == null ? '—' : typeof value === 'boolean' ? value ? '예' : '아니오' : String(value)
}
export async function loadSubmissions(signal?: AbortSignal): Promise<Submission[]> {
  const [submissions, links] = await Promise.all([
    request<Submission[]>(`${CLASSIFIER_BASE}/submissions`, { signal }), request<Postponement[]>(`${API_BASE}/postponements`, { signal }),
  ])
  return submissions.map(item => {
    const link = links.find(link => link.classifier_submission_id === item.id)
    return { ...item, projectPostponementId: link?.id,
      approved_at: link?.approved_at ?? (item.status === 'approved' ? item.decided_at : null),
      status: link?.status === 'approved' ? 'approved' : link?.status === 'rejected' ? 'declined' : link?.status === 'pending' ? 'pending' : item.status }
  })
}
export async function linkSubmission(item: Submission): Promise<number> {
  if (!item.military_number) throw new Error('먼저 대상자를 연결하세요.')
  const linked = await request<Postponement>(`${API_BASE}/postponements`, jsonRequest('POST', {
    person_id: item.military_number, type: item.application_type.startsWith('postponement.') ? 'delay' : 'hold',
    reason: item.reason_category, category: item.application_type, source_file: item.filename, classifier_submission_id: item.id,
  }))
  notifyReviewChanged()
  return linked.id
}
export async function decide(item: Submission, decision: 'approved' | 'declined', note?: string) {
  if (!item.military_number && decision === 'declined') {
    await request(`${CLASSIFIER_BASE}/submissions/${item.id}/decision`, jsonRequest('POST', { decision, note }))
    notifyReviewChanged(); return
  }
  const id = item.projectPostponementId ?? await linkSubmission(item)
  await request(`${API_BASE}/postponements/${id}/${decision === 'approved' ? 'approve' : 'reject'}`, jsonRequest('PATCH', { note }))
  notifyReviewChanged()
}
export async function verifySubmission(item: Submission, context: Record<string, Fact>): Promise<Verification> {
  const result = !item.military_number ? await request<Verification>(`${CLASSIFIER_BASE}/submissions/${item.id}/verify`, jsonRequest('POST', { context })) : await request<Verification>(`${API_BASE}/postponements/verify`, jsonRequest('POST', {
    person_id: item.military_number, submission_id: item.id, documents: [item.extraction], context,
  }))
  notifyReviewChanged()
  return result
}
