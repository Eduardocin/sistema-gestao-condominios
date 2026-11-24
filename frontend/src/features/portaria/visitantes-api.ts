import type { AxiosInstance } from 'axios'
import { createEncomendasClient } from './encomendas-api.ts'

export type Canal = 'interfone' | 'telefone'
export type RespostaContato = 'autorizou' | 'negou' | 'sem_resposta'
export type StatusVisita = 'em_andamento' | 'encerrada'

interface Referencia {
  id: string
  nome: string
}
export interface Pagina<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
export interface Visitante {
  id: string
  nome: string
  unidade: Referencia
  entrada_prevista: string
  saida_prevista: string
  ambigua: boolean
}
export interface Autorizacao {
  id: string
  autorizado_por: Referencia
  inicio: string
  fim: string
}
interface Movimento {
  em: string
  funcionario: Referencia
}
export interface Visita {
  id: string
  visitante: Referencia
  unidade: Referencia
  status: StatusVisita
  entrada: Movimento
  saida: Movimento | null
  autorizacao: Autorizacao | null
  contato: { morador_id: string; canal: Canal; resposta: 'autorizou' } | null
}
export interface Contato {
  id: string
  visitante: Referencia
  unidade: Referencia
  funcionario: Referencia
  canal: Canal
  resposta: 'negou' | 'sem_resposta'
  registrado_em: string
}
interface Destino {
  visitante_id: string
  unidade_id: string
  funcionario_id: string
}
interface Resposta<T extends RespostaContato> {
  morador_id: string
  canal: Canal
  resposta: T
}
export type Busca = { unidade: string; termo: string; por: 'nome' | 'cpf' }

export function createVisitantesClient(http: AxiosInstance) {
  const { units, residents, employees } = createEncomendasClient(http)
  return {
    units,
    residents,
    employees,
    async buscar(busca: Busca, page: number): Promise<Pagina<Visitante>> {
      const params = { page, page_size: 20 }
      if (busca.por === 'cpf') {
        const { data } = await http.post<Pagina<Visitante>>(
          '/portaria/visitantes/busca-documento',
          {
            unidade_id: busca.unidade,
            cpf: busca.termo.replace(/[.\-\s]/g, ''),
          },
          { params },
        )
        return data
      }
      const { data } = await http.get<Pagina<Visitante>>('/portaria/visitantes', {
        params: {
          ...params,
          unidade_id: busca.unidade || undefined,
          busca: busca.termo.trim() || undefined,
        },
      })
      return data
    },
    async autorizacao(visitante: Visitante): Promise<Autorizacao | null> {
      const { data } = await http.get<Autorizacao[]>('/portaria/autorizacoes', {
        params: { visitante_id: visitante.id, unidade_id: visitante.unidade.id },
      })
      return data[0] ?? null
    },
    async visitas(status: StatusVisita, page: number, busca?: string): Promise<Pagina<Visita>> {
      const { data } = await http.get<Pagina<Visita>>('/visitas', {
        params: { status, page, page_size: 20, busca: busca?.trim() || undefined },
      })
      return data
    },
    async contatos(page: number): Promise<Pagina<Contato>> {
      const { data } = await http.get<Pagina<Contato>>('/portaria/contatos', {
        params: { page, page_size: 20 },
      })
      return data
    },
    async entrar(
      dados: Destino & ({ autorizacao_id: string } | { contato: Resposta<'autorizou'> }),
    ): Promise<Visita> {
      const { data } = await http.post<Visita>('/visitas', dados)
      return data
    },
    async registrarContato(dados: Destino & Resposta<'negou' | 'sem_resposta'>): Promise<Contato> {
      const { data } = await http.post<Contato>('/portaria/contatos', dados)
      return data
    },
    async sair(id: string, funcionario_id: string): Promise<Visita> {
      const { data } = await http.post<Visita>(`/visitas/${encodeURIComponent(id)}/saida`, {
        funcionario_id,
      })
      return data
    },
  }
}
