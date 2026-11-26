import { createBrowserRouter } from 'react-router'
import { HomePage } from '../features/home/HomePage'
import { StatusPage } from '../features/home/StatusPage'
import { AccessPage } from '../features/access/AccessPage'
import { DesignSystemPage } from '../features/design-system/DesignSystemPage'
import { NotFoundPage } from './NotFoundPage'
import { PortariaPage } from '../features/portaria/PortariaPage'
import { LoginPage } from '../features/auth/LoginPage'
import { RegistrationPage } from '../features/auth/RegistrationPage'
import { EmployeesPage } from '../features/employees/EmployeesPage'
import {
  AccessDenied,
  AppEntry,
  RequireSession,
  SelectCondominiumPage,
} from '../features/auth/SessionPages'
import { WorkspacePage } from '../features/auth/WorkspacePage'
import { PackagesWorkspacePage } from '../features/portaria/PackagesWorkspacePage'
import { ResidentPackagesPage } from '../features/portaria/ResidentPackagesPage'
import { VisitorsWorkspacePage } from '../features/portaria/VisitorsWorkspacePage'
import { ResidentVisitorsPage } from '../features/resident/ResidentVisitorsPage'
import { ResidentVehiclesPage } from '../features/resident/ResidentVehiclesPage'
import { ApprovalPage } from '../features/condominiums/ApprovalPage'
import { CondominiumWizard } from '../features/condominiums/CondominiumWizard'
import { AccessKeysPage } from '../features/condominiums/AccessKeysPage'
import { ResidentLinkPage } from '../features/condominiums/ResidentLinkPage'
import {
  ResidentReservationsPage,
  ResidentReservePage,
} from '../features/resident/ResidentReservationsPages'
import { ResidentOccurrencesPage } from '../features/resident/ResidentOccurrencesPage'

export const router = createBrowserRouter([
  { path: '/', element: <HomePage /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/cadastro', element: <AccessPage /> },
  { path: '/cadastro/morador', element: <RegistrationPage key="morador" profile="morador" /> },
  {
    path: '/cadastro/administracao',
    element: <RegistrationPage key="administracao" profile="administracao" />,
  },
  { path: '/status', element: <StatusPage /> },
  { path: '/design-system', element: <DesignSystemPage /> },
  { path: '/prototipos/portaria', element: <PortariaPage /> },
  { path: '/selecionar-condominio', element: <SelectCondominiumPage /> },
  { path: '/app', element: <AppEntry /> },
  { path: '/app/plataforma/condominios', element: <RequireSession><ApprovalPage /></RequireSession> },
  { path: '/app/cadastrar-condominio', element: <RequireSession><CondominiumWizard /></RequireSession> },
  { path: '/app/administracao/chaves', element: <RequireSession><AccessKeysPage /></RequireSession> },
  { path: '/app/vincular-unidade', element: <RequireSession><ResidentLinkPage /></RequireSession> },
  {
    path: '/app/administracao/funcionarios',
    element: (
      <RequireSession>
        <EmployeesPage />
      </RequireSession>
    ),
  },
  {
    path: '/app/portaria/encomendas',
    element: (
      <RequireSession>
        <PackagesWorkspacePage />
      </RequireSession>
    ),
  },
  {
    path: '/app/portaria/visitantes',
    element: (
      <RequireSession>
        <VisitorsWorkspacePage />
      </RequireSession>
    ),
  },
  {
    path: '/app/morador/encomendas',
    element: (
      <RequireSession>
        <ResidentPackagesPage />
      </RequireSession>
    ),
  },
  {
    path: '/app/morador/visitantes',
    element: (
      <RequireSession>
        <ResidentVisitorsPage />
      </RequireSession>
    ),
  },
  {
    path: '/app/morador/veiculos',
    element: (
      <RequireSession>
        <ResidentVehiclesPage />
      </RequireSession>
    ),
  },
  ...[
    { path: '/app/morador/areas-comuns', Page: ResidentReservePage },
    { path: '/app/morador/reservas', Page: ResidentReservationsPage },
    { path: '/app/morador/ocorrencias', Page: ResidentOccurrencesPage },
  ].map(({ path, Page }) => ({
    path,
    element: (
      <RequireSession>
        <Page />
      </RequireSession>
    ),
  })),
  ...['morador', 'portaria', 'administracao', 'plataforma', 'sem-condominio'].map((area) => ({
    path: `/app/${area}`,
    element: <WorkspacePage area={area} />,
  })),
  {
    path: '/acesso-negado',
    element: (
      <RequireSession>
        <AccessDenied />
      </RequireSession>
    ),
  },
  { path: '*', element: <NotFoundPage /> },
])
