/**
 * Navegação lateral única por perfil. Toda tela de uma área usa a mesma lista,
 * mudando só o item ativo — assim o menu não "encolhe" ao entrar em uma página.
 */
export interface AreaNavigationItem {
  key: string
  label: string
  to: string
  symbol: string
}

export const adminNavigation: AreaNavigationItem[] = [
  { key: 'overview', label: 'Visão geral', to: '/app/administracao', symbol: '⌂' },
  {
    key: 'settings',
    label: 'Condomínio e estrutura',
    to: '/app/administracao/condominio',
    symbol: '▦',
  },
  { key: 'units', label: 'Chaves de acesso', to: '/app/administracao/chaves', symbol: '⚿' },
  {
    key: 'shared',
    label: 'Conta de funcionários',
    to: '/app/administracao/conta-funcionarios',
    symbol: '⊡',
  },
  { key: 'employees', label: 'Funcionários', to: '/app/administracao/funcionarios', symbol: '♙' },
  { key: 'notices', label: 'Avisos', to: '/app/administracao/avisos', symbol: '◇' },
  { key: 'areas', label: 'Áreas comuns', to: '/app/administracao/areas-comuns', symbol: '◫' },
  { key: 'reservations', label: 'Reservas', to: '/app/administracao/reservas', symbol: '✓' },
  { key: 'occurrences', label: 'Ocorrências', to: '/app/administracao/ocorrencias', symbol: '!' },
  {
    key: 'packageReport',
    label: 'Relatório de encomendas',
    to: '/app/administracao/encomendas/relatorio',
    symbol: '▣',
  },
  { key: 'support', label: 'Suporte', to: '/app/administracao/suporte', symbol: '☏' },
  {
    key: 'announcements',
    label: 'Comunicados',
    to: '/app/administracao/comunicados',
    symbol: '✉',
  },
]

export const platformNavigation: AreaNavigationItem[] = [
  { key: 'overview', label: 'Visão geral', to: '/app/plataforma', symbol: '⌂' },
  { key: 'approvals', label: 'Condomínios', to: '/app/plataforma/condominios', symbol: '▤' },
  { key: 'support', label: 'Fila de suporte', to: '/app/plataforma/suporte', symbol: '☏' },
  { key: 'announcements', label: 'Comunicados', to: '/app/plataforma/comunicados', symbol: '✉' },
  { key: 'audit', label: 'Auditoria', to: '/app/plataforma/auditoria', symbol: '☰' },
]

export const portariaNavigation: AreaNavigationItem[] = [
  { key: 'overview', label: 'Visão geral', to: '/app/portaria', symbol: '⌂' },
  { key: 'packages', label: 'Encomendas', to: '/app/portaria/encomendas', symbol: '▣' },
  { key: 'visitors', label: 'Visitantes', to: '/app/portaria/visitantes', symbol: '↔' },
]
