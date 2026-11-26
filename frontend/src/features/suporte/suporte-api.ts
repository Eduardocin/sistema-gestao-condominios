import { isAxiosError } from 'axios'
import type { AxiosInstance } from 'axios'

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export type TicketStatus = 'aberto' | 'em_atendimento' | 'encerrado'

export interface Reference {
  id: string
  nome: string
}

export interface TicketSummary {
  id: string
  titulo: string
  status: TicketStatus
  condominio: Reference | null
  aberto_por: Reference
  atendido_por: Reference | null
  criado_em: string
  encerrado_em: string | null
}

export interface TicketMessage {
  id: string
  autor: { tipo: 'administracao' | 'plataforma'; nome: string }
  texto: string
  em: string
}

export interface Ticket extends TicketSummary {
  descricao: string
  anexos: string[]
  mensagens: TicketMessage[]
}

export interface PlatformTicketFilters {
  status?: TicketStatus
  busca?: string
  de?: string
  ate?: string
}

export interface Announcement {
  id: string
  titulo: string
  texto: string
  criado_em: string
}

export interface SentAnnouncement extends Announcement {
  enviado_por: Reference
  total_destinatarios: number
}

export interface SentAnnouncementDetail extends SentAnnouncement {
  destinatarios: Reference[]
}

export interface PackageTotals {
  registradas: number
  aguardando_retirada: number
  entregue_aguardando_confirmacao: number
  retirada_confirmada: number
}

export interface PackageReport {
  periodo: { de: string | null; ate: string | null }
  totais: PackageTotals
  por_unidade: (PackageTotals & { unidade: { id: string; identificacao: string } })[]
}

export interface PackageReportFilters {
  data_de?: string
  data_ate?: string
}

export type SupportScope = 'administracao' | 'plataforma'

const slug = encodeURIComponent
export const pageSize = 20

function withoutBlanks<T extends object>(filters: T) {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== ''),
  )
}

export function createSupportClient(http: AxiosInstance) {
  const base = (scope: SupportScope) =>
    scope === 'plataforma' ? '/plataforma/chamados' : '/chamados'
  return {
    async tickets(
      scope: SupportScope,
      page: number,
      filters: PlatformTicketFilters = {},
      signal?: AbortSignal,
    ) {
      const params = withoutBlanks({
        ...(scope === 'plataforma' ? filters : { status: filters.status }),
        page,
        page_size: pageSize,
      })
      const { data } = await http.get<Page<TicketSummary>>(base(scope), { params, signal })
      return data
    },
    async ticket(scope: SupportScope, id: string, signal?: AbortSignal) {
      const { data } = await http.get<Ticket>(`${base(scope)}/${slug(id)}`, { signal })
      return data
    },
    async openTicket(title: string, description: string, attachments: string[]) {
      const { data } = await http.post<Ticket>('/chamados', {
        titulo: title,
        descricao: description,
        anexos: attachments,
      })
      return data
    },
    async reply(scope: SupportScope, id: string, text: string) {
      const { data } = await http.post<TicketMessage>(`${base(scope)}/${slug(id)}/mensagens`, {
        texto: text,
      })
      return data
    },
    async closeTicket(id: string) {
      const { data } = await http.post<Ticket>(`/plataforma/chamados/${slug(id)}/encerramento`, {})
      return data
    },
    async uploadAttachment(file: File) {
      const { data } = await http.post<{ id: string }>('/arquivos/suporte', file, {
        params: { nome: file.name },
        headers: { 'Content-Type': file.type },
      })
      return data.id
    },
    async download(id: string, signal?: AbortSignal) {
      const { data } = await http.get<{ url: string }>(`/arquivos/${slug(id)}/download`, { signal })
      return data.url
    },
    async platformAnnouncements(page: number, signal?: AbortSignal) {
      const { data } = await http.get<Page<SentAnnouncement>>('/plataforma/comunicados', {
        params: { page, page_size: pageSize },
        signal,
      })
      return data
    },
    async platformAnnouncement(id: string, signal?: AbortSignal) {
      const { data } = await http.get<SentAnnouncementDetail>(
        `/plataforma/comunicados/${slug(id)}`,
        { signal },
      )
      return data
    },
    async sendAnnouncement(title: string, text: string) {
      const { data } = await http.post<SentAnnouncementDetail>('/plataforma/comunicados', {
        titulo: title,
        texto: text,
      })
      return data
    },
    async receivedAnnouncements(page: number, signal?: AbortSignal) {
      const { data } = await http.get<Page<Announcement>>('/comunicados', {
        params: { page, page_size: pageSize },
        signal,
      })
      return data
    },
    async packageReport(filters: PackageReportFilters, signal?: AbortSignal) {
      const { data } = await http.get<PackageReport>('/encomendas/relatorio', {
        params: withoutBlanks(filters),
        signal,
      })
      return data
    },
  }
}

export type SupportClient = ReturnType<typeof createSupportClient>

export function supportError(error: unknown) {
  if (isAxiosError<{ error?: { message?: string } }>(error)) {
    const { response } = error
    if (response?.status === 403) return 'Seu acesso não permite esta operação.'
    if (response && response.status < 500 && response.data?.error?.message)
      return response.data.error.message
  }
  return 'Não foi possível concluir a operação. Tente novamente.'
}

export const ticketStatusLabels: Record<TicketStatus, string> = {
  aberto: 'Aberto',
  em_atendimento: 'Em atendimento',
  encerrado: 'Encerrado',
}

/** Valida o período do relatório: ambas as datas são opcionais, mas não podem se inverter. */
export function reportPeriodError(filters: PackageReportFilters) {
  const { data_de: from, data_ate: to } = filters
  return from && to && from > to ? 'A data inicial não pode ser posterior à data final.' : ''
}
