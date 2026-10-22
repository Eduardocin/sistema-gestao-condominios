import { createBrowserRouter } from 'react-router'
import { HomePage } from '../features/home/HomePage'
import { StatusPage } from '../features/home/StatusPage'
import { AccessPage } from '../features/access/AccessPage'
import { DesignSystemPage } from '../features/design-system/DesignSystemPage'
import { NotFoundPage } from './NotFoundPage'

export const router = createBrowserRouter([
  { path: '/', element: <HomePage /> },
  { path: '/login', element: <AccessPage mode="login" /> },
  { path: '/cadastro', element: <AccessPage mode="cadastro" /> },
  { path: '/status', element: <StatusPage /> },
  { path: '/design-system', element: <DesignSystemPage /> },
  { path: '*', element: <NotFoundPage /> },
])
