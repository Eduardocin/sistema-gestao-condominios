import { useState } from 'react'
import type { FormEvent } from 'react'
import { Badge, Button, Card, CheckField, Heading, Notice, Select, Text } from '../../components'
import { EmployeeSelect, ResidentSelect, UnitSelect } from './fields'
import { enterVisitor, formatTime, personName, resolveAuthorization, visitors } from './model'
import type { Contact, ContactResponse, DemoState } from './model'
import { useContentFocus } from './useContentFocus'
import styles from './Portaria.module.css'

export function EntryForm({ state, onSave, onCancel }: { state: DemoState; onSave: (state: DemoState, message: string) => void; onCancel: () => void }) {
  const [visitorId, setVisitorId] = useState('')
  const [unitId, setUnitId] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [identityChecked, setIdentityChecked] = useState(false)
  const [residentId, setResidentId] = useState('')
  const [channel, setChannel] = useState<Contact['channel']>('intercom')
  const [response, setResponse] = useState<ContactResponse | ''>('')
  const [error, setError] = useState('')
  useContentFocus('entry-title')
  const authorization = resolveAuthorization(state.authorizations, visitorId, unitId, new Date().toISOString())
  function changeDestination(value: string) { setUnitId(value); setVisitorId(''); setIdentityChecked(false); setResidentId(''); setResponse(''); setError('') }
  function submit(event: FormEvent) {
    event.preventDefault()
    const now = new Date().toISOString()
    if (!identityChecked) { setError('Confira a identidade do visitante antes de registrar a decisão.'); return }
    if (!authorization && (response === 'denied' || response === 'no_answer')) {
      onSave({ ...state, attempts: [{ id: `TENT-${crypto.randomUUID().slice(0, 8)}`, visitorId, unitId, employeeId, at: now, contact: { residentId, channel, response } }, ...state.attempts] }, response === 'denied' ? 'Autorização negada registrada. Entrada não liberada.' : 'Contato sem resposta registrado. Entrada não liberada.')
      return
    }
    const result = enterVisitor(state, { visitorId, unitId, employeeId, identityChecked, authorizationId: authorization?.id, residentId, channel, response: response || undefined }, now)
    if (!result.ok) { setError(result.error); return }
    onSave(result.value, 'Entrada registrada. A visita está em andamento.')
  }
  return <section className={styles.stack} aria-labelledby="entry-title">
    <div className={styles.headingRow}><div><Text size="sm" tone="secondary">FLUXO 03 · ENTRADA DE VISITANTES</Text><Heading level={1} id="entry-title" tabIndex={-1}>Registrar entrada</Heading><Text tone="secondary">Identifique o visitante e confira a autorização de acesso.</Text></div><Button variant="secondary" onClick={onCancel}>Voltar aos visitantes</Button></div>
    <form className={styles.formLayout} onSubmit={submit}>
      <Card className={styles.stack}>
        <Heading level={2} size="md">Quem está chegando?</Heading>
        <UnitSelect value={unitId} onChange={changeDestination} />
        <Select label="Visitante cadastrado" required disabled={!unitId} options={visitors.filter((visitor) => visitor.unitId === unitId).map((visitor) => ({ value: visitor.id, label: visitor.name }))} value={visitorId} onChange={(event) => { setVisitorId(event.target.value); setIdentityChecked(false); setResponse(''); setResidentId(''); setError('') }} hint="Selecione a unidade para consultar seus visitantes cadastrados. O cadastro avulso ficará para uma etapa futura." />
        <EmployeeSelect value={employeeId} onChange={setEmployeeId} />
        <CheckField checked={identityChecked} onChange={(event) => setIdentityChecked(event.target.checked)}>Conferi a identidade do visitante e a unidade de destino.</CheckField>
        <Heading level={2} size="md">Autorização de acesso</Heading>
        {!visitorId || !unitId ? <Notice>Selecione o destino e o visitante para consultar a autorização.</Notice> : authorization ? <Notice tone="success" title="Autorização prévia válida"><Text as="span" size="sm">Autorizado por {personName(authorization.residentId)}. Válida de {formatTime(authorization.startsAt)} até {formatTime(authorization.endsAt)}. Permite novas entradas durante esse período, após registrar a saída da visita anterior.</Text></Notice> : <>
          <Notice tone="warning" title="Consulte o morador">Nenhuma autorização prévia válida para esta visita. Entre em contato por interfone ou telefone e registre a resposta.</Notice>
          <ResidentSelect label="Morador consultado" value={residentId} onChange={(value) => { setResidentId(value); setResponse('') }} unitId={unitId} />
          <div className={styles.twoColumns}><Select label="Forma de contato" value={channel} onChange={(event) => { setChannel(event.target.value as Contact['channel']); setResponse('') }} options={[{ value: 'intercom', label: 'Interfone' }, { value: 'phone', label: 'Telefone' }]} /><Select label="Resposta do morador" required value={response} onChange={(event) => setResponse(event.target.value as ContactResponse)} options={[{ value: 'authorized', label: 'Autorizou a entrada' }, { value: 'denied', label: 'Não autorizou' }, { value: 'no_answer', label: 'Sem resposta' }]} /></div>
          {(response === 'denied' || response === 'no_answer') && <Notice tone="alert">Entrada não liberada. O contato ficará registrado, sem iniciar uma visita.</Notice>}
        </>}
        {error && <Notice tone="alert" role="alert">{error}</Notice>}
        <div className={styles.actions}><Button variant="secondary" onClick={onCancel}>Cancelar</Button><Button type="submit" disabled={!visitorId || !unitId}>{!authorization && (response === 'denied' || response === 'no_answer') ? 'Registrar contato sem entrada' : 'Confirmar entrada'}</Button></div>
      </Card>
      <div className={styles.stack}><Card className={styles.stack}><Badge variant="primary">Acesso com autorização</Badge><Heading level={2} size="md">Cada visita tem seu registro</Heading><Text size="sm" tone="secondary">A autorização prévia vale apenas para o visitante, o destino e o período indicados.</Text><Text size="sm" tone="secondary">Sem autorização válida, a entrada depende da resposta do morador. Sem resposta ou com negativa, o visitante não entra.</Text></Card><Notice>Na saída, encerre a visita em andamento. Uma próxima entrada exige uma nova verificação de autorização.</Notice></div>
    </form>
  </section>
}
