import { isAxiosError } from 'axios'
import type { AxiosInstance } from 'axios'

export interface AuditReference {
  id: string
  nome: string
}

export interface AuditRecord {
  id: number
  criado_em: string
  acao: string
  usuario: AuditReference | null
  responsavel_nome: string | null
  perfil: string | null
  condominio: AuditReference | null
  recurso_tipo: string | null
  recurso_id: string | null
  antes: Record<string, unknown> | null
  depois: Record<string, unknown> | null
  ip: string | null
}

export interface AuditPage {
  items: AuditRecord[]
  page_size: number
  next_cursor: string | null
}

export interface AuditFilters {
  condominio_id: string
  de: string
  ate: string
  acao: string
  recurso_tipo: string
}

export const noAuditFilters: AuditFilters = {
  condominio_id: '',
  de: '',
  ate: '',
  acao: '',
  recurso_tipo: '',
}

export const auditPageSize = 20

export function createAuditClient(http: AxiosInstance) {
  return {
    async records(filters: AuditFilters, cursor: string | null, signal?: AbortSignal) {
      const params: Record<string, string | number> = { page_size: auditPageSize }
      for (const [key, value] of Object.entries(filters)) {
        if (value.trim()) params[key] = value.trim()
      }
      if (cursor) params.cursor = cursor
      const { data } = await http.get<AuditPage>('/plataforma/auditoria', { params, signal })
      return data
    },
    async condominiums(signal?: AbortSignal) {
      const { data } = await http.get<{ items: AuditReference[] }>('/plataforma/condominios', {
        params: { status: 'ativo', page: 1, page_size: 100 },
        signal,
      })
      return data.items.map(({ id, nome }) => ({ id, nome }))
    },
  }
}

export type AuditClient = ReturnType<typeof createAuditClient>

const actionPattern = /^[a-z][a-z0-9_]*\.(?:[a-z][a-z0-9_]*)?$/

/** Filtros que o servidor rejeitaria com 422, avisados antes de enviar. */
export function auditFilterError(filters: AuditFilters) {
  const action = filters.acao.trim()
  if (action && (action.length > 60 || !actionPattern.test(action)))
    return 'Informe a ação como grupo.verbo (reserva.cancelar) ou só o grupo com ponto (reserva.).'
  if (filters.de && filters.ate && filters.de > filters.ate)
    return 'A data inicial não pode ser posterior à data final.'
  return ''
}

export function auditError(error: unknown) {
  if (isAxiosError<{ error?: { message?: string } }>(error)) {
    const { response } = error
    if (response?.status === 403) return 'Seu acesso não permite consultar a auditoria.'
    if (response && response.status < 500 && response.data?.error?.message)
      return response.data.error.message
  }
  return 'Não foi possível carregar a auditoria. Tente novamente.'
}

export const profileLabels: Record<string, string> = {
  plataforma: 'Plataforma',
  administracao: 'Administração',
  funcionario: 'Funcionário',
  morador: 'Morador',
}

/** Texto curto de um valor de `antes` ou `depois`. */
export function auditValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
