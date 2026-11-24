import { isAxiosError } from 'axios'
import type { AxiosInstance } from 'axios'
import type { Pagina, Veiculo } from '../portaria/visitantes-api.ts'

export const VEHICLES_PER_UNIT = 5

export interface VehicleFields {
  placa: string
  marca: string
  modelo: string
  cor: string
}

export interface ResidentVehicle extends Veiculo {
  unidade_id: string
  ativo: boolean
}

export function createResidentVehiclesClient(http: AxiosInstance) {
  return {
    async list(
      unitId: string,
      search: string,
      page: number,
      pageSize: number,
      signal?: AbortSignal,
    ) {
      const term = search.trim()
      const { data } = await http.get<Pagina<ResidentVehicle>>('/veiculos', {
        params: { unidade_id: unitId, page, page_size: pageSize, ...(term ? { busca: term } : {}) },
        signal,
      })
      return data
    },
    async detail(id: string, signal?: AbortSignal) {
      const { data } = await http.get<ResidentVehicle>(`/veiculos/${encodeURIComponent(id)}`, {
        signal,
      })
      return data
    },
    async create(unitId: string, fields: VehicleFields) {
      const { data } = await http.post<ResidentVehicle>('/veiculos', {
        ...fields,
        unidade_id: unitId,
      })
      return data
    },
    async update(id: string, fields: VehicleFields) {
      const { data } = await http.put<ResidentVehicle>(
        `/veiculos/${encodeURIComponent(id)}`,
        fields,
      )
      return data
    },
    async remove(id: string) {
      const { data } = await http.post<ResidentVehicle>(
        `/veiculos/${encodeURIComponent(id)}/remocao`,
        {},
      )
      return data
    },
  }
}

export type VehicleFieldErrors = Partial<Record<keyof VehicleFields, string>>

export function prepareVehicle(
  fields: VehicleFields,
): { data: VehicleFields; errors?: never } | { data?: never; errors: VehicleFieldErrors } {
  const data: VehicleFields = {
    placa: fields.placa.replace(/[\s-]/g, '').toUpperCase(),
    marca: fields.marca.trim(),
    modelo: fields.modelo.trim(),
    cor: fields.cor.trim(),
  }
  const errors: VehicleFieldErrors = {}
  if (fields.placa.length > 20 || !/^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$/.test(data.placa)) {
    errors.placa = 'Informe uma placa brasileira válida, como ABC-1234 ou ABC1D23.'
  }
  for (const key of ['marca', 'modelo', 'cor'] as const) {
    if (!data[key]) errors[key] = 'Preencha este campo.'
    else if ([...data[key]].length > 40) errors[key] = 'Use até 40 caracteres.'
  }
  return Object.keys(errors).length > 0 ? { errors } : { data }
}

export function vehicleFailureMessage(error: unknown) {
  if (isAxiosError<{ error?: { reason?: string } }>(error)) {
    const { status, data } = error.response ?? {}
    if (status === 403) return 'Seu acesso a veículos está bloqueado nesta unidade.'
    if (status === 404)
      return 'O registro não está mais disponível. Confira o vínculo da unidade ou atualize a lista.'
    if (status === 422) return 'Confira os dados informados e tente novamente.'
    if (status === 429) return 'Muitas tentativas. Aguarde um pouco e tente novamente.'
    if (status === 409) {
      switch (data?.error?.reason) {
        case 'placa_ja_cadastrada_na_unidade':
          return 'Já existe um veículo ativo com essa placa nesta unidade.'
        case 'limite_veiculos':
          return `Esta unidade já tem ${VEHICLES_PER_UNIT} veículos ativos.`
        case 'veiculo_removido':
          return 'Este veículo já foi removido. Atualize a lista.'
        default:
          return 'O cadastro mudou. Atualize a lista e tente novamente.'
      }
    }
  }
  return 'Não foi possível concluir a operação. Verifique a conexão e tente novamente.'
}
