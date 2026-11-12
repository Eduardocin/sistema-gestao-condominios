import type { Condominium, CondominiumStatus, Identity, Profile } from './types.ts'

export const profileLabels: Record<Profile, string> = { morador: 'Morador', funcionario: 'Portaria', administracao: 'Administração' }
const destinations: Record<Profile, string> = { morador: '/app/morador', funcionario: '/app/portaria', administracao: '/app/administracao' }

export function condominiumNotice(status: CondominiumStatus | undefined) {
  if (status === 'pendente') return { title: 'Cadastro do condomínio em análise', message: 'Aguarde a análise do cadastro. As operações do condomínio serão liberadas após a aprovação.' }
  if (status === 'rejeitado') return { title: 'Cadastro do condomínio rejeitado', message: 'O cadastro não foi aprovado. Entre em contato com a administração para conferir os ajustes necessários.' }
  if (status === 'desativado') return { title: 'Condomínio desativado', message: 'As operações estão indisponíveis. Entre em contato com a administração para verificar o acesso.' }
  return { title: 'Acesso ao condomínio indisponível', message: 'Sua conta está autenticada, mas ainda não há um condomínio disponível para operações. Entre em contato com a administração para verificar seu vínculo.' }
}

export function homePath(identity: Identity, condominiums: Condominium[]): string {
  if (identity.administrador_plataforma) return '/app/plataforma'
  if (!identity.condominio) return condominiums.length > 1 ? '/selecionar-condominio' : '/app/sem-condominio'
  if (identity.condominio.status !== 'ativo') return '/app/sem-condominio'
  return destinations[identity.condominio.perfil]
}
