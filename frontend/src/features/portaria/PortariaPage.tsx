import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { Button, Modal, Notice, OperationsLayout, Text } from '../../components'
import { seedDemo } from './model'
import type { Parcel, Visit } from './model'
import { PackagesView } from './PackagesView'
import { ResidentView } from './ResidentView'
import { VisitorsView } from './VisitorsView'
import styles from './Portaria.module.css'

const navigation = [
  { key: 'encomendas', label: 'Encomendas', to: '/prototipos/portaria', symbol: '▣' },
  { key: 'visitantes', label: 'Visitantes', to: '/prototipos/portaria?visao=visitantes', symbol: '↔' },
  { key: 'morador', label: 'Prévia do morador', to: '/prototipos/portaria?visao=morador', symbol: '⌂' },
]

export function PortariaPage() {
  const [params] = useSearchParams()
  const view = ['visitantes', 'morador'].includes(params.get('visao') ?? '') ? params.get('visao')! : 'encomendas'
  const [state, setState] = useState(() => seedDemo(new Date().toISOString()))
  const [message, setMessage] = useState('')
  const [resetting, setResetting] = useState(false)
  const [version, setVersion] = useState(0)
  function saveParcel(parcel: Parcel) {
    setState((current) => ({ ...current, packages: current.packages.map((item) => item.id === parcel.id ? parcel : item) }))
    setMessage(parcel.status === 'confirmed' ? 'Retirada confirmada pelo morador.' : 'Entrega registrada. Aguardando confirmação do morador.')
  }
  function saveVisit(visit: Visit) {
    setState((current) => ({ ...current, visits: current.visits.map((item) => item.id === visit.id ? visit : item) }))
    setMessage('Saída registrada. Visita encerrada.')
  }
  return <OperationsLayout activeKey={view} navigation={navigation} tools={<Button variant="secondary" size="sm" onClick={() => setResetting(true)}>Reiniciar demonstração</Button>}>
    <div className={styles.stack}>
      {message && <Notice tone="success" role="status"><div className={styles.headingRow}><span>{message}</span><Button size="sm" variant="secondary" onClick={() => setMessage('')}>Dispensar aviso</Button></div></Notice>}
      {view === 'encomendas' && <PackagesView key={`packages-${version}`} state={state} onSave={saveParcel} onCreate={(parcel) => { setState((current) => ({ ...current, packages: [parcel, ...current.packages] })); setMessage('Recebimento registrado. A encomenda aguarda retirada.') }} />}
      {view === 'visitantes' && <VisitorsView key={`visitors-${version}`} state={state} onSave={saveVisit} onChange={(nextState, notice) => { setState(nextState); setMessage(notice) }} />}
      {view === 'morador' && <ResidentView key={`resident-${version}`} state={state} onSave={saveParcel} />}
    </div>
    <Modal isOpen={resetting} onClose={() => setResetting(false)} title="Reiniciar demonstração"><div className={styles.stack}><Text>Os registros e as fotos adicionados nesta aba serão descartados. Os exemplos iniciais serão restaurados.</Text><div className={styles.actions}><Button variant="secondary" onClick={() => setResetting(false)}>Cancelar</Button><Button onClick={() => { setState(seedDemo(new Date().toISOString())); setVersion((current) => current + 1); setMessage('Demonstração reiniciada.'); setResetting(false) }}>Restaurar exemplos</Button></div></div></Modal>
  </OperationsLayout>
}
