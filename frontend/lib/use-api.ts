"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { api } from "./api"

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(path !== null)
  const seq = useRef(0)

  const load = useCallback(async () => {
    if (path === null) return
    const mine = ++seq.current
    setLoading(true)
    setError(null)
    try {
      const value = await api<T>(path)
      if (mine === seq.current) setData(value)
    } catch (e) {
      if (mine === seq.current) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (mine === seq.current) setLoading(false)
    }
  }, [path])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetching on mount/path change
    void load()
  }, [load])

  return { data, error, loading, reload: load, setData }
}
