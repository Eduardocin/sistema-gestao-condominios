import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Button, OperationsLayout } from '../../components'
import { AccessDenied } from '../auth/SessionPages'
import { useAuth } from '../auth/context'
import { residentNavigation } from './resident-navigation'
import styles from './ResidentWorkspace.module.css'

interface Props {
  activeKey: 'packages' | 'visitors' | 'vehicles'
  children: ReactNode
}

export function ResidentWorkspace({ activeKey, children }: Props) {
  const { snapshot, client } = useAuth()
  const identity = snapshot.identity
  const condominium = identity?.condominio
  if (
    identity?.administrador_plataforma ||
    condominium?.perfil !== 'morador' ||
    condominium.status !== 'ativo'
  ) {
    return <AccessDenied />
  }

  const tools = (
    <div className={styles.tools}>
      {snapshot.condominiums.length > 1 && (
        <Link to="/selecionar-condominio">Trocar condomínio</Link>
      )}
      <Button variant="secondary" size="sm" onClick={() => client.logout()}>
        Sair
      </Button>
    </div>
  )

  return (
    <OperationsLayout
      key={condominium.id}
      activeKey={activeKey}
      navigation={residentNavigation}
      workspace={{ name: condominium.nome, profile: 'Morador', tools }}
    >
      {children}
    </OperationsLayout>
  )
}
