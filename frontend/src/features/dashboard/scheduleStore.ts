// 주요 일정 저장소. 지금은 localStorage(아이디별)이고, 백엔드 저장으로 바꿀 때 이 객체만 교체하면 됩니다.
// 일정 날짜는 연도를 포함한 YYYY-MM-DD, 색상은 중요도(높음/보통/낮음)에 따라 개인이 고릅니다.
export type ScheduleColor = 'high' | 'normal' | 'low'
export type Schedule = { id: number; date: string; title: string; color: ScheduleColor }

export const defaultSchedules = (): Schedule[] => [
  { id: 1, date: '2026-01-14', title: '동원훈련 1형 예정', color: 'high' },
  { id: 2, date: '2026-01-15', title: '월 중간 결산', color: 'normal' },
]

export type ScheduleStore = {
  load(userKey: string): Schedule[] | null
  save(userKey: string, schedules: Schedule[]): void
}
const storageKey = (userKey: string) => `project-ai-tf.schedules.${userKey}`

function sanitize(raw: unknown): Schedule[] | null {
  if (!Array.isArray(raw)) return null
  const colors: ScheduleColor[] = ['high', 'normal', 'low']
  return raw.flatMap((item): Schedule[] => {
    if (!item || typeof item !== 'object') return []
    const { id, date, title, color } = item as Partial<Schedule>
    if (typeof id !== 'number' || typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date) || typeof title !== 'string') return []
    return [{ id, date, title, color: colors.includes(color as ScheduleColor) ? color as ScheduleColor : 'normal' }]
  })
}

export const localScheduleStore: ScheduleStore = {
  load(userKey) {
    try {
      const text = window.localStorage.getItem(storageKey(userKey))
      return text ? sanitize(JSON.parse(text)) : null
    } catch { return null }
  },
  save(userKey, schedules) {
    try { window.localStorage.setItem(storageKey(userKey), JSON.stringify(schedules)) } catch { /* 저장 실패는 무시 */ }
  },
}
