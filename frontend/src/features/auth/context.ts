import { createContext, useContext } from 'react'
import type { SessionClient } from './session'
import type { SessionSnapshot } from './types'

export const AuthContext = createContext<{ client: SessionClient; snapshot: SessionSnapshot } | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('O acesso à sessão exige AuthProvider.')
  return value
}
