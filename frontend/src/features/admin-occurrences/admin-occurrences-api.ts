import type { AxiosInstance } from 'axios'
import type { OccurrenceListParams, ReplyPayload, ResolutionPayload } from './occurrence-form.ts'

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export type OccurrenceStatus = 'em_aberto' | 'resolvida'
export type InteractionType = 'resposta' | 'comentario' | 'resolucao' | 'reabertura'

export interface Attachment {
  arquivo_id: string
  interacao_id: string | null
}

export interface OccurrenceSummary {
  id: string
  titulo: string
  status: OccurrenceStatus
  unidade: { id: string; identificacao: string }
  criada_em: string
  ultima_interacao_em: string | null
  aguardando_administracao: boolean
}

export interface Interaction {
  id: string
  tipo: InteractionType
  texto: string | null
  autor: { tipo: 'morador' | 'administracao'; nome: string }
  em: string
  anexos: Attachment[]
}

export interface Occurrence {
  id: string
  unidade: { id: string; identificacao: string }
  titulo: string
  detalhe: string
  status: OccurrenceStatus
  aberta_por: { id: string; nome: string }
  criada_em: string
  resolvida_em: string | null
  anexos: Attachment[]
  interacoes: Interaction[]
}

export interface Responsible {
  id: string
  nome: string
  ativo: boolean
}

const slug = encodeURIComponent
// Teto de page_size da API (GET /ocorrencias aceita de 1 a 100).
export const MAX_PAGE_SIZE = 100

export function createAdminOccurrencesClient(http: AxiosInstance) {
  return {
    async occurrences(params: OccurrenceListParams, signal?: AbortSignal) {
      const page_size = Math.min(Math.max(1, params.page_size), MAX_PAGE_SIZE)
      const { data } = await http.get<Page<OccurrenceSummary>>('/ocorrencias', {
        params: { ...params, page_size },
        signal,
      })
      return data
    },
    async occurrence(id: string, signal?: AbortSignal) {
      return (await http.get<Occurrence>(`/ocorrencias/${slug(id)}`, { signal })).data
    },
    async reply(id: string, payload: ReplyPayload) {
      return (await http.post<Interaction>(`/ocorrencias/${slug(id)}/respostas`, payload)).data
    },
    async resolve(id: string, payload: ResolutionPayload) {
      return (await http.post<Occurrence>(`/ocorrencias/${slug(id)}/resolucao`, payload)).data
    },
    async activeResponsibles(signal?: AbortSignal) {
      const { data } = await http.get<Responsible[]>('/responsaveis-administracao', { signal })
      return data.filter((person) => person.ativo)
    },
    /** URL assinada e curta do anexo (a Administração lê anexos do próprio condomínio). */
    async attachmentUrl(fileId: string, signal?: AbortSignal) {
      const { data } = await http.get<{ url: string }>(`/arquivos/${slug(fileId)}/download`, {
        signal,
      })
      return data.url
    },
  }
}

export type AdminOccurrencesClient = ReturnType<typeof createAdminOccurrencesClient>
