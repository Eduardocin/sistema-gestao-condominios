import type { AxiosInstance } from 'axios'
import type { AreaPayload } from './area-form.ts'
import type { ReservationParams } from './reservation-admin.ts'

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface AdminArea {
  id: string
  nome: string
  foto_arquivo_id: string
  regras: string | null
  abre_as: string
  fecha_as: string
  capacidade: number
  ativa: boolean
}

export type AreaStatusFilter = 'ativas' | 'desativadas' | 'todas'

export interface Reference {
  id: string
  nome: string
}

export interface AdminReservation {
  id: string
  area: Reference
  unidade: { id: string; identificacao: string }
  data: string
  hora_inicio: string
  hora_fim: string
  status: 'ativa' | 'cancelada'
  reservada_por?: Reference | null
  criada_em: string
  cancelamento: {
    em: string
    por: 'morador' | 'administracao'
    motivo: string | null
    responsavel?: Reference | null
  } | null
}

export interface Responsible {
  id: string
  nome: string
  ativo: boolean
}

export interface UnitSummary {
  id: string
  identificacao: string
  bloco: string | null
  andar: string | null
  ativo: boolean
}

const slug = encodeURIComponent
// Teto de page_size da API: usado só para montar os selects (lista completa).
const maxPageSize = 100

// O filtro da tela vira o booleano opcional `ativa` da API (omitido em "todas").
function activeParam(filter: AreaStatusFilter) {
  return filter === 'todas' ? undefined : filter === 'ativas'
}

async function everyPage<T>(load: (page: number) => Promise<Page<T>>) {
  const items: T[] = []
  for (let page = 1; ; page += 1) {
    const data = await load(page)
    items.push(...data.items)
    if (!data.items.length || items.length >= data.total) return items
  }
}

export function createAdminAreasClient(http: AxiosInstance) {
  return {
    async areas(filter: AreaStatusFilter, page: number, signal?: AbortSignal) {
      const ativa = activeParam(filter)
      const { data } = await http.get<Page<AdminArea>>('/areas-comuns', {
        params: { page, page_size: 20, ...(ativa === undefined ? {} : { ativa }) },
        signal,
      })
      return data
    },
    /** Todas as áreas (ativas e desativadas), para o filtro da lista de reservas. */
    allAreas(signal?: AbortSignal) {
      return everyPage(
        async (page) =>
          (
            await http.get<Page<AdminArea>>('/areas-comuns', {
              params: { page, page_size: maxPageSize },
              signal,
            })
          ).data,
      )
    },
    async area(id: string, signal?: AbortSignal) {
      return (await http.get<AdminArea>(`/areas-comuns/${slug(id)}`, { signal })).data
    },
    async createArea(payload: AreaPayload) {
      return (await http.post<AdminArea>('/areas-comuns', payload)).data
    },
    async updateArea(id: string, payload: AreaPayload) {
      return (await http.put<AdminArea>(`/areas-comuns/${slug(id)}`, payload)).data
    },
    async deactivateArea(id: string) {
      return (await http.post<AdminArea>(`/areas-comuns/${slug(id)}/desativacao`, {})).data
    },
    async reactivateArea(id: string) {
      return (await http.post<AdminArea>(`/areas-comuns/${slug(id)}/reativacao`, {})).data
    },
    /** A API de arquivos recebe o corpo binário (não multipart), com o nome na query. */
    async uploadPhoto(photo: File) {
      const { data } = await http.post<{ id: string }>('/arquivos/fotos', photo, {
        params: { nome: photo.name },
        headers: { 'Content-Type': photo.type },
      })
      return data.id
    },
    async photoUrl(fileId: string, signal?: AbortSignal) {
      const { data } = await http.get<{ url: string }>(`/arquivos/${slug(fileId)}/download`, {
        signal,
      })
      return data.url
    },
    async reservations(params: ReservationParams, signal?: AbortSignal) {
      return (await http.get<Page<AdminReservation>>('/reservas', { params, signal })).data
    },
    async cancelReservation(id: string, motivo: string, responsavelId: string) {
      return (
        await http.post<AdminReservation>(`/reservas/${slug(id)}/cancelamento`, {
          motivo,
          responsavel_id: responsavelId,
        })
      ).data
    },
    async activeResponsibles(signal?: AbortSignal) {
      const { data } = await http.get<Responsible[]>('/responsaveis-administracao', { signal })
      return data.filter((person) => person.ativo)
    },
    units(signal?: AbortSignal) {
      return everyPage(
        async (page) =>
          (
            await http.get<Page<UnitSummary>>('/unidades', {
              params: { page, page_size: maxPageSize },
              signal,
            })
          ).data,
      )
    },
  }
}

export type AdminAreasClient = ReturnType<typeof createAdminAreasClient>
