import { isAxiosError } from 'axios'
import type { AxiosInstance } from 'axios'

interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface CommonArea {
  id: string
  nome: string
  regras: string | null
  abre_as: string
  fecha_as: string
  capacidade: number
}

export interface ReservationSlot {
  hora_inicio: string
  hora_fim: string
  estado: 'livre' | 'da_minha_unidade' | 'ocupado' | 'bloqueado' | 'passado'
}

interface Agenda {
  unidade_ja_reservou: boolean
  slots: ReservationSlot[]
}

export interface Reservation {
  id: string
  area: { nome: string }
  data: string
  hora_inicio: string
  hora_fim: string
  status: 'ativa' | 'cancelada'
  cancelamento: { por: 'morador' | 'administracao'; motivo: string | null } | null
}

export interface OccurrenceSummary {
  id: string
  titulo: string
  status: 'em_aberto' | 'resolvida'
  criada_em: string
  aguardando_administracao: boolean
}

export interface Occurrence extends Omit<OccurrenceSummary, 'aguardando_administracao'> {
  detalhe: string
  anexos: { arquivo_id: string }[]
  interacoes: {
    id: string
    tipo: 'resposta' | 'comentario' | 'resolucao' | 'reabertura'
    texto: string | null
    autor: { nome: string }
    em: string
    anexos: { arquivo_id: string }[]
  }[]
}

const slug = encodeURIComponent
const pageSize = 20

export function createResidentCommunityClient(http: AxiosInstance) {
  return {
    async areas(signal?: AbortSignal) {
      const areas: CommonArea[] = []
      let page = 1
      while (true) {
        const { data } = await http.get<Page<CommonArea>>('/areas-comuns', {
          params: { page, page_size: pageSize },
          signal,
        })
        areas.push(...data.items)
        if (!data.items.length || areas.length >= data.total) return areas
        page += 1
      }
    },
    async agenda(areaId: string, unitId: string, date: string, signal?: AbortSignal) {
      const { data } = await http.get<Agenda>(`/areas-comuns/${slug(areaId)}/agenda`, {
        params: { unidade_id: unitId, data: date },
        signal,
      })
      return data
    },
    async reserve(areaId: string, unitId: string, date: string, time: string) {
      await http.post('/reservas', {
        area_id: areaId,
        unidade_id: unitId,
        data: date,
        hora_inicio: time,
      })
    },
    async reservations(unitId: string, page: number, signal?: AbortSignal) {
      const { data } = await http.get<Page<Reservation>>('/reservas', {
        params: { unidade_id: unitId, page, page_size: pageSize },
        signal,
      })
      return data
    },
    async cancelReservation(id: string) {
      await http.post(`/reservas/${slug(id)}/cancelamento`, {})
    },
    async occurrences(unitId: string, page: number, signal?: AbortSignal) {
      const { data } = await http.get<Page<OccurrenceSummary>>('/ocorrencias', {
        params: { unidade_id: unitId, page, page_size: pageSize },
        signal,
      })
      return data
    },
    async occurrence(id: string, signal?: AbortSignal) {
      const { data } = await http.get<Occurrence>(`/ocorrencias/${slug(id)}`, { signal })
      return data
    },
    async uploadOccurrencePhoto(unitId: string, photo: File) {
      const { data } = await http.post<{ id: string }>('/arquivos/ocorrencias', photo, {
        params: { nome: photo.name, unidade_id: unitId },
        headers: { 'Content-Type': photo.type },
      })
      return data.id
    },
    async openOccurrence(unitId: string, title: string, description: string, photos: string[]) {
      await http.post('/ocorrencias', {
        unidade_id: unitId,
        titulo: title,
        detalhe: description,
        anexos: photos,
      })
    },
    async interact(id: string, action: 'comentarios' | 'reabertura', text: string) {
      await http.post(`/ocorrencias/${slug(id)}/${action}`, { texto: text })
    },
    async download(id: string, signal?: AbortSignal) {
      const { data } = await http.get<{ url: string }>(`/arquivos/${slug(id)}/download`, { signal })
      return data.url
    },
  }
}

export type ResidentCommunityClient = ReturnType<typeof createResidentCommunityClient>

export function communityError(error: unknown) {
  if (isAxiosError<{ error?: { message?: string } }>(error)) {
    const { response } = error
    if (response?.status === 403) return 'Seu acesso não permite esta operação para a unidade.'
    if (response && response.status < 500 && response.data?.error?.message)
      return response.data.error.message
  }
  return 'Não foi possível concluir a operação. Tente novamente.'
}
