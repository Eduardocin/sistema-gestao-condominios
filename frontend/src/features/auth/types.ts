export interface User { id: string; nome: string; email: string }
export type Profile = 'administracao' | 'funcionario' | 'morador'
export const condominiumStatuses = ['pendente', 'ativo', 'rejeitado', 'desativado'] as const
export type CondominiumStatus = (typeof condominiumStatuses)[number]
export interface Condominium { id: string; nome: string; perfil: Profile; status: CondominiumStatus }
export interface Identity {
  usuario: User
  condominio: Condominium | null
  unidades: { id: string; identificacao: string }[]
  administrador_plataforma: boolean
}
export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in: number
  usuario: User
  condominio: Condominium | null
  condominios: Condominium[]
  requer_selecao: boolean
  administrador_plataforma: boolean
}
export interface SessionSnapshot {
  status: 'loading' | 'anonymous' | 'authenticated' | 'error'
  identity: Identity | null
  condominiums: Condominium[]
  message: string | null
}
export type SessionStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
