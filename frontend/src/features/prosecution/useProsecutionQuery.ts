import { useEffect, useState } from 'react'
import { errorMessage, prosecutionRequest } from './api'

export function useProsecutionQuery<T>(path: string, revision = 0) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    prosecutionRequest<T>(path, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setData(result) })
      .catch(cause => { if (!controller.signal.aborted) setError(errorMessage(cause)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [path, revision])

  return { data, loading, error }
}
