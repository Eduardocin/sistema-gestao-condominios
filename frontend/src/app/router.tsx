import { createBrowserRouter } from 'react-router'
import { HomePage } from '../features/home/HomePage'
import { DesignSystemPage } from '../features/design-system/DesignSystemPage'
import { NotFoundPage } from './NotFoundPage'

export const router = createBrowserRouter([
  { path: '/', element: <HomePage /> },
  { path: '/design-system', element: <DesignSystemPage /> },
  { path: '*', element: <NotFoundPage /> },
])
