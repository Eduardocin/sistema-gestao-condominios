import type { Condominium, Identity, Profile } from './types.ts'

export const profileLabels: Record<Profile, string> = { morador: 'Morador', funcionario: 'Portaria', administracao: 'Administração' }
const destinations: Record<Profile, string> = { morador: '/app/morador', funcionario: '/app/portaria', administracao: '/app/administracao' }

export function homePath(identity: Identity, condominiums: Condominium[]): string {
  if (identity.administrador_plataforma) return '/app/plataforma'
  if (!identity.condominio) return condominiums.length > 1 ? '/selecionar-condominio' : '/app/sem-condominio'
  if (identity.condominio.status !== 'ativo') return '/app/sem-condominio'
  return destinations[identity.condominio.perfil]
}
