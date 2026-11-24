import { useCallback, useEffect, useRef, useState } from 'react'
import { defaultSchedules, localScheduleStore } from './scheduleStore'
import type { Schedule } from './scheduleStore'

// 저장소를 바꾸려면(예: 백엔드) 여기의 store만 교체합니다.
const store = localScheduleStore

export function useSchedules(userKey: string) {
  const [schedules, setSchedulesState] = useState<Schedule[]>(() => store.load(userKey) ?? defaultSchedules())
  const dirty = useRef(false)
  const setSchedules = useCallback((change: (current: Schedule[]) => Schedule[]) => {
    dirty.current = true
    setSchedulesState(change)
  }, [])
  useEffect(() => {
    if (dirty.current) store.save(userKey, schedules)
  }, [userKey, schedules])
  return [schedules, setSchedules] as const
}
