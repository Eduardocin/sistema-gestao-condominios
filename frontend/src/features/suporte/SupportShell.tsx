import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Heading, OperationsLayout } from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import styles from '../resident/ResidentWorkspace.module.css'
import { createSupportClient } from './suporte-api.ts'
import type { SupportClient, SupportScope } from './suporte-api.ts'
import { adminNavigation, platformNavigation } from '../auth/area-navigation'

interface Props {
  area: SupportScope
  activeKey: string
  title: string
  children: (api: SupportClient) => ReactNode
}

/** Moldura das telas de suporte, comunicados e relatório: confere o perfil e entrega o cliente da API. */
export function SupportShell({ area, activeKey, title, children }: Props) {
  const { snapshot, client } = useAuth()
  const api = useMemo(() => createSupportClient(client.http), [client])
  const identity = snapshot.identity
  const allowed =
    area === 'plataforma'
      ? Boolean(identity?.administrador_plataforma)
      : identity?.condominio?.perfil === 'administracao' && identity.condominio.status === 'ativo'
  if (!allowed) return <AccessDenied />

  return (
    <OperationsLayout
      activeKey={activeKey}
      navigation={area === 'plataforma' ? platformNavigation : adminNavigation}
      workspace={{
        name:
          area === 'plataforma'
            ? 'Gestão da plataforma'
            : (identity?.condominio?.nome ?? 'Condomínio'),
        profile: area === 'plataforma' ? 'Plataforma' : 'Administração',
        tools: <Link to={`/app/${area}`}>Voltar</Link>,
      }}
    >
      <section className={styles.content}>
        <Heading level={1}>{title}</Heading>
        {children(api)}
      </section>
    </OperationsLayout>
  )
}
