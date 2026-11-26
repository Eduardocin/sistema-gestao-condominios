import { useCallback, useEffect, useState } from 'react'
import { occurrenceErrorMessage } from './occurrence-errors'

/**
 * Carrega dados com cancelamento. Trocar `load` (filtro, página, ocorrência) volta a
 * "carregando"; `reload` mantém os dados atuais na tela até a resposta nova chegar,
 * para o detalhe não sumir (nem perder o foco) depois de responder ou resolver.
 */
export function useRefreshableQuery<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{ load: typeof load; data?: T; error?: string }>()

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ load, data })
      },
      (error: unknown) => {
        if (!controller.signal.aborted)
          setResult({ load, error: occurrenceErrorMessage(error, 'carregar') })
      },
    )
    return () => controller.abort()
  }, [load, revision])

  const reload = useCallback(() => setRevision((value) => value + 1), [])
  return { result: result?.load === load ? result : undefined, reload }
}
