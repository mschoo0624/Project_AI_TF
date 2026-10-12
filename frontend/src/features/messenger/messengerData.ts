export type Message = { id: number; from: 'me' | 'them'; text: string; sentAt: number }
export type Conversation = { id: number; name: string; unit: string; unread: number; messages: Message[] }

const at = (month: number, day: number, hour: number, minute: number) =>
  new Date(2026, month - 1, day, hour, minute).getTime()

// 예시 데이터 (메신저 API가 생기면 교체)
export const initialConversations: Conversation[] = [
  {
    id: 1, name: '홍길동', unit: '디지털전략팀', unread: 1,
    messages: [
      { id: 1, from: 'them', text: '안녕하세요, 10월 5일 1형 훈련 일정 확인하셨나요?', sentAt: at(10, 7, 9, 12) },
      { id: 2, from: 'me', text: '네, 확인했습니다. 대상자 명단 정리 중입니다.', sentAt: at(10, 7, 9, 13) },
      { id: 3, from: 'them', text: '감사합니다. 정리되면 공유 부탁드려요.', sentAt: at(10, 7, 9, 15) },
    ],
  },
  {
    id: 2, name: '김민수', unit: '교육훈련계', unread: 0,
    messages: [
      { id: 1, from: 'me', text: '홍보메일 발송 완료했습니다. 대상자 134명입니다.', sentAt: at(9, 28, 14, 30) },
      { id: 2, from: 'them', text: '확인했습니다. 수고하셨습니다.', sentAt: at(9, 28, 14, 41) },
    ],
  },
  {
    id: 3, name: '박지은', unit: '인사과', unread: 0,
    messages: [
      { id: 1, from: 'them', text: '전출자 3명 명단 보내드렸습니다.', sentAt: at(9, 25, 11, 5) },
      { id: 2, from: 'me', text: '받았습니다. 반영해 두겠습니다.', sentAt: at(9, 25, 11, 20) },
    ],
  },
]

const pad = (value: number) => String(value).padStart(2, '0')

export const formatClock = (ts: number) => {
  const date = new Date(ts)
  const hour = date.getHours()
  return `${hour < 12 ? '오전' : '오후'} ${hour % 12 || 12}:${pad(date.getMinutes())}`
}

export const formatDay = (ts: number) => {
  const date = new Date(ts)
  return `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일`
}

// 목록 오른쪽 시간: 오늘이면 시각, 아니면 날짜
export const formatListTime = (ts: number) => {
  const date = new Date(ts)
  const now = new Date()
  const sameDay = date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate()
  return sameDay ? formatClock(ts) : `${date.getMonth() + 1}월 ${date.getDate()}일`
}

// 홈 연락 알림용: 10월 7일 09:15
export const formatAlertTime = (ts: number) => {
  const date = new Date(ts)
  return `${date.getMonth() + 1}월 ${date.getDate()}일 ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
