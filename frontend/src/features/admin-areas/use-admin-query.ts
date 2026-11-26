import { useCallback, useEffect, useState } from 'react'
import { adminErrorMessage } from './admin-errors'

/**
 * Carrega dados com cancelamento: troca de filtro ou de página aborta a requisição anterior,
 * e uma resposta atrasada nunca sobrescreve a atual. `load` precisa vir de um useCallback.
 */
export function useAdminQuery<T>(load: (signal: AbortSignal) => Promise<T>) {
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
        if (!controller.signal.aborted)
          setResult({ load, revision, error: adminErrorMessage(error, 'carregar') })
      },
    )
    return () => controller.abort()
  }, [load, revision])

  const reload = useCallback(() => setRevision((value) => value + 1), [])
  // Resultado de outra chave ou revisão conta como "carregando".
  return {
    result: result?.load === load && result.revision === revision ? result : undefined,
    reload,
  }
}
