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

export function supportNavigation(area: 'administracao' | 'plataforma') {
  return area === 'plataforma'
    ? [
        { key: 'overview', label: 'Visão geral', to: '/app/plataforma', symbol: '⌂' },
        {
          key: 'condominiums',
          label: 'Condomínios',
          to: '/app/plataforma/condominios',
          symbol: '▤',
        },
        { key: 'support', label: 'Fila de suporte', to: '/app/plataforma/suporte', symbol: '☏' },
        {
          key: 'announcements',
          label: 'Comunicados',
          to: '/app/plataforma/comunicados',
          symbol: '✉',
        },
      ]
    : [
        { key: 'overview', label: 'Visão geral', to: '/app/administracao', symbol: '⌂' },
        {
          key: 'employees',
          label: 'Funcionários',
          to: '/app/administracao/funcionarios',
          symbol: '♙',
        },
        { key: 'notices', label: 'Avisos', to: '/app/administracao/avisos', symbol: '◇' },
        { key: 'support', label: 'Suporte', to: '/app/administracao/suporte', symbol: '☏' },
        {
          key: 'announcements',
          label: 'Comunicados',
          to: '/app/administracao/comunicados',
          symbol: '✉',
        },
        {
          key: 'packageReport',
          label: 'Relatório de encomendas',
          to: '/app/administracao/encomendas/relatorio',
          symbol: '▣',
        },
      ]
}
