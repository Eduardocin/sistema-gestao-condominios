import { useState } from 'react'
import { useContentFocus } from './useContentFocus'
import { Badge, Button, Card, CheckField, Heading, Input, MetricCard, Modal, Notice, RecordPhoto, Select, Table, Text } from '../../components'
import { EmployeeSelect, ResidentSelect } from './fields'
import { deliverPackage, formatTime, parcelStatus, personName, unitName } from './model'
import type { DemoState, Parcel } from './model'
import { ReceiptForm } from './ReceiptForm'
import styles from './Portaria.module.css'

export function ParcelBadge({ parcel }: { parcel: Parcel }) {
  return <Badge wrap variant={parcel.status === 'confirmed' ? 'success' : parcel.status === 'awaiting' ? 'primary' : 'warning'}>{parcelStatus[parcel.status]}</Badge>
}

export function ParcelHistory({ parcel }: { parcel: Parcel }) {
  return <div className={styles.stack}><Text size="sm"><strong>Recebida</strong> · {formatTime(parcel.receivedAt)}<br />Por {personName(parcel.receivedBy)}</Text>{parcel.deliveredAt && <Text size="sm"><strong>Entregue</strong> · {formatTime(parcel.deliveredAt)}<br />Por {personName(parcel.deliveredBy)} · Recebida por {personName(parcel.receiverId)}</Text>}{parcel.confirmedAt && <Text size="sm"><strong>Retirada confirmada</strong> · {formatTime(parcel.confirmedAt)}<br />Por {personName(parcel.confirmedBy)}</Text>}</div>
}

function PackageDetails({ parcel, onClose, onSave }: { parcel: Parcel; onClose: () => void; onSave: (parcel: Parcel) => void }) {
  const [receiverId, setReceiverId] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [checked, setChecked] = useState(false)
  const [error, setError] = useState('')
  return <Modal isOpen onClose={onClose} title={parcel.status === 'awaiting' ? 'Registrar entrega' : 'Detalhes da encomenda'}>
    <form className={styles.stack} onSubmit={(event) => {
      event.preventDefault()
      if (!checked) { setError('Confira a identidade e a entrega física antes de registrar.'); return }
      const result = deliverPackage(parcel, receiverId, employeeId, new Date().toISOString())
      if (!result.ok) { setError(result.error); return }
      onSave(result.value)
    }}>
      <Badge variant="neutral">FLUXO 02 · ENTREGA E CONFIRMAÇÃO</Badge>
      <div><Heading level={3} size="sm">{parcel.description}</Heading><Text size="sm" tone="secondary">{unitName(parcel.unitId)} · {personName(parcel.residentId)} · {parcel.id}</Text></div>
      <ParcelBadge parcel={parcel} /><RecordPhoto src={parcel.photo} alt={`Foto de ${parcel.description}`} /><ParcelHistory parcel={parcel} />
      {parcel.status === 'awaiting' ? <>
        <ResidentSelect unitId={parcel.unitId} label="Morador que está retirando" value={receiverId} onChange={setReceiverId} />
        <EmployeeSelect value={employeeId} onChange={setEmployeeId} />
        <CheckField checked={checked} onChange={(event) => setChecked(event.target.checked)}>Conferi a identidade e entreguei a encomenda ao morador selecionado.</CheckField>
        <Notice tone="warning">A encomenda ficará entregue, aguardando confirmação. Somente o morador que a recebeu confirma depois, em sua conta.</Notice>
        {error && <Notice tone="alert" role="alert">{error}</Notice>}
        <div className={styles.actions}><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button type="submit">Registrar entrega</Button></div>
      </> : <>{parcel.status === 'pending_confirmation' && <Notice tone="warning">Confirmação pendente de {personName(parcel.receiverId)}. A portaria pode entrar em contato por interfone ou telefone. A pendência permanece até o morador confirmar.</Notice>}<Button variant="secondary" onClick={onClose}>Fechar detalhes</Button></>}
    </form>
  </Modal>
}

export function PackagesView({ state, onSave, onCreate }: { state: DemoState; onSave: (parcel: Parcel) => void; onCreate: (parcel: Parcel) => void }) {
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = state.packages.find((parcel) => parcel.id === selectedId)
  useContentFocus('packages-title', !creating && !selected)
  const filtered = state.packages.filter((parcel) => (filter === 'all' || parcel.status === filter) && `${parcel.description} ${parcel.id} ${unitName(parcel.unitId)} ${personName(parcel.residentId)}`.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR')))
  if (creating) return <ReceiptForm onCancel={() => setCreating(false)} onSave={(parcel) => { onCreate(parcel); setCreating(false) }} />
  return <section className={styles.stack} aria-labelledby="packages-title">
    <div className={styles.headingRow}><div><Text size="sm" tone="secondary">ROTINA DA PORTARIA</Text><Heading level={1} id="packages-title" tabIndex={-1}>Encomendas</Heading><Text tone="secondary">Da chegada à retirada, acompanhe cada entrega.</Text></div><Button onClick={() => setCreating(true)}>+ Receber encomenda</Button></div>
    <div className={styles.metrics}><MetricCard label="Aguardando retirada" value={state.packages.filter((parcel) => parcel.status === 'awaiting').length} description="Disponíveis na portaria" /><MetricCard label="Aguardando confirmação" value={state.packages.filter((parcel) => parcel.status === 'pending_confirmation').length} description="Entregues aos moradores" tone="warning" /><MetricCard label="Retiradas confirmadas" value={state.packages.filter((parcel) => parcel.status === 'confirmed').length} description="Ciclo de entrega concluído" tone="success" /></div>
    <Card className={styles.stack}>
      <div className={styles.headingRow}><Heading level={2} size="md">Controle de encomendas</Heading><Text size="sm" tone="secondary">{filtered.length} registro(s)</Text></div>
      <div className={styles.filters}><Input label="Buscar encomenda" type="search" placeholder="Descrição, morador, unidade ou código" value={search} onChange={(event) => setSearch(event.target.value)} /><Select label="Status da encomenda" value={filter} onChange={(event) => setFilter(event.target.value)} options={[{ value: 'all', label: 'Todos os status' }, ...Object.entries(parcelStatus).map(([value, label]) => ({ value, label }))]} /></div>
      <Table caption="Encomendas do condomínio de exemplo" headers={['Encomenda', 'Destino', 'Recebimento', 'Status', 'Ação']} emptyMessage="Nenhuma encomenda encontrada. Ajuste a busca ou registre um recebimento." rows={filtered.map((parcel) => [<div key="parcel"><Text size="sm"><strong>{parcel.description}</strong></Text><Text size="xs" tone="secondary">{parcel.id}</Text></div>, <div key="unit"><Text size="sm">{unitName(parcel.unitId)}</Text><Text size="xs" tone="secondary">{personName(parcel.residentId)}</Text></div>, <Text key="date" size="sm">{formatTime(parcel.receivedAt)}</Text>, <ParcelBadge key="status" parcel={parcel} />, <Button key="action" variant="secondary" size="sm" onClick={() => setSelectedId(parcel.id)} aria-label={`${parcel.status === 'awaiting' ? 'Registrar entrega de' : 'Ver detalhes de'} ${parcel.description}`}>{parcel.status === 'awaiting' ? 'Registrar entrega' : 'Ver detalhes'}</Button>])} />
    </Card>
    <Notice>Receber → entregar → aguardar confirmação do morador. Nenhuma pendência é confirmada automaticamente.</Notice>
    {selected && <PackageDetails key={selected.id} parcel={selected} onClose={() => setSelectedId(null)} onSave={(parcel) => { onSave(parcel); setSelectedId(null) }} />}
  </section>
}
