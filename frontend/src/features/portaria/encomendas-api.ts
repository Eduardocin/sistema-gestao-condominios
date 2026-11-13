import type { AxiosInstance } from 'axios'

export type PackageStatus =
  | 'aguardando_retirada'
  | 'entregue_aguardando_confirmacao'
  | 'retirada_confirmada'

export interface PackageRecord {
  id: string
  unidade: { id: string; identificacao: string }
  destinatario: { id: string; nome: string }
  descricao: string
  foto_arquivo_id: string
  status: PackageStatus
  recebimento: { em: string; funcionario_id: string; funcionario_nome: string }
  entrega: {
    em: string
    funcionario_id: string
    funcionario_nome: string
    recebedor_id: string
    recebedor_nome: string
  } | null
  confirmacao: { em: string; morador_id: string; morador_nome: string } | null
  pode_confirmar: boolean
}

export interface PackagePage {
  items: PackageRecord[]
  page: number
  page_size: number
  total: number
}

export interface UnitOption {
  id: string
  identificacao: string
}

export interface ResidentOption {
  id: string
  nome: string
}

export interface EmployeeOption {
  id: string
  nome: string
}

export interface RegisterPackage {
  unidade_id: string
  destinatario_morador_unidade_id: string
  descricao: string
  recebido_por_funcionario_id: string
  foto: File
}

export interface DeliverPackage {
  recebedor_morador_unidade_id: string
  entregue_por_funcionario_id: string
}

interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

async function allPages<T>(
  http: AxiosInstance,
  path: string,
  extraParams: Record<string, string | number | boolean> = {},
): Promise<T[]> {
  const items: T[] = []
  let page = 1
  let total = Number.POSITIVE_INFINITY

  while (items.length < total) {
    const { data } = await http.get<Page<T>>(path, {
      params: { ...extraParams, page, page_size: 100 },
    })
    items.push(...data.items)
    total = data.total
    if (data.items.length === 0) break
    page = data.page + 1
  }

  return items.slice(0, total)
}

export function createEncomendasClient(http: AxiosInstance) {
  async function list(
    filters: {
      search?: string
      status?: PackageStatus | ''
      page?: number
    } = {},
  ): Promise<PackagePage> {
    const { data } = await http.get<PackagePage>('/encomendas', {
      params: {
        ...(filters.search?.trim() ? { busca: filters.search.trim() } : {}),
        ...(filters.status ? { status: filters.status } : {}),
        page: filters.page ?? 1,
        page_size: 20,
      },
    })
    return data
  }

  async function get(id: string): Promise<PackageRecord> {
    const { data } = await http.get<PackageRecord>(`/encomendas/${encodeURIComponent(id)}`)
    return data
  }

  async function register(input: RegisterPackage): Promise<PackageRecord> {
    const form = new FormData()
    form.set('unidade_id', input.unidade_id)
    form.set('destinatario_morador_unidade_id', input.destinatario_morador_unidade_id)
    form.set('descricao', input.descricao.trim())
    form.set('recebido_por_funcionario_id', input.recebido_por_funcionario_id)
    form.set('foto', input.foto)
    const { data } = await http.post<PackageRecord>('/encomendas', form)
    return data
  }

  async function units(): Promise<UnitOption[]> {
    return allPages<UnitOption>(http, '/portaria/unidades')
  }

  async function residents(unitId: string, somenteConfirmaveis = false): Promise<ResidentOption[]> {
    return allPages<ResidentOption>(
      http,
      `/portaria/unidades/${encodeURIComponent(unitId)}/moradores`,
      somenteConfirmaveis ? { somente_confirmaveis: true } : {},
    )
  }

  async function employees(): Promise<EmployeeOption[]> {
    return allPages<EmployeeOption>(http, '/funcionarios', { ativo: true })
  }

  async function deliver(id: string, input: DeliverPackage): Promise<PackageRecord> {
    const { data } = await http.post<PackageRecord>(
      `/encomendas/${encodeURIComponent(id)}/entrega`,
      input,
    )
    return data
  }

  async function confirm(id: string): Promise<PackageRecord> {
    const { data } = await http.post<PackageRecord>(
      `/encomendas/${encodeURIComponent(id)}/confirmacao`,
      {},
    )
    return data
  }

  async function photoUrl(fileId: string): Promise<string> {
    const { data } = await http.get<{ url: string; expires_in: number }>(
      `/arquivos/${encodeURIComponent(fileId)}/download`,
    )
    return data.url
  }

  return { list, get, register, units, residents, employees, deliver, confirm, photoUrl }
}
