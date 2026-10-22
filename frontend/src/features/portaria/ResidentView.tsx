import { useState } from 'react'
import { useContentFocus } from './useContentFocus'
import { Button, Card, CheckField, Heading, Modal, Notice, RecordPhoto, Select, Text } from '../../components'
import { confirmPackage, personName, residents, unitName } from './model'
import type { DemoState, Parcel } from './model'
import { ParcelBadge, ParcelHistory } from './PackagesView'
import styles from './Portaria.module.css'

export function ResidentView({ state, onSave }: { state: DemoState; onSave: (parcel: Parcel) => void }) {
  const [residentId, setResidentId] = useState('ana')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checked, setChecked] = useState(false)
  const [error, setError] = useState('')
  const resident = residents.find((person) => person.id === residentId)!
  const selected = state.packages.find((parcel) => parcel.id === selectedId)
  useContentFocus('resident-title', !selected)
  const packages = state.packages.filter((parcel) => parcel.unitId === resident.unitId)
  return <section className={styles.stack} aria-labelledby="resident-title">
    <div><Text size="sm" tone="secondary">FLUXO 02 · CONFIRMAÇÃO PELO MORADOR</Text><Heading level={1} id="resident-title" tabIndex={-1}>Minhas encomendas</Heading><Text tone="secondary">Confira o que chegou e confirme as entregas que você recebeu.</Text></div>
    <Notice title="Prévia da experiência do morador">O seletor abaixo serve apenas para testar esta demonstração. No sistema integrado, a identidade virá da conta autenticada do morador.</Notice>
    <div className={styles.filters}><Select label="Morador de exemplo" value={residentId} onChange={(event) => setResidentId(event.target.value)} options={residents.map((person) => ({ value: person.id, label: `${person.name} · ${unitName(person.unitId)}` }))} /></div>
    <div className={styles.residentCards}>{packages.map((parcel) => <Card key={parcel.id} className={styles.stack}><ParcelBadge parcel={parcel} /><RecordPhoto src={parcel.photo} alt={`Foto de ${parcel.description}`} /><div><Heading level={2} size="md">{parcel.description}</Heading><Text size="sm" tone="secondary">Para {personName(parcel.residentId)} · {unitName(parcel.unitId)}</Text></div><ParcelHistory parcel={parcel} />{parcel.status === 'pending_confirmation' && (parcel.receiverId === residentId ? <Button onClick={() => { setSelectedId(parcel.id); setChecked(false); setError('') }}>Confirmar que recebi</Button> : <Notice tone="warning">A confirmação cabe a {personName(parcel.receiverId)}, que recebeu esta encomenda.</Notice>)}{parcel.status === 'awaiting' && <Text size="sm" tone="secondary">Disponível para retirada na portaria.</Text>}</Card>)}</div>
    {packages.length === 0 && <Card><Text>Nenhuma encomenda para sua unidade neste momento.</Text></Card>}
    {selected && <Modal isOpen onClose={() => setSelectedId(null)} title="Confirmar recebimento da encomenda"><div className={styles.stack}><Text>Você está confirmando que recebeu <strong>{selected.description}</strong>.</Text><CheckField checked={checked} onChange={(event) => setChecked(event.target.checked)}>Sim, esta encomenda foi entregue a mim.</CheckField>{error && <Notice tone="alert" role="alert">{error}</Notice>}<div className={styles.actions}><Button variant="secondary" onClick={() => setSelectedId(null)}>Voltar</Button><Button disabled={!checked} onClick={() => { const result = confirmPackage(selected, residentId, new Date().toISOString()); if (!result.ok) { setError(result.error); return } onSave(result.value); setSelectedId(null) }}>Confirmar recebimento</Button></div></div></Modal>}
  </section>
}
