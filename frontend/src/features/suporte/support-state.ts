import { useEffect, useState } from 'react'
import { supportError } from './suporte-api.ts'

export function useSupportQuery<T>(load: (signal: AbortSignal) => Promise<T>) {
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
        if (!controller.signal.aborted) setResult({ load, revision, error: supportError(error) })
      },
    )
    return () => controller.abort()
  }, [load, revision])

  return {
    result: result?.load === load && result.revision === revision ? result : undefined,
    reload: () => setRevision((value) => value + 1),
  }
}

export const dateTime = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'America/Sao_Paulo',
})
