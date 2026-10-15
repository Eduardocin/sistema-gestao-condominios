import { createBrowserRouter } from 'react-router'
import { HomePage } from '../features/home/HomePage'
import { NotFoundPage } from './NotFoundPage'

export const router = createBrowserRouter([
  { path: '/', element: <HomePage /> },
  { path: '*', element: <NotFoundPage /> },
])
