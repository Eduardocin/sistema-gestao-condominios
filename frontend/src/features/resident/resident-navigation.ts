export const residentNavigation = [
  { key: 'overview', label: 'Visão geral', to: '/app/morador', symbol: '⌂' },
  { key: 'packages', label: 'Encomendas', to: '/app/morador/encomendas', symbol: '▣' },
  { key: 'visitors', label: 'Visitantes', to: '/app/morador/visitantes', symbol: '↔' },
  { key: 'vehicles', label: 'Veículos', to: '/app/morador/veiculos', symbol: '⌑' },
  { key: 'reserve', label: 'Reservar área', to: '/app/morador/areas-comuns', symbol: '▦' },
  { key: 'reservations', label: 'Minhas reservas', to: '/app/morador/reservas', symbol: '✓' },
  { key: 'occurrences', label: 'Ocorrências', to: '/app/morador/ocorrencias', symbol: '◇' },
]

export const residentTabPermissions: Record<string, string> = {
  packages: 'encomendas', visitors: 'visitantes', vehicles: 'veiculos',
  reserve: 'reservas', reservations: 'reservas', occurrences: 'ocorrencias',
  permissions: 'usuarios',
}

export function visibleResidentNavigation(units: { abas?: string[] }[]) {
  return residentNavigation.filter(({ key }) => !residentTabPermissions[key] ||
    units.some((unit) => unit.abas?.includes(residentTabPermissions[key])))
}
