import { useCallback, useEffect, useRef, useState } from 'react'
import { defaultDashboardConfig, localDashboardStore } from './dashboardLayout'
import type { DashboardConfig } from './dashboardLayout'

// 저장소를 바꾸려면(예: 백엔드) 여기의 store만 교체합니다.
const store = localDashboardStore

export function useDashboardConfig(userKey: string) {
  const [config, setConfig] = useState<DashboardConfig>(() => store.load(userKey) ?? defaultDashboardConfig())
  const dirty = useRef(false)
  const update = useCallback((change: (current: DashboardConfig) => DashboardConfig) => {
    dirty.current = true
    setConfig(change)
  }, [])
  const reset = useCallback(() => {
    dirty.current = true
    setConfig(defaultDashboardConfig())
  }, [])
  useEffect(() => {
    if (dirty.current) store.save(userKey, config)
  }, [userKey, config])
  return { config, update, reset }
}
