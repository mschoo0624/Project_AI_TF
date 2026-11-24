import { authenticatedFetch, apiBase } from '../training/auth'

export async function prosecutionRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await authenticatedFetch(`${apiBase()}${path}`, init)
  } catch (cause) {
    if (init.signal?.aborted) throw cause
    throw new Error('서버에 연결할 수 없습니다. 백엔드 실행 상태를 확인한 뒤 다시 시도하세요.')
  }
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null
    let message = typeof detail === 'string' ? detail : '고발장 요청을 처리하지 못했습니다.'
    if (Array.isArray(detail)) message = detail.map(item => `${item.loc?.slice(1).join('.') ?? ''}: ${item.msg ?? '입력값을 확인하세요.'}`).join('\n')
    if (response.status === 404 && (!detail || detail === 'Not Found')) message = '고발장 API를 찾을 수 없습니다. 변경된 코드로 백엔드를 재시작하세요.'
    else if (response.status === 401) message = '로그인이 필요합니다. 다시 로그인하세요.'
    else if (response.status === 403) message = '고발장 요청을 처리할 권한이 없습니다.'
    else if ([502, 503, 504].includes(response.status)) message = '백엔드에 연결하지 못했습니다. 서버 실행 상태를 확인하세요.'
    throw new Error(`${message} (HTTP ${response.status})`)
  }
  if (data === null) throw new Error('서버가 올바른 JSON 응답을 반환하지 않았습니다. API 연결 주소를 확인하세요.')
  return data as T
}

export const errorMessage = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)
export const jsonBody = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const documentTime = (value: string) => new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'medium', hour12: false,
}).format(new Date(value))
