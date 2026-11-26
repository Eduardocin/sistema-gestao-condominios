import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Button, OperationsLayout } from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import styles from './AdminAreas.module.css'

/** Layout comum às telas de áreas e reservas, com a mesma checagem de acesso da NoticesPage. */
export function AdminAreasShell({
  activeKey,
  children,
}: {
  activeKey: 'areas' | 'reservations'
  children: ReactNode
}) {
  const { snapshot, client } = useAuth()
  const condominium = snapshot.identity?.condominio
  // Só esconde a tela; quem autoriza de verdade é a API (perfil relido a cada requisição).
  if (condominium?.perfil !== 'administracao' || condominium.status !== 'ativo')
    return <AccessDenied />

  const tools = (
    <div className={styles.actions}>
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
      activeKey={activeKey}
      navigation={[
        { key: 'overview', label: 'Visão geral', to: '/app/administracao', symbol: '⌂' },
        { key: 'areas', label: 'Áreas comuns', to: '/app/administracao/areas-comuns', symbol: '◫' },
        { key: 'reservations', label: 'Reservas', to: '/app/administracao/reservas', symbol: '▦' },
      ]}
      workspace={{ name: condominium.nome, profile: 'Administração', tools }}
    >
      {/* A chave remonta o conteúdo ao trocar de condomínio: nada da lista anterior vaza. */}
      <div key={condominium.id} className={styles.content}>
        {children}
      </div>
    </OperationsLayout>
  )
}
