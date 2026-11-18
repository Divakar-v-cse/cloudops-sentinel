import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api/client'

interface Options {
  pollMs?: number
  enabled?: boolean
}

export function useApi<T>(loader: () => Promise<T>, deps: unknown[] = [], options: Options = {}) {
  const { pollMs, enabled = true } = options
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [tick, setTick] = useState(0)
  const mounted = useRef(true)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    loaderRef
      .current()
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
        setUpdatedAt(new Date())
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled])

  useEffect(() => {
    if (!pollMs || !enabled) return
    const interval = window.setInterval(() => {
      loaderRef
        .current()
        .then((result) => {
          if (mounted.current) {
            setData(result)
            setError(null)
            setUpdatedAt(new Date())
          }
        })
        .catch(() => undefined)
    }, pollMs)
    return () => window.clearInterval(interval)
  }, [pollMs, enabled])

  const reload = useCallback(() => setTick((value) => value + 1), [])

  return { data, error, loading, reload, updatedAt }
}

export function useDebounced<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])
  return debounced
}
