import { lazy, Suspense } from 'react'
import { useAuth } from '../auth/context'

const CondominiumSettingsPage = lazy(() =>
  import('./CondominiumSettingsPage').then((module) => ({
    default: module.CondominiumSettingsPage,
  })),
)
const SharedAccountPage = lazy(() =>
  import('./SharedAccountPage').then((module) => ({ default: module.SharedAccountPage })),
)

export function CondominiumSettingsRoute() {
  const { snapshot } = useAuth()
  return (
    <Suspense fallback={<p role="status">Carregando página…</p>}>
      <CondominiumSettingsPage key={snapshot.identity?.condominio?.id ?? 'none'} />
    </Suspense>
  )
}

export function SharedAccountRoute() {
  const { snapshot } = useAuth()
  return (
    <Suspense fallback={<p role="status">Carregando página…</p>}>
      <SharedAccountPage key={snapshot.identity?.condominio?.id ?? 'none'} />
    </Suspense>
  )
}
