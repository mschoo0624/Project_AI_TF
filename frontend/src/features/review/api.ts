import { API_BASE, CLASSIFIER_BASE, decide, fieldValue, jsonRequest, loadSubmissions, notifyReviewChanged, pdfUrl, request,
  type MatchedPerson, type Postponement, type Submission, type Verification } from './classifierApi'

export type Document = {
  id: string
  type: string
  issued: string
  expiry: string
  status: '검토대기' | '승인' | '반려' | '확인요청'
  owner: string
  file_path: string | null
  verify_number: string | null
  reject_reason: string | null
  verify_reason: string | null
  reviewer: string | null
  reviewed_at: string | null
  verification?: Verification | null
}

export type Person = {
  person_id: string
  name: string
  occupation: string | null
  branch: string
  discharge_year: number | null
  mobilization_designated: boolean
  resource_year: number | null
  classification: string
  exemption_type: string | null
  rule_code: string | null
  mobilization: string
  training: string
  hours: number | null
  makeup_hours: number | null
  carryover: number | null
  total_hours: number | null
  reasons: string[]
  alerts: string[]
  pending_count: number
  documents: Document[]
}

export type QueueItem = Document & {
  application_date?: string
  person_id: string
  person_name: string
  occupation: string | null
  waiting_days: number
  current_classification: string
  if_accepted_classification: string
}

export type ReasonOption = {
  code: string
  label: string
  can_resubmit?: boolean
  message?: string
}

export type Bootstrap = {
  as_of: string
  training_date: string
  reject_reasons: ReasonOption[]
  verify_reasons: ReasonOption[]
  people: Person[]
  queue: QueueItem[]
}

export function reviewReason(item: QueueItem): string {
  const classification = item.if_accepted_classification || item.current_classification || ''
  if (classification.includes('연기')) return '연기자'
  if (classification.includes('보류') || classification.includes('후순위')) return '보류자'
  return item.type
}

export function countReviewDocuments(queue: QueueItem[]): number {
  return new Set(queue.filter(item => item.status === '검토대기' || item.status === '확인요청').map(item => item.id)).size
}

function classification(type: string): string {
  return type.startsWith('statutory.') ? '법규보류' : type.startsWith('policy.') ? '방침보류' : type.startsWith('postponement.') || type === 'delay' ? '연기' : '보류'
}
function toDocument(item: Submission): Document {
  return { id: item.id, type: fieldValue(item, 'document_title'), issued: fieldValue(item, 'issued_on'), expiry: '—',
    status: item.status === 'approved' ? '승인' : item.status === 'declined' ? '반려' : item.confirmation_requested ? '확인요청' : '검토대기',
    owner: item.reason_category, file_path: pdfUrl(item.id), verify_number: item.extraction.fields.document_number?.value ? String(item.extraction.fields.document_number.value) : null,
    reject_reason: item.status === 'declined' ? item.note : null, verify_reason: item.confirmation_requested ? item.note : null,
    reviewer: null, reviewed_at: item.decided_at, verification: item.verification }
}
export async function fetchBootstrap(signal?: AbortSignal): Promise<Bootstrap> {
  const [submissions, allRecords] = await Promise.all([loadSubmissions(signal), request<Postponement[]>(`${API_BASE}/postponements`, { signal })])
  const records = allRecords.filter(r => submissions.some(s => s.id === r.classifier_submission_id))
  const ids = [...new Set([...submissions.map(s => s.military_number), ...records.map(r => r.person_id)])].filter(Boolean)
  const matches = await Promise.all(ids.map(async id => {
    const response = await fetch(`${API_BASE}/persons/${encodeURIComponent(id)}`, { signal })
    if (response.status === 404) return [id, null] as const
    if (!response.ok) throw new Error('등록 인원을 불러오지 못했습니다.')
    return [id, await response.json() as MatchedPerson] as const
  }))
  const byId = new Map(matches)
  const people: Person[] = ids.map(id => {
    const person = byId.get(id)
    const docs = submissions.filter(s => s.military_number === id)
    const approved = records.filter(r => r.person_id === id && r.status === 'approved')
    return { person_id: id, name: person?.name ?? docs[0]?.applicant_name ?? id, occupation: person?.position ?? null,
      branch: person?.branch ?? '—', discharge_year: null, mobilization_designated: ['지정', '동원지정', 'designated'].includes(person?.mobilization_status ?? ''),
      resource_year: person?.service_year ?? null, classification: approved.length ? classification(approved[0].category ?? approved[0].type) : '일반',
      exemption_type: null, rule_code: approved[0]?.category ?? null, mobilization: person?.mobilization_status ?? '—', training: '범위 확인 필요',
      hours: null, makeup_hours: null, carryover: null, total_hours: null,
      reasons: approved.map(r => `승인된 신청: ${r.reason}`), alerts: approved.length ? ['승인 기록 기준입니다. 실제 적용 기간과 훈련 범위를 확인하세요.'] : [],
      pending_count: docs.filter(s => s.status === 'pending').length, documents: docs.map(toDocument) }
  })
  const queue: QueueItem[] = submissions.filter(s => s.status === 'pending').map(s => ({ ...toDocument(s),
    person_id: s.military_number || '대상자 미연결', person_name: byId.get(s.military_number)?.name ?? (s.applicant_name || '성명 미확인'),
    occupation: byId.get(s.military_number)?.position ?? null, waiting_days: Math.max(0, Math.floor((Date.now() - Date.parse(s.created_at)) / 86400000)),
    current_classification: people.find(p => p.person_id === s.military_number)?.classification ?? '일반',
    if_accepted_classification: classification(s.application_type), application_date: s.created_at }))
  return { as_of: new Date().toISOString(), training_date: '—', people, queue,
    reject_reasons: [{ code: 'INSUFFICIENT', label: '근거 자료 부족', can_resubmit: true, message: '필요한 증빙 자료를 보완해 주세요.' }, { code: 'NOT_MET', label: '요건 불충족', can_resubmit: false }, { code: 'OTHER', label: '기타', can_resubmit: true }],
    verify_reasons: [{ code: 'DOCUMENT', label: '발급기관·문서 진위 확인' }, { code: 'EVIDENCE', label: '추가 근거 확인' }, { code: 'OTHER', label: '기타' }] }
}
async function findSubmission(id: string): Promise<Submission> {
  const item = (await loadSubmissions()).find(s => s.id === id)
  if (!item) throw new Error('제출 건을 찾을 수 없습니다. 목록을 새로고침하세요.')
  return item
}
export async function acceptDocument(id: string, _payload: { doc_type?: string; issued_date?: string }) {
  void _payload
  await decide(await findSubmission(id), 'approved'); return { ok: true }
}
export async function rejectDocument(id: string, reason: string, message?: string) {
  await decide(await findSubmission(id), 'declined', message ?? reason); return { ok: true }
}
export async function verifyDocument(id: string, reason: string, message?: string) {
  await request(`${CLASSIFIER_BASE}/submissions/${encodeURIComponent(id)}/request-confirmation`, jsonRequest('POST', { note: message ?? reason }))
  notifyReviewChanged(); return { ok: true }
}
