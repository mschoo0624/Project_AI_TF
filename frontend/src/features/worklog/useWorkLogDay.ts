import { useEffect } from 'react'
import { apiBase, authenticatedFetch } from '../training/auth'

export function useWorkLogDay() {
  useEffect(() => {
    const controller = new AbortController()
    let createdDay = ''
    let pending = false
    const ensureDay = async () => {
      const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' }).format(new Date())
      if (pending || createdDay === day) return
      pending = true
      try {
        const response = await authenticatedFetch(`${apiBase()}/worklogs/today`, { signal: controller.signal })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        createdDay = day
      } catch (error) {
        if (!controller.signal.aborted) console.error('오늘 업무일지 생성 실패:', error)
      } finally { pending = false }
    }
    void ensureDay()
    const timer = window.setInterval(() => { void ensureDay() }, 60_000)
    window.addEventListener('focus', ensureDay)
    return () => {
      controller.abort()
      window.clearInterval(timer)
      window.removeEventListener('focus', ensureDay)
    }
  }, [])
}
