import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router'
import {
  Badge,
  Button,
  Heading,
  Input,
  Notice,
  OperationsLayout,
  Select,
  Text,
} from '../../components'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import styles from '../resident/ResidentWorkspace.module.css'
import {
  auditError,
  auditFilterError,
  auditValue,
  createAuditClient,
  noAuditFilters,
  profileLabels,
} from './auditoria-api.ts'
import type { AuditFilters, AuditRecord, AuditReference } from './auditoria-api.ts'
import { platformNavigation } from '../auth/area-navigation'

const dateTime = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'medium',
  timeZone: 'America/Sao_Paulo',
})

export function AuditPage() {
  const { snapshot, client } = useAuth()
  const api = useMemo(() => createAuditClient(client.http), [client])
  const allowed = Boolean(snapshot.identity?.administrador_plataforma)
  const [draft, setDraft] = useState<AuditFilters>(noAuditFilters)
  const [filters, setFilters] = useState<AuditFilters>(noAuditFilters)
  const [condominiums, setCondominiums] = useState<AuditReference[]>([])
  const [records, setRecords] = useState<AuditRecord[]>([])
  const [next, setNext] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [error, setError] = useState('')
  const [filterError, setFilterError] = useState('')
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    if (!allowed) return
    const controller = new AbortController()
    api.condominiums(controller.signal).then(setCondominiums, () => undefined)
    return () => controller.abort()
  }, [api, allowed])

  useEffect(() => {
    if (!allowed) return
    const controller = new AbortController()
    api.records(filters, null, controller.signal).then(
      (page) => {
        if (controller.signal.aborted) return
        setRecords(page.items)
        setNext(page.next_cursor)
        setError('')
        setLoading(false)
      },
      (failure: unknown) => {
        if (controller.signal.aborted) return
        setRecords([])
        setNext(null)
        setError(auditError(failure))
        setLoading(false)
      },
    )
    return () => controller.abort()
  }, [api, allowed, filters, revision])

  if (!allowed) return <AccessDenied />

  function apply(event: FormEvent) {
    event.preventDefault()
    const problem = auditFilterError(draft)
    setFilterError(problem)
    if (problem) return
    setLoading(true)
    setFilters(draft)
  }

  function clear() {
    setDraft(noAuditFilters)
    setFilterError('')
    setLoading(true)
    setFilters(noAuditFilters)
  }

  async function loadMore() {
    if (!next || more) return
    setMore(true)
    try {
      const page = await api.records(filters, next)
      setRecords((current) => [...current, ...page.items])
      setNext(page.next_cursor)
      setError('')
    } catch (failure) {
      setError(auditError(failure))
    } finally {
      setMore(false)
    }
  }

  return (
    <OperationsLayout
      activeKey="audit"
      navigation={platformNavigation}
      workspace={{
        name: 'Gestão da plataforma',
        profile: 'Plataforma',
        tools: <Link to="/app/plataforma">Voltar</Link>,
      }}
    >
      <section className={styles.content}>
        <Heading level={1}>Auditoria</Heading>
        <Text tone="secondary">
          Registro somente de leitura das ações dos condomínios e da plataforma, do mais recente ao
          mais antigo.
        </Text>
        <form className={styles.filters} onSubmit={apply} aria-label="Filtros da auditoria">
          <Select
            label="Condomínio"
            placeholder="Todos os condomínios"
            options={condominiums.map(({ id, nome }) => ({ value: id, label: nome }))}
            value={draft.condominio_id}
            onChange={(event) => setDraft({ ...draft, condominio_id: event.target.value })}
          />
          <Input
            label="De"
            type="date"
            value={draft.de}
            onChange={(event) => setDraft({ ...draft, de: event.target.value })}
          />
          <Input
            label="Até"
            type="date"
            value={draft.ate}
            onChange={(event) => setDraft({ ...draft, ate: event.target.value })}
          />
          <Input
            label="Ação"
            value={draft.acao}
            maxLength={60}
            placeholder="Ex.: reserva. (todas)"
            onChange={(event) => setDraft({ ...draft, acao: event.target.value })}
          />
          <Input
            label="Tipo de recurso"
            value={draft.recurso_tipo}
            maxLength={60}
            placeholder="Ex.: reserva"
            onChange={(event) => setDraft({ ...draft, recurso_tipo: event.target.value })}
          />
          <div className={styles.actions}>
            <Button type="submit">Filtrar</Button>
            <Button variant="secondary" onClick={clear}>
              Limpar
            </Button>
          </div>
        </form>
        {filterError && (
          <Notice tone="alert" role="alert">
            {filterError}
          </Notice>
        )}
        {error && (
          <Notice tone="alert" role="alert">
            <div className={styles.actions}>
              {error}
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setRevision((value) => value + 1)}
              >
                Tentar novamente
              </Button>
            </div>
          </Notice>
        )}
        {loading && <Text role="status">Carregando registros…</Text>}
        {!loading && !error && !records.length && (
          <Text>Nenhum registro encontrado com esses filtros.</Text>
        )}
        {records.map((record) => (
          <AuditEntry key={record.id} record={record} />
        ))}
        {next && (
          <div>
            <Button variant="secondary" loading={more} onClick={() => void loadMore()}>
              Carregar mais
            </Button>
          </div>
        )}
      </section>
    </OperationsLayout>
  )
}

function AuditEntry({ record }: { record: AuditRecord }) {
  const keys = Array.from(
    new Set([...Object.keys(record.antes ?? {}), ...Object.keys(record.depois ?? {})]),
  )
  return (
    <article className={styles.listItem}>
      <div className={styles.actions}>
        <Badge variant="primary">{record.acao}</Badge>
        <Text size="sm" tone="secondary">
          {dateTime.format(new Date(record.criado_em))}
        </Text>
      </div>
      <Text size="sm">
        <strong>{record.usuario?.nome ?? 'Sistema ou visitante'}</strong>
        {record.perfil ? ` · ${profileLabels[record.perfil] ?? record.perfil}` : ''}
        {record.responsavel_nome ? ` · responsável: ${record.responsavel_nome}` : ''}
        {' · '}
        {record.condominio?.nome ?? 'Sem condomínio'}
      </Text>
      <Text size="sm" tone="secondary">
        {record.recurso_tipo ?? 'Sem recurso'}
        {record.recurso_id ? ` ${record.recurso_id}` : ''}
        {record.ip ? ` · IP ${record.ip}` : ''}
      </Text>
      {keys.length > 0 && (
        <details>
          <summary>Ver alterações</summary>
          <dl className={styles.content}>
            {keys.map((key) => (
              <div key={key}>
                <dt>
                  <strong>{key}</strong>
                </dt>
                <dd>
                  Antes: {auditValue(record.antes?.[key])} · Depois:{' '}
                  {auditValue(record.depois?.[key])}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </article>
  )
}
