// 데이터 소스.
//
// 지금은 public/data.json (export_frontend.py 가 생성) 을 그대로 읽습니다.
// 실제 백엔드가 준비되면 이 파일만 바꾸면 됩니다 — 화면 컴포넌트는
// Bootstrap 타입만 알고 출처를 모르므로 App.tsx 는 손댈 필요 없습니다.
//
//   1. DATA_SOURCE 를 'api' 로 변경
//   2. vite.config.ts 의 proxy 를 실제 백엔드 주소로 확인
//   3. fetchBootstrap() 의 API 분기에서 엔드포인트 경로만 맞추기
//   4. acceptDocument / rejectDocument / verifyDocument 를 실제
//      PATCH 요청으로 바꾸기 (지금은 콘솔 로그만 남기는 스텁입니다)

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
}

export type Person = {
  person_id: string
  name: string
  occupation: string | null
  branch: string
  discharge_year: number
  mobilization_designated: boolean
  resource_year: number
  classification: string
  exemption_type: string | null
  rule_code: string | null
  mobilization: string
  training: string
  hours: number
  makeup_hours: number
  carryover: number
  total_hours: number
  reasons: string[]
  alerts: string[]
  pending_count: number
  documents: Document[]
}

export type QueueItem = Document & {
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
  return new Set(queue.filter(item => item.status === '검토대기').map(item => item.id)).size
}

const DATA_SOURCE: 'static' | 'api' = 'static'
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export async function fetchBootstrap(signal?: AbortSignal): Promise<Bootstrap> {
  if (DATA_SOURCE === 'api') {
    const res = await fetch(`${API_BASE}/exemptions/bootstrap`, { signal, cache: 'no-store' })
    if (!res.ok) throw new Error(`백엔드 응답 오류 (${res.status})`)
    return res.json() as Promise<Bootstrap>
  }

  const res = await fetch('/data.json', { signal, cache: 'no-store' })
  if (!res.ok) throw new Error('data.json 을 불러오지 못했습니다')
  return res.json() as Promise<Bootstrap>
}

// 아래 세 함수는 지금 스텁입니다. 실제 백엔드가 생기면 PATCH 요청으로
// 바꾸고, 화면에서는 반환값으로 로컬 상태만 갱신하면 됩니다.
export async function acceptDocument(id: string, payload: { doc_type?: string; issued_date?: string }) {
  console.log('[stub] accept', id, payload)
  await new Promise((r) => setTimeout(r, 150))
  return { ok: true }
}

export async function rejectDocument(id: string, reason: string, message?: string) {
  console.log('[stub] reject', id, reason, message)
  await new Promise((r) => setTimeout(r, 150))
  return { ok: true }
}

export async function verifyDocument(id: string, reason: string, message?: string) {
  console.log('[stub] verify', id, reason, message)
  await new Promise((r) => setTimeout(r, 150))
  return { ok: true }
}
