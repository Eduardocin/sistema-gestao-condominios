import { useEffect, useState, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import { AuthContext } from './context'
import { createSessionClient } from './session'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => {
    let storage: Storage | undefined
    try { storage = window.sessionStorage } catch { /* Storage pode ser bloqueado pelo navegador. */ }
    return createSessionClient(import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1', storage)
  })
  const snapshot = useSyncExternalStore(client.subscribe, client.getSnapshot)
  useEffect(() => { void client.restore() }, [client])
  return <AuthContext.Provider value={{ client, snapshot }}>{children}</AuthContext.Provider>
}
