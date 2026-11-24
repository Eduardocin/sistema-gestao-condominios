import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Button, Card, Heading, Notice, Select, Text } from '../../components'
import { useAuth } from '../auth/context'
import { ResidentWorkspace } from './ResidentWorkspace'
import styles from './ResidentWorkspace.module.css'
import { createResidentCommunityClient } from './resident-community-api'
import type { ResidentCommunityClient } from './resident-community-api'

type CommunitySection = 'reserve' | 'reservations' | 'occurrences'

export interface CommunityUnit {
  id: string
  identificacao: string
}

interface Props {
  activeKey: CommunitySection
  title: string
  children: (unit: CommunityUnit, api: ResidentCommunityClient) => ReactNode
}

export function ResidentCommunity(props: Props) {
  return (
    <ResidentWorkspace activeKey={props.activeKey}>
      <CommunityContent {...props} />
    </ResidentWorkspace>
  )
}

function CommunityContent({ title, children }: Props) {
  const { snapshot, client } = useAuth()
  const api = useMemo(() => createResidentCommunityClient(client.http), [client])
  const units = snapshot.identity?.unidades ?? []
  const [unitId, setUnitId] = useState('')
  const unit = units.find(({ id }) => id === unitId) ?? units[0]

  return (
    <section className={styles.content}>
      <Heading level={1}>{title}</Heading>
      {unit ? (
        <Card className={styles.content}>
          <Select
            label="Unidade"
            options={units.map(({ id, identificacao }) => ({ value: id, label: identificacao }))}
            value={unit.id}
            onChange={(event) => setUnitId(event.target.value)}
            disabled={units.length === 1}
          />
          <div key={unit.id} className={styles.content}>
            {children(unit, api)}
          </div>
        </Card>
      ) : (
        <Notice tone="warning">
          Sua conta ainda não tem uma unidade vinculada neste condomínio.
        </Notice>
      )}
    </section>
  )
}

export function CommunityPageControls({
  page,
  pages,
  onChange,
}: {
  page: number
  pages: number
  onChange: (page: number) => void
}) {
  if (pages <= 1) return null
  return (
    <nav className={styles.pagination} aria-label="Paginação">
      <Text size="sm">
        Página {page} de {pages}
      </Text>
      <div>
        <Button
          size="sm"
          variant="secondary"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          Anterior
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Próxima
        </Button>
      </div>
    </nav>
  )
}

export function CommunityLoadError({ children, retry }: { children: string; retry: () => void }) {
  return (
    <Notice tone="alert" role="alert">
      <div className={styles.actions}>
        {children}
        <Button size="sm" variant="secondary" onClick={retry}>
          Tentar novamente
        </Button>
      </div>
    </Notice>
  )
}
