import type { AxiosInstance } from 'axios'

export interface Responsible {
  id: string
  nome: string
  ativo: boolean
}
export interface Employee {
  id: string
  nome: string
  funcao: 'porteiro' | 'seguranca'
  telefone: string
  email: string
  foto_arquivo_id: string | null
  ativo: boolean
  desligado_em: string | null
}
export interface EmployeeInput {
  nome: string
  funcao: Employee['funcao']
  telefone: string
  email: string
  responsavel_id: string
}
export interface EmployeeList {
  items: Employee[]
  page: number
  page_size: number
  total: number
}

export function createEmployeesClient(http: AxiosInstance) {
  return {
    responsibles: async () => (await http.get<Responsible[]>('/responsaveis-administracao')).data,
    addResponsible: async (name: string) =>
      (await http.post<Responsible>('/responsaveis-administracao', { nome: name.trim() })).data,
    list: async ({ active, search, page }: { active: boolean; search: string; page: number }) =>
      (
        await http.get<EmployeeList>('/funcionarios', {
          params: { ativo: active, busca: search.trim(), page, page_size: 20 },
        })
      ).data,
    create: async (input: EmployeeInput) =>
      (
        await http.post<Employee>('/funcionarios', {
          ...input,
          nome: input.nome.trim(),
          email: input.email.trim().toLowerCase(),
        })
      ).data,
    dismiss: async (id: string, responsibleId: string) =>
      (
        await http.post<Employee>(`/funcionarios/${encodeURIComponent(id)}/desligamento`, {
          responsavel_id: responsibleId,
        })
      ).data,
  }
}
