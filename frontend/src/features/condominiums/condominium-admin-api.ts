import { isAxiosError } from 'axios'
import type { AxiosInstance } from 'axios'

export interface CondominiumAddress {
  cep: string | null
  logradouro: string | null
  numero: string | null
  complemento: string | null
  bairro: string | null
  cidade: string | null
  uf: string | null
}

export interface CondominiumRecord {
  id: string
  nome: string
  cnpj: string | null
  status: 'pendente' | 'ativo' | 'rejeitado' | 'desativado'
  endereco: CondominiumAddress
  logo_arquivo_id: string | null
  motivo_rejeicao: string | null
  aprovado_em: string | null
  analises: { evento: string; motivo: string | null; em: string }[]
}

export interface UnitRecord {
  id: string
  identificacao: string
  ativo: boolean
}

export interface FloorRecord {
  id: string
  nome: string
  ordem: number
  ativo: boolean
  unidades: UnitRecord[]
}

export interface BlockRecord {
  id: string
  nome: string
  ativo: boolean
  andares: FloorRecord[]
}

export interface StructureRecord {
  blocos: BlockRecord[]
}

export interface ResponsibleRecord {
  id: string
  nome: string
  ativo: boolean
}

export interface SharedEmployeeAccount {
  login: string
  atualizada_em: string | null
}

export interface CondominiumUpdate {
  nome: string
  cnpj: string
  endereco: CondominiumAddress
  responsavel_id: string
}

export function createCondominiumAdminApi(http: AxiosInstance) {
  const pathId = (id: string) => encodeURIComponent(id)
  return {
    async condominium(signal?: AbortSignal) {
      const { data } = await http.get<CondominiumRecord>('/condominio', { signal })
      return data
    },
    async structure(signal?: AbortSignal) {
      const { data } = await http.get<StructureRecord>('/condominio/estrutura', { signal })
      return data
    },
    async updateCondominium(input: CondominiumUpdate) {
      const { data } = await http.put<CondominiumRecord>('/condominio', input)
      return data
    },
    async updateBlock(id: string, input: { nome: string; responsavel_id: string }) {
      const { data } = await http.put<BlockRecord>(`/estrutura/blocos/${pathId(id)}`, input)
      return data
    },
    async updateFloor(id: string, input: { nome: string; ordem: number; responsavel_id: string }) {
      const { data } = await http.put<FloorRecord>(`/estrutura/andares/${pathId(id)}`, input)
      return data
    },
    async updateUnit(id: string, input: { identificacao: string; responsavel_id: string }) {
      const { data } = await http.put<UnitRecord>(`/estrutura/unidades/${pathId(id)}`, input)
      return data
    },
    async createBlock(input: { nome: string; responsavel_id: string }) {
      const { data } = await http.post<BlockRecord>('/estrutura/blocos', input)
      return data
    },
    async createFloor(
      blockId: string,
      input: { nome: string; ordem: number; responsavel_id: string },
    ) {
      const { data } = await http.post<FloorRecord>(
        `/estrutura/blocos/${pathId(blockId)}/andares`,
        input,
      )
      return data
    },
    async createUnit(floorId: string, input: { identificacao: string; responsavel_id: string }) {
      const { data } = await http.post<UnitRecord>(
        `/estrutura/andares/${pathId(floorId)}/unidades`,
        input,
      )
      return data
    },
    async setStructureStatus(
      type: 'blocos' | 'andares' | 'unidades',
      id: string,
      active: boolean,
      responsibleId: string,
    ) {
      const action = active ? 'reativacao' : 'desativacao'
      const { data } = await http.post<BlockRecord | FloorRecord | UnitRecord>(
        `/estrutura/${type}/${pathId(id)}/${action}`,
        { responsavel_id: responsibleId },
      )
      return data
    },
    async resendRegistration(responsibleId: string) {
      const { data } = await http.post<CondominiumRecord & { enviado_em: string }>(
        '/condominio/reenvio',
        { responsavel_id: responsibleId },
      )
      return data
    },
    async setCondominiumStatus(id: string, active: boolean) {
      const action = active ? 'reativacao' : 'desativacao'
      const { data } = await http.post<CondominiumRecord>(
        `/plataforma/condominios/${pathId(id)}/${action}`,
        {},
      )
      return data
    },
    async responsibles(signal?: AbortSignal) {
      const { data } = await http.get<ResponsibleRecord[]>('/responsaveis-administracao', {
        params: { ativo: true },
        signal,
      })
      return data
    },
    async createResponsible(nome: string) {
      const { data } = await http.post<ResponsibleRecord>('/responsaveis-administracao', { nome })
      return data
    },
    async updateResponsible(id: string, nome: string) {
      const { data } = await http.put<ResponsibleRecord>(
        `/responsaveis-administracao/${pathId(id)}`,
        { nome },
      )
      return data
    },
    async deactivateResponsible(id: string) {
      const { data } = await http.post<ResponsibleRecord>(
        `/responsaveis-administracao/${pathId(id)}/desativacao`,
        {},
      )
      return data
    },
    async sharedAccount(signal?: AbortSignal) {
      const { data } = await http.get<SharedEmployeeAccount>('/conta-funcionarios', { signal })
      return data
    },
    async saveSharedAccount(input: { login: string; senha: string; responsavel_id: string }) {
      const { data } = await http.put<SharedEmployeeAccount>('/conta-funcionarios', input)
      return data
    },
  }
}

export type CondominiumAdminApi = ReturnType<typeof createCondominiumAdminApi>

export function condominiumAdminError(error: unknown, fallback: string) {
  if (
    isAxiosError<{ error?: { message?: string } }>(error) &&
    error.response &&
    error.response.status < 500 &&
    error.response.data?.error?.message
  ) {
    return error.response.data.error.message
  }
  return fallback
}
