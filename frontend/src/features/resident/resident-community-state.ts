import { useEffect, useState } from 'react'
import { communityError } from './resident-community-api'

export function useCommunityQuery<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{
    load: typeof load
    revision: number
    data?: T
    error?: string
  }>()

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ load, revision, data })
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setResult({ load, revision, error: communityError(error) })
      },
    )
    return () => controller.abort()
  }, [load, revision])

  return {
    result: result?.load === load && result.revision === revision ? result : undefined,
    reload: () => setRevision((value) => value + 1),
  }
}

export function communityDate(date: string) {
  return new Date(`${date}T12:00:00`).toLocaleDateString('pt-BR')
}
