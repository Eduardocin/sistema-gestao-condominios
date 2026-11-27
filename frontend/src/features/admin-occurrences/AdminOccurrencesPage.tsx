import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router'
import {
  Badge,
  Button,
  Card,
  Heading,
  Input,
  Modal,
  Notice,
  OperationsLayout,
  Select,
  Table,
  Text,
} from '../../components'
import { FormField } from '../../components/FormField'
import fieldStyles from '../../components/FormField.module.css'
import { useAuth } from '../auth/context'
import { AccessDenied } from '../auth/SessionPages'
import { createAdminOccurrencesClient } from './admin-occurrences-api'
import type {
  AdminOccurrencesClient,
  Attachment,
  InteractionType,
  OccurrenceStatus,
  Responsible,
} from './admin-occurrences-api'
import {
  ALREADY_RESOLVED,
  errorStatus,
  isAlreadyResolved,
  occurrenceErrorMessage,
} from './occurrence-errors'
import {
  DEFAULT_FILTERS,
  TEXT_MAX,
  buildOccurrenceParams,
  formatDateTime,
  openingAttachments,
  validateReply,
  validateResolution,
} from './occurrence-form'
import type { InteractionErrors, OccurrenceFilters } from './occurrence-form'
import { useRefreshableQuery } from './use-refreshable-query'
import styles from './AdminOccurrences.module.css'
import { adminNavigation } from '../auth/area-navigation'

// O Select do design system trava a opção vazia (placeholder); "todos" usa um valor próprio.
const ALL = '*'
const statusOptions = [
  { value: 'em_aberto', label: 'Em aberto' },
  { value: 'resolvida', label: 'Resolvidas' },
  { value: ALL, label: 'Todas' },
]
const interactionLabels: Record<InteractionType, string> = {
  resposta: 'Resposta',
  comentario: 'Comentário',
  resolucao: 'Resolução',
  reabertura: 'Reabertura',
}

type Feedback = { message: string; tone: 'success' | 'alert' }
type Responsibles = {
  list: Responsible[] | undefined
  error: string | undefined
  reload: () => void
}

export function AdminOccurrencesPage() {
  const { snapshot, client } = useAuth()
  const condominium = snapshot.identity?.condominio
  // Mesma checagem da AccessKeysPage. Só esconde a tela: quem autoriza é a API.
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
      activeKey="occurrences"
      navigation={adminNavigation}
      workspace={{ name: condominium.nome, profile: 'Administração', tools }}
    >
      {/* A chave remonta o conteúdo ao trocar de condomínio: nada da lista anterior vaza. */}
      <div key={condominium.id} className={styles.content}>
        <OccurrencesContent />
      </div>
    </OperationsLayout>
  )
}

function OccurrencesContent() {
  const { client } = useAuth()
  const api = useMemo(() => createAdminOccurrencesClient(client.http), [client])
  const [draft, setDraft] = useState<OccurrenceFilters>(DEFAULT_FILTERS)
  const [applied, setApplied] = useState<OccurrenceFilters>(DEFAULT_FILTERS)
  const [filterError, setFilterError] = useState('')
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const list = useRefreshableQuery(
    useCallback(
      (signal: AbortSignal) => {
        const query = buildOccurrenceParams(applied, page)
        // Os filtros aplicados já passaram pela validação; aqui é só defesa.
        if (!query.ok) return Promise.reject(new Error(query.message))
        return api.occurrences(query.params, signal)
      },
      [api, applied, page],
    ),
  )
  const people = useRefreshableQuery(
    useCallback((signal: AbortSignal) => api.activeResponsibles(signal), [api]),
  )
  const data = list.result?.data
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const responsibles: Responsibles = {
    list: people.result?.data,
    error: people.result?.error,
    reload: people.reload,
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const query = buildOccurrenceParams(draft)
    if (!query.ok) {
      setFilterError(query.message)
      return
    }
    setFilterError('')
    setApplied(draft)
    setPage(1)
  }

  function clearFilters() {
    setDraft(DEFAULT_FILTERS)
    setApplied(DEFAULT_FILTERS)
    setFilterError('')
    setPage(1)
  }

  return (
    <>
      <div>
        <Badge variant="primary">Administração</Badge>
        <Heading level={1}>Ocorrências</Heading>
        <Text tone="secondary">
          Acompanhe as ocorrências abertas pelos moradores, responda e registre a resolução. As
          marcadas com &quot;Aguardando administração&quot; têm a última mensagem de um morador.
        </Text>
      </div>
      <Card>
        <form className={styles.filters} onSubmit={applyFilters} aria-label="Filtrar ocorrências">
          <Select
            label="Situação"
            value={draft.status || ALL}
            options={statusOptions}
            onChange={(event) => {
              const value = event.target.value
              setDraft({ ...draft, status: value === ALL ? '' : (value as OccurrenceStatus) })
            }}
          />
          <Input
            label="Abertas de"
            type="date"
            value={draft.de}
            max={draft.ate || undefined}
            onChange={(event) => setDraft({ ...draft, de: event.target.value })}
          />
          <Input
            label="Até"
            type="date"
            value={draft.ate}
            min={draft.de || undefined}
            onChange={(event) => setDraft({ ...draft, ate: event.target.value })}
          />
          <Button type="submit" variant="secondary">
            Filtrar
          </Button>
          <Button variant="secondary" onClick={clearFilters}>
            Limpar
          </Button>
        </form>
        {filterError && (
          <Notice tone="alert" role="alert">
            {filterError}
          </Notice>
        )}
        {list.result?.error ? (
          <Notice tone="alert" role="alert">
            {list.result.error}
            <div className={styles.actions}>
              <Button size="sm" onClick={list.reload}>
                Tentar novamente
              </Button>
            </div>
          </Notice>
        ) : !data ? (
          <Text role="status">Carregando ocorrências…</Text>
        ) : (
          <>
            <Table
              className={styles.table}
              caption="Ocorrências do condomínio"
              headers={['Título', 'Unidade', 'Situação', 'Aberta em', 'Ação']}
              emptyMessage="Nenhuma ocorrência encontrada com esses filtros."
              rows={data.items.map((item) => [
                item.titulo,
                item.unidade.identificacao,
                <div className={styles.badges}>
                  <StatusBadge status={item.status} />
                  {item.aguardando_administracao && (
                    <Badge variant="warning" wrap>
                      Aguardando administração
                    </Badge>
                  )}
                </div>,
                formatDateTime(item.criada_em),
                <Button
                  size="sm"
                  variant={selectedId === item.id ? 'primary' : 'secondary'}
                  aria-pressed={selectedId === item.id}
                  aria-label={`Ver detalhes de ${item.titulo}, unidade ${item.unidade.identificacao}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  Ver detalhes
                </Button>,
              ])}
            />
            {data.total > 0 && (
              <div className={styles.pagination}>
                <Text size="sm">
                  Página {data.page} de {pages} · {data.total}{' '}
                  {data.total === 1 ? 'ocorrência' : 'ocorrências'}
                </Text>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  Anterior
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={page >= pages}
                  onClick={() => setPage(page + 1)}
                >
                  Próxima
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
      {selectedId && (
        <Card>
          <OccurrenceDetail
            key={selectedId}
            id={selectedId}
            api={api}
            responsibles={responsibles}
            onChanged={list.reload}
            onClose={() => setSelectedId(null)}
          />
        </Card>
      )}
    </>
  )
}

function StatusBadge({ status }: { status: OccurrenceStatus }) {
  return (
    <Badge variant={status === 'resolvida' ? 'success' : 'alert'}>
      {status === 'resolvida' ? 'Resolvida' : 'Em aberto'}
    </Badge>
  )
}

function OccurrenceDetail({
  id,
  api,
  responsibles,
  onChanged,
  onClose,
}: {
  id: string
  api: AdminOccurrencesClient
  responsibles: Responsibles
  onChanged: () => void
  onClose: () => void
}) {
  const replyId = useId()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [reply, setReply] = useState('')
  const [responsibleId, setResponsibleId] = useState('')
  const [errors, setErrors] = useState<InteractionErrors>({})
  const [feedback, setFeedback] = useState<Feedback>()
  const [pending, setPending] = useState(false)
  const [resolving, setResolving] = useState(false)
  const [resolveBusy, setResolveBusy] = useState(false)
  const submitting = useRef(false)
  const { result, reload } = useRefreshableQuery(
    useCallback((signal: AbortSignal) => api.occurrence(id, signal), [api, id]),
  )
  const item = result?.data
  const loadedId = item?.id
  const activeIds = (responsibles.list ?? []).map((person) => person.id)

  // Leva o foco ao detalhe quando ele chega, para quem usa teclado ou leitor de tela.
  useEffect(() => {
    if (loadedId) headingRef.current?.focus()
  }, [loadedId])

  function refresh() {
    reload()
    onChanged()
  }

  // 404 ao agir é, na prática, responsável desativado: limpa a escolha e recarrega a lista.
  function responsibleGone() {
    setResponsibleId('')
    responsibles.reload()
  }

  async function sendReply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    const validation = validateReply({ texto: reply, responsavelId: responsibleId }, activeIds)
    setFeedback(undefined)
    if (!validation.ok) {
      setErrors(validation.errors)
      return
    }
    setErrors({})
    submitting.current = true
    setPending(true)
    try {
      await api.reply(id, validation.payload)
      setReply('')
      setFeedback({ message: 'Resposta enviada ao morador.', tone: 'success' })
      refresh()
    } catch (failure) {
      if (errorStatus(failure) === 404) responsibleGone()
      setFeedback({ message: occurrenceErrorMessage(failure, 'resposta'), tone: 'alert' })
    } finally {
      submitting.current = false
      setPending(false)
    }
  }

  if (result?.error)
    return (
      <Notice tone="alert" role="alert">
        {result.error}
        <div className={styles.actions}>
          <Button size="sm" onClick={reload}>
            Tentar novamente
          </Button>
          <Button size="sm" variant="secondary" onClick={onClose}>
            Fechar detalhe
          </Button>
        </div>
      </Notice>
    )
  if (!item) return <Text role="status">Carregando ocorrência…</Text>

  const counterId = `${replyId}-counter`
  return (
    <div className={styles.detail}>
      <div className={styles.header}>
        <Heading level={2} size="md" ref={headingRef} tabIndex={-1} className={styles.heading}>
          {item.titulo}
        </Heading>
        <Button size="sm" variant="secondary" onClick={onClose}>
          Fechar detalhe
        </Button>
      </div>
      <dl className={styles.facts}>
        <div>
          <dt>Situação</dt>
          <dd>
            <StatusBadge status={item.status} />
          </dd>
        </div>
        <div>
          <dt>Unidade</dt>
          <dd>{item.unidade.identificacao}</dd>
        </div>
        <div>
          <dt>Aberta por</dt>
          <dd>
            {item.aberta_por.nome}, em {formatDateTime(item.criada_em)}
          </dd>
        </div>
        {item.resolvida_em && (
          <div>
            <dt>Resolvida em</dt>
            <dd>{formatDateTime(item.resolvida_em)}</dd>
          </div>
        )}
      </dl>
      <Heading level={3} size="sm">
        Descrição
      </Heading>
      <Text className={styles.preserveLines}>{item.detalhe}</Text>
      <AttachmentList files={openingAttachments(item.anexos)} api={api} />

      <Heading level={3} size="sm">
        Histórico
      </Heading>
      {item.interacoes.length === 0 ? (
        <Text tone="secondary">Ainda não há interações nesta ocorrência.</Text>
      ) : (
        <ol className={styles.timeline}>
          {item.interacoes.map((interaction) => (
            <li
              key={interaction.id}
              className={`${styles.timelineItem} ${
                interaction.autor.tipo === 'administracao' ? styles.fromAdministration : ''
              }`}
            >
              <Text size="sm">
                <strong>{interactionLabels[interaction.tipo]}</strong> · {interaction.autor.nome} (
                {interaction.autor.tipo === 'administracao' ? 'Administração' : 'Morador'}) ·{' '}
                <time dateTime={interaction.em}>{formatDateTime(interaction.em)}</time>
              </Text>
              {interaction.texto && (
                <Text className={styles.preserveLines}>{interaction.texto}</Text>
              )}
              <AttachmentList files={interaction.anexos} api={api} />
            </li>
          ))}
        </ol>
      )}

      {feedback && (
        <Notice tone={feedback.tone} role={feedback.tone === 'alert' ? 'alert' : 'status'}>
          {feedback.message}
        </Notice>
      )}

      <form className={styles.form} noValidate onSubmit={(event) => void sendReply(event)}>
        <Heading level={3} size="sm">
          Responder ao morador
        </Heading>
        <FormField
          id={replyId}
          label="Resposta"
          required
          error={errors.texto}
          errorId={`${replyId}-error`}
        >
          <textarea
            id={replyId}
            className={fieldStyles.control}
            rows={4}
            required
            maxLength={TEXT_MAX}
            value={reply}
            disabled={pending}
            aria-invalid={errors.texto ? true : undefined}
            aria-describedby={[counterId, errors.texto && `${replyId}-error`]
              .filter(Boolean)
              .join(' ')}
            onChange={(event) => setReply(event.target.value)}
          />
        </FormField>
        <Text id={counterId} size="sm" tone="secondary" className={styles.counter}>
          {reply.length}/{TEXT_MAX} caracteres
        </Text>
        <ResponsibleSelect
          label="Responsável pela resposta"
          responsibles={responsibles}
          value={responsibleId}
          error={errors.responsavel}
          disabled={pending}
          onChange={setResponsibleId}
        />
        <div className={styles.actions}>
          <Button type="submit" loading={pending} disabled={!responsibles.list?.length}>
            Enviar resposta
          </Button>
          {item.status === 'em_aberto' && (
            <Button
              variant="success"
              disabled={pending}
              onClick={() => {
                setFeedback(undefined)
                setResolving(true)
              }}
            >
              Resolver
            </Button>
          )}
        </div>
      </form>

      <Modal
        isOpen={resolving}
        title="Resolver ocorrência"
        onClose={() => {
          if (!resolveBusy) setResolving(false)
        }}
      >
        {resolving && (
          <ResolveForm
            api={api}
            occurrenceId={item.id}
            title={item.titulo}
            responsibles={responsibles}
            activeIds={activeIds}
            responsibleId={responsibleId}
            onResponsibleChange={setResponsibleId}
            onBusy={setResolveBusy}
            onCancel={() => setResolving(false)}
            onResolved={() => {
              setResolving(false)
              setFeedback({ message: 'Ocorrência resolvida.', tone: 'success' })
              refresh()
            }}
            onAlreadyResolved={() => {
              // Outra pessoa resolveu antes: fecha, avisa e mostra a situação atual.
              setResolving(false)
              setFeedback({ message: ALREADY_RESOLVED, tone: 'alert' })
              refresh()
            }}
            onResponsibleGone={responsibleGone}
          />
        )}
      </Modal>
    </div>
  )
}

function ResponsibleSelect({
  label,
  responsibles,
  value,
  error,
  disabled,
  onChange,
}: {
  label: string
  responsibles: Responsibles
  value: string
  error?: string
  disabled?: boolean
  onChange: (value: string) => void
}) {
  return (
    <>
      <Select
        label={label}
        required
        value={value}
        options={(responsibles.list ?? []).map((person) => ({
          value: person.id,
          label: person.nome,
        }))}
        error={error}
        disabled={disabled || !responsibles.list}
        onChange={(event) => onChange(event.target.value)}
      />
      {responsibles.error ? (
        <Notice tone="alert" role="alert">
          Não foi possível carregar os responsáveis. {responsibles.error}
          <div className={styles.actions}>
            <Button size="sm" onClick={responsibles.reload}>
              Tentar novamente
            </Button>
          </div>
        </Notice>
      ) : !responsibles.list ? (
        <Text size="sm" tone="secondary" role="status">
          Carregando responsáveis…
        </Text>
      ) : (
        !responsibles.list.length && (
          <Notice tone="warning">
            Nenhum responsável ativo. Cadastre um em{' '}
            <Link to="/app/administracao/funcionarios">Funcionários</Link> para responder e resolver
            ocorrências.
          </Notice>
        )
      )}
    </>
  )
}

function ResolveForm({
  api,
  occurrenceId,
  title,
  responsibles,
  activeIds,
  responsibleId,
  onResponsibleChange,
  onBusy,
  onCancel,
  onResolved,
  onAlreadyResolved,
  onResponsibleGone,
}: {
  api: AdminOccurrencesClient
  occurrenceId: string
  title: string
  responsibles: Responsibles
  activeIds: string[]
  responsibleId: string
  onResponsibleChange: (value: string) => void
  onBusy: (busy: boolean) => void
  onCancel: () => void
  onResolved: () => void
  onAlreadyResolved: () => void
  onResponsibleGone: () => void
}) {
  const textId = useId()
  const [text, setText] = useState('')
  const [errors, setErrors] = useState<InteractionErrors>({})
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    const validation = validateResolution({ texto: text, responsavelId: responsibleId }, activeIds)
    if (!validation.ok) {
      setErrors(validation.errors)
      return
    }
    setErrors({})
    setError('')
    submitting.current = true
    setPending(true)
    onBusy(true)
    let closing = false
    try {
      await api.resolve(occurrenceId, validation.payload)
      closing = true
      onResolved()
    } catch (failure) {
      if (isAlreadyResolved(failure)) {
        closing = true
        onAlreadyResolved()
      } else {
        // Fica no modal com o texto preservado; o 404 recarrega os responsáveis.
        if (errorStatus(failure) === 404) onResponsibleGone()
        setError(occurrenceErrorMessage(failure, 'resolucao'))
      }
    } finally {
      submitting.current = false
      onBusy(false)
      if (!closing) setPending(false)
    }
  }

  const counterId = `${textId}-counter`
  return (
    <form className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
      <Text>
        Marcar <strong>{title}</strong> como resolvida? O morador verá a resolução no histórico e
        ainda poderá reabrir a ocorrência.
      </Text>
      <FormField
        id={textId}
        label="Texto da resolução (opcional)"
        error={errors.texto}
        errorId={`${textId}-error`}
      >
        <textarea
          id={textId}
          className={fieldStyles.control}
          rows={3}
          maxLength={TEXT_MAX}
          value={text}
          disabled={pending}
          aria-invalid={errors.texto ? true : undefined}
          aria-describedby={[counterId, errors.texto && `${textId}-error`]
            .filter(Boolean)
            .join(' ')}
          onChange={(event) => setText(event.target.value)}
        />
      </FormField>
      <Text id={counterId} size="sm" tone="secondary" className={styles.counter}>
        {text.length}/{TEXT_MAX} caracteres
      </Text>
      <ResponsibleSelect
        label="Responsável pela resolução"
        responsibles={responsibles}
        value={responsibleId}
        error={errors.responsavel}
        disabled={pending}
        onChange={onResponsibleChange}
      />
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button
          type="submit"
          variant="success"
          loading={pending}
          disabled={!responsibles.list?.length}
        >
          Confirmar resolução
        </Button>
        <Button variant="secondary" disabled={pending} onClick={onCancel}>
          Voltar
        </Button>
      </div>
    </form>
  )
}

function AttachmentList({ files, api }: { files: Attachment[]; api: AdminOccurrencesClient }) {
  if (!files.length) return null
  return (
    <div className={styles.actions}>
      {files.map(({ arquivo_id }, index) => (
        <AttachmentButton
          key={arquivo_id}
          id={arquivo_id}
          label={`Abrir anexo ${index + 1}`}
          api={api}
        />
      ))}
    </div>
  )
}

function AttachmentButton({
  id,
  label,
  api,
}: {
  id: string
  label: string
  api: AdminOccurrencesClient
}) {
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle')
  async function open() {
    setState('loading')
    try {
      // A URL é assinada e curta: pede na hora do clique, nunca guarda.
      const url = new URL(await api.attachmentUrl(id))
      if (url.protocol !== 'https:' && url.protocol !== 'http:') throw new Error('URL inválida')
      const link = document.createElement('a')
      link.href = url.href
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      link.click()
      setState('idle')
    } catch {
      setState('error')
    }
  }
  return (
    <span className={styles.actions}>
      <Button
        size="sm"
        variant="secondary"
        loading={state === 'loading'}
        onClick={() => void open()}
      >
        {label}
      </Button>
      {state === 'error' && (
        <Text size="sm" role="alert">
          Não foi possível abrir o anexo.
        </Text>
      )}
    </span>
  )
}
