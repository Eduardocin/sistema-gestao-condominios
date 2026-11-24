import { isAxiosError } from 'axios'
import type { AxiosInstance } from 'axios'

export type ResidentVisitorStatus = 'vigentes' | 'futuros' | 'encerrados' | 'cancelados'

export interface ResidentVisitorData {
  nome: string
  cpf: string | null
  idade: number | null
  observacoes: string | null
  entrada_prevista: string
  saida_prevista: string
}

export interface ResidentVisitor extends ResidentVisitorData {
  id: string
  unidade_id: string
  avulso: boolean
  cancelado_em: string | null
}

export interface ResidentVisitorQuery {
  unidade_id: string
  busca?: string
  situacao?: ResidentVisitorStatus
  page: number
}

export interface ResidentVisitorsResult {
  items: ResidentVisitor[]
  total: number
  page: number
  page_size: number
}

export function visitorNameSearchError(value: string) {
  // A API interpreta dígitos na busca também como parte de um CPF.
  if (/\p{Number}/u.test(value)) return 'Busque pelo nome do visitante, sem números.'
}

export function residentVisitorError(error: unknown, fallback: string) {
  if (!isAxiosError<{ error?: { reason?: string } }>(error)) return fallback
  switch (error.response?.status) {
    case 403:
      return 'Você não tem permissão para esta ação na unidade selecionada.'
    case 404:
      return 'Este registro ou unidade não está mais disponível para sua conta.'
    case 409: {
      switch (error.response.data?.error?.reason) {
        case 'visitante_ja_utilizado':
          return 'A portaria já registrou uma entrada com este cadastro. A edição está bloqueada.'
        case 'visita_em_andamento':
          return 'A visita está em andamento. Aguarde o registro de saída pela portaria para cancelar.'
        case 'visitante_cancelado':
          return 'Este cadastro já foi cancelado.'
        default:
          return 'A situação deste cadastro mudou. Consulte os detalhes atualizados.'
      }
    }
    case 422:
      return 'Confira os dados informados e tente novamente.'
    case 429:
      return 'Muitas tentativas. Aguarde um pouco antes de tentar novamente.'
    default:
      return fallback
  }
}

export function createResidentVisitorsClient(http: AxiosInstance) {
  return {
    async list(
      { unidade_id, busca: name, situacao, page }: ResidentVisitorQuery,
      signal?: AbortSignal,
    ): Promise<ResidentVisitorsResult> {
      const busca = name?.trim()
      const error = visitorNameSearchError(busca ?? '')
      if (error) throw new Error(error)
      const { data } = await http.get<ResidentVisitorsResult>('/visitantes', {
        params: { unidade_id, busca: busca || undefined, situacao, page, page_size: 20 },
        signal,
      })
      return data
    },
    async get(id: string): Promise<ResidentVisitor> {
      const { data } = await http.get<ResidentVisitor>(`/visitantes/${encodeURIComponent(id)}`)
      return data
    },
    async create(visitor: ResidentVisitorData & { unidade_id: string }): Promise<ResidentVisitor> {
      const { data } = await http.post<ResidentVisitor>('/visitantes', visitor)
      return data
    },
    async update(id: string, visitor: ResidentVisitorData): Promise<ResidentVisitor> {
      const { data } = await http.put<ResidentVisitor>(
        `/visitantes/${encodeURIComponent(id)}`,
        visitor,
      )
      return data
    },
    async cancel(id: string): Promise<ResidentVisitor> {
      const { data } = await http.post<ResidentVisitor>(
        `/visitantes/${encodeURIComponent(id)}/cancelamento`,
        {},
      )
      return data
    },
  }
}
