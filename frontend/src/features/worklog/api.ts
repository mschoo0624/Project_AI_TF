import { apiBase, authenticatedFetch } from '../training/auth'

export type WorkLogPerson = { military_number?: string; name?: string; branch?: string; rank?: string; unit?: string }
export type WorkLogEvent = {
  id: number; occurred_at: string; category: string; action: string; summary: string; actor: string
  people: WorkLogPerson[]; details: Record<string, unknown>
}
export type WorkLogRevision = { revision: number; confirmed_at: string; confirmed_by: string; event_count: number; last_event_id: number }
export type WorkLogSummary = {
  date: string; event_count: number; revision: number; last_event_id: number
  has_unconfirmed_changes: boolean; confirmed_at: string | null
}
export type WorkLogDetail = {
  date: string; events: WorkLogEvent[]; notes: string; revisions: WorkLogRevision[]
  last_event_id: number; has_unconfirmed_changes: boolean
}

export class WorkLogError extends Error {
  readonly status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

export async function workLogRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await authenticatedFetch(`${apiBase()}/worklogs${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new WorkLogError(typeof body?.detail === 'string' ? body.detail : `업무일지를 불러오지 못했습니다. (${response.status})`, response.status)
  }
  return response.json() as Promise<T>
}

export async function workLogPdf(path: string, signal: AbortSignal, init: RequestInit = {}): Promise<Blob> {
  const response = await authenticatedFetch(`${apiBase()}/worklogs${path}`, { ...init, signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new WorkLogError(typeof body?.detail === 'string' ? body.detail : `PDF를 불러오지 못했습니다. (${response.status})`, response.status)
  }
  return response.blob()
}

export const categoryNames: Record<string, string> = {
  transfer_in: '전입', transfer_out: '전출', travel: '출국·귀국', postponement: '보류·연기',
  personnel: '인원', assignment: '전투편성', training: '교육훈련', prosecution: '고발장', organization: '편제',
}
export const errorText = (error: unknown) => error instanceof Error ? error.message : '업무일지 처리에 실패했습니다.'
export const displayDate = (date: string) => date.replaceAll('-', '.')
export const displayTime = (value: string) => new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
}).format(new Date(value))
export const displayTimestamp = (value: string) => new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour12: false, hour: '2-digit', minute: '2-digit',
}).format(new Date(value))
