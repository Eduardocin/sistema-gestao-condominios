import { useState } from 'react'
import { useContentFocus } from './useContentFocus'
import { Badge, Button, Card, CheckField, Heading, Input, MetricCard, Modal, Notice, Select, Table, Text } from '../../components'
import { EmployeeSelect } from './fields'
import { closeVisit, formatTime, personName, unitName } from './model'
import type { DemoState, Visit } from './model'
import { EntryForm } from './EntryForm'
import styles from './Portaria.module.css'

function VisitDetails({ visit, onClose, onSave }: { visit: Visit; onClose: () => void; onSave: (visit: Visit) => void }) {
  const [employeeId, setEmployeeId] = useState('')
  const [checked, setChecked] = useState(false)
  const [error, setError] = useState('')
  return <Modal isOpen onClose={onClose} title={visit.status === 'active' ? 'Registrar saída' : 'Histórico da visita'}><form className={styles.stack} onSubmit={(event) => {
    event.preventDefault()
    if (!checked) { setError('Confirme que o visitante saiu do condomínio.'); return }
    const result = closeVisit(visit, employeeId, new Date().toISOString())
    if (!result.ok) { setError(result.error); return }
    onSave(result.value)
  }}><Badge variant="neutral">FLUXO 04 · SAÍDA DE VISITANTES</Badge><div><Heading level={3}>{personName(visit.visitorId)}</Heading><Text tone="secondary">{unitName(visit.unitId)} · {visit.id}</Text></div><Text size="sm"><strong>Entrada</strong> · {formatTime(visit.enteredAt)}<br />Por {personName(visit.enteredBy)}</Text><Text size="sm"><strong>Autorização</strong><br />{visit.authorizationId ? `Prévia · ${visit.authorizationId}` : `${personName(visit.contact?.residentId)} · ${visit.contact?.channel === 'phone' ? 'Telefone' : 'Interfone'}`}</Text>{visit.status === 'active' ? <><EmployeeSelect value={employeeId} onChange={setEmployeeId} /><CheckField checked={checked} onChange={(event) => setChecked(event.target.checked)}>Confirmei a saída deste visitante do condomínio.</CheckField><Notice>A saída encerra esta visita e mantém o histórico. Não exige confirmação do morador.</Notice>{error && <Notice tone="alert" role="alert">{error}</Notice>}<div className={styles.actions}><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button type="submit">Confirmar saída</Button></div></> : <><Text size="sm"><strong>Saída</strong> · {formatTime(visit.exitedAt)}<br />Por {personName(visit.exitedBy)}</Text><Badge variant="neutral">Encerrada</Badge><Button variant="secondary" onClick={onClose}>Fechar histórico</Button></>}</form></Modal>
}

export function VisitorsView({ state, onChange, onSave }: { state: DemoState; onChange: (state: DemoState, message: string) => void; onSave: (visit: Visit) => void }) {
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('active')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = state.visits.find((visit) => visit.id === selectedId)
  useContentFocus('visitors-title', !creating && !selected)
  const filtered = state.visits.filter((visit) => (filter === 'all' || visit.status === filter) && `${personName(visit.visitorId)} ${unitName(visit.unitId)}`.toLocaleLowerCase('pt-BR').includes(search.toLocaleLowerCase('pt-BR')))
  if (creating) return <EntryForm state={state} onCancel={() => setCreating(false)} onSave={(nextState, message) => { onChange(nextState, message); setCreating(false) }} />
  return <section className={styles.stack} aria-labelledby="visitors-title">
    <div className={styles.headingRow}><div><Text size="sm" tone="secondary">CONTROLE DE ACESSO</Text><Heading level={1} id="visitors-title" tabIndex={-1}>Visitantes</Heading><Text tone="secondary">Saiba quem está no condomínio e mantenha as visitas organizadas.</Text></div><Button onClick={() => setCreating(true)}>+ Registrar entrada</Button></div>
    <div className={styles.metrics}><MetricCard label="Visitas em andamento" value={state.visits.filter((visit) => visit.status === 'active').length} description="Aguardando registro de saída" /><MetricCard label="Visitas encerradas" value={state.visits.filter((visit) => visit.status === 'closed').length} description="Entrada e saída registradas" tone="success" /><MetricCard label="Contatos sem entrada" value={state.attempts.length} description="Negativa ou ausência de resposta" tone="warning" /></div>
    <Card className={styles.stack}><Heading level={2} size="md">Controle de visitas</Heading><div className={styles.filters}><Input label="Buscar visitante" type="search" placeholder="Nome ou unidade de destino" value={search} onChange={(event) => setSearch(event.target.value)} /><Select label="Status da visita" value={filter} onChange={(event) => setFilter(event.target.value)} options={[{ value: 'active', label: 'Em andamento' }, { value: 'closed', label: 'Encerradas' }, { value: 'all', label: 'Todas as visitas' }]} /></div><Table caption="Visitas do condomínio de exemplo" headers={['Visitante', 'Destino', 'Entrada', 'Status', 'Ação']} emptyMessage="Nenhuma visita encontrada para este filtro." rows={filtered.map((visit) => [<Text key="visitor" size="sm"><strong>{personName(visit.visitorId)}</strong></Text>, unitName(visit.unitId), formatTime(visit.enteredAt), <Badge key="status" variant={visit.status === 'active' ? 'primary' : 'neutral'}>{visit.status === 'active' ? 'Em andamento' : 'Encerrada'}</Badge>, <Button key="action" variant="secondary" size="sm" onClick={() => setSelectedId(visit.id)} aria-label={`${visit.status === 'active' ? 'Registrar saída de' : 'Ver histórico de'} ${personName(visit.visitorId)}`}>{visit.status === 'active' ? 'Registrar saída' : 'Ver histórico'}</Button>])} /></Card>
    {state.attempts.length > 0 && <Card className={styles.stack}><Heading level={2} size="md">Contatos sem liberação de entrada</Heading><Table caption="Histórico de contatos externos" headers={['Visitante', 'Destino', 'Morador consultado', 'Contato', 'Resposta', 'Registro']} rows={state.attempts.map((attempt) => [personName(attempt.visitorId), unitName(attempt.unitId), personName(attempt.contact.residentId), attempt.contact.channel === 'phone' ? 'Telefone' : 'Interfone', <Badge key="response" variant="warning">{attempt.contact.response === 'denied' ? 'Não autorizou' : 'Sem resposta'}</Badge>, <Text key="date" size="sm">{formatTime(attempt.at)}<br />{personName(attempt.employeeId)}</Text>])} /></Card>}
    <Notice>Visitas sem saída continuam em andamento até a conferência da portaria. Não há encerramento automático.</Notice>
    {selected && <VisitDetails key={selected.id} visit={selected} onClose={() => setSelectedId(null)} onSave={(visit) => { onSave(visit); setSelectedId(null) }} />}
  </section>
}
