import { createBrowserRouter } from 'react-router'
import { HomePage } from '../features/home/HomePage'
import { StatusPage } from '../features/home/StatusPage'
import { AccessPage } from '../features/access/AccessPage'
import { DesignSystemPage } from '../features/design-system/DesignSystemPage'
import { NotFoundPage } from './NotFoundPage'
import { PortariaPage } from '../features/portaria/PortariaPage'
import { LoginPage } from '../features/auth/LoginPage'
import { AccessDenied, AppEntry, RequireSession, SelectCondominiumPage } from '../features/auth/SessionPages'
import { WorkspacePage } from '../features/auth/WorkspacePage'

export const router = createBrowserRouter([
  { path: '/', element: <HomePage /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/cadastro', element: <AccessPage /> },
  { path: '/status', element: <StatusPage /> },
  { path: '/design-system', element: <DesignSystemPage /> },
  { path: '/prototipos/portaria', element: <PortariaPage /> },
  { path: '/selecionar-condominio', element: <SelectCondominiumPage /> },
  { path: '/app', element: <AppEntry /> },
  ...['morador', 'portaria', 'administracao', 'plataforma', 'sem-condominio'].map((area) => ({ path: `/app/${area}`, element: <WorkspacePage area={area} /> })),
  { path: '/acesso-negado', element: <RequireSession><AccessDenied /></RequireSession> },
  { path: '*', element: <NotFoundPage /> },
])
