import { useCallback, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Badge,
  Button,
  Card,
  Heading,
  Input,
  Modal,
  Notice,
  Select,
  Text,
  Upload,
} from '../../components'
import { FormField } from '../../components/FormField'
import fieldStyles from '../../components/FormField.module.css'
import { CommunityLoadError, CommunityPageControls } from '../resident/ResidentCommunity'
import styles from '../resident/ResidentWorkspace.module.css'
import { supportError, ticketStatusLabels } from './suporte-api.ts'
import type { SupportClient, SupportScope, Ticket, TicketStatus } from './suporte-api.ts'
import { dateTime, useSupportQuery } from './support-state.ts'

const supportedFiles = ['image/jpeg', 'image/png', 'image/webp']
const maxBytes = 5 * 1024 * 1024
const statusOptions = (['aberto', 'em_atendimento', 'encerrado'] as const).map((value) => ({
  value,
  label: ticketStatusLabels[value],
}))
const statusVariant = {
  aberto: 'warning',
  em_atendimento: 'primary',
  encerrado: 'neutral',
} as const

type Filters = { status: '' | TicketStatus; busca: string; de: string; ate: string }
const noFilters: Filters = { status: '', busca: '', de: '', ate: '' }

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return <Badge variant={statusVariant[status]}>{ticketStatusLabels[status]}</Badge>
}

export function TicketsView({ scope, api }: { scope: SupportScope; api: SupportClient }) {
  const platform = scope === 'plataforma'
  const [page, setPage] = useState(1)
  const [draft, setDraft] = useState(noFilters)
  const [filters, setFilters] = useState(noFilters)
  const [dialog, setDialog] = useState<{ kind: 'create' } | { kind: 'detail'; id: string }>()
  const [success, setSuccess] = useState('')
  const busy = useRef(false)
  const { result, reload } = useSupportQuery(
    useCallback(
      (signal) =>
        api.tickets(scope, page, { ...filters, status: filters.status || undefined }, signal),
      [api, scope, page, filters],
    ),
  )
  const list = result?.data
  const close = () => {
    if (!busy.current) setDialog(undefined)
  }
  const lock = {
    start() {
      if (busy.current) return false
      busy.current = true
      return true
    },
    finish() {
      busy.current = false
    },
  }

  function apply(event: FormEvent) {
    event.preventDefault()
    setPage(1)
    setFilters(draft)
  }

  return (
    <>
      <form className={styles.filters} onSubmit={apply} aria-label="Filtros dos chamados">
        <Select
          label="Status"
          placeholder="Todos os status"
          options={statusOptions}
          value={draft.status}
          onChange={(event) =>
            setDraft({ ...draft, status: event.target.value as Filters['status'] })
          }
          hint={
            platform && !draft.status ? 'Sem filtro: só os chamados não encerrados.' : undefined
          }
        />
        {platform && (
          <>
            <Input
              label="Buscar"
              value={draft.busca}
              maxLength={120}
              onChange={(event) => setDraft({ ...draft, busca: event.target.value })}
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
          </>
        )}
        <div className={styles.actions}>
          <Button type="submit">Filtrar</Button>
          <Button
            variant="secondary"
            onClick={() => {
              setDraft(noFilters)
              setFilters(noFilters)
              setPage(1)
            }}
          >
            Limpar
          </Button>
          {!platform && (
            <Button
              onClick={() => {
                setSuccess('')
                setDialog({ kind: 'create' })
              }}
            >
              Abrir chamado
            </Button>
          )}
        </div>
      </form>
      {success && (
        <Notice tone="success" role="status">
          {success}
        </Notice>
      )}
      {!result && <Text role="status">Carregando chamados…</Text>}
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {list && !list.items.length && (
        <Text>
          {platform ? 'Nenhum chamado na fila com esses filtros.' : 'Nenhum chamado encontrado.'}
        </Text>
      )}
      {list?.items.map((item) => (
        <article className={styles.listItem} key={item.id}>
          <Heading level={3}>{item.titulo}</Heading>
          <Text size="sm" tone="secondary">
            {platform && item.condominio ? `${item.condominio.nome} · ` : ''}
            Aberto por {item.aberto_por.nome} em {dateTime.format(new Date(item.criado_em))}
            {item.atendido_por ? ` · Atendido por ${item.atendido_por.nome}` : ''}
          </Text>
          <div className={styles.actions}>
            <TicketStatusBadge status={item.status} />
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setDialog({ kind: 'detail', id: item.id })}
            >
              {platform ? 'Atender' : 'Ver chamado'}
            </Button>
          </div>
        </article>
      ))}
      {list && (
        <CommunityPageControls
          page={page}
          pages={Math.ceil(list.total / list.page_size)}
          onChange={setPage}
        />
      )}
      <Modal
        isOpen={Boolean(dialog)}
        title={dialog?.kind === 'create' ? 'Abrir chamado' : 'Chamado de suporte'}
        onClose={close}
      >
        {dialog?.kind === 'create' && (
          <TicketForm
            api={api}
            lock={lock}
            onClose={close}
            onCreated={(ticket) => {
              setSuccess('Chamado aberto. A equipe da plataforma responderá por aqui.')
              setDialog({ kind: 'detail', id: ticket.id })
              setPage(1)
              reload()
            }}
          />
        )}
        {dialog?.kind === 'detail' && (
          <TicketDetails
            key={dialog.id}
            id={dialog.id}
            scope={scope}
            api={api}
            lock={lock}
            onUpdate={reload}
          />
        )}
      </Modal>
    </>
  )
}

type Lock = { start: () => boolean; finish: () => void }

function TicketForm({
  api,
  lock,
  onClose,
  onCreated,
}: {
  api: SupportClient
  lock: Lock
  onClose: () => void
  onCreated: (ticket: Ticket) => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [fileError, setFileError] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const uploaded = useRef(new Map<File, string>())
  const descriptionId = useId()

  function choose(chosen: File[]) {
    setFiles(chosen)
    uploaded.current.clear()
    setFileError(
      chosen.length > 5
        ? 'Selecione até cinco arquivos.'
        : chosen.some((file) => !supportedFiles.includes(file.type) || file.size > maxBytes)
          ? 'Use imagens JPG, PNG ou WebP de até 5 MB cada.'
          : '',
    )
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (fileError) return
    const form = new FormData(event.currentTarget)
    const title = String(form.get('titulo') ?? '').trim()
    const description = String(form.get('descricao') ?? '').trim()
    if (!title || !description) {
      setError('Preencha o título e a descrição do chamado.')
      return
    }
    if (!lock.start()) return
    setError('')
    setPending(true)
    try {
      const ids: string[] = []
      for (const file of files) {
        const id = uploaded.current.get(file) ?? (await api.uploadAttachment(file))
        uploaded.current.set(file, id)
        ids.push(id)
      }
      onCreated(await api.openTicket(title, description, ids))
    } catch (failure) {
      setError(supportError(failure))
    } finally {
      setPending(false)
      lock.finish()
    }
  }

  return (
    <form className={styles.form} onSubmit={(event) => void submit(event)}>
      <Input label="Título" name="titulo" required maxLength={120} disabled={pending} />
      <FormField id={descriptionId} label="Descrição" required>
        <textarea
          id={descriptionId}
          className={fieldStyles.control}
          name="descricao"
          required
          maxLength={4000}
          rows={5}
          disabled={pending}
        />
      </FormField>
      <Upload
        label="Anexar imagens (opcional)"
        multiple
        accept={supportedFiles.join(',')}
        disabled={pending}
        onChange={(event) => choose(Array.from(event.target.files ?? []))}
      />
      {fileError && (
        <Notice tone="alert" role="alert">
          {fileError}
        </Notice>
      )}
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button variant="secondary" disabled={pending} onClick={onClose}>
          Voltar
        </Button>
        <Button type="submit" loading={pending} disabled={Boolean(fileError)}>
          Enviar chamado
        </Button>
      </div>
    </form>
  )
}

function TicketDetails({
  id,
  scope,
  api,
  lock,
  onUpdate,
}: {
  id: string
  scope: SupportScope
  api: SupportClient
  lock: Lock
  onUpdate: () => void
}) {
  const platform = scope === 'plataforma'
  const [text, setText] = useState('')
  const [pending, setPending] = useState(false)
  const [confirmClose, setConfirmClose] = useState(false)
  const [feedback, setFeedback] = useState<{ message: string; error?: boolean }>()
  const textId = useId()
  const { result, reload } = useSupportQuery(
    useCallback((signal) => api.ticket(scope, id, signal), [api, scope, id]),
  )
  const ticket = result?.data

  async function run(action: () => Promise<unknown>, done: string) {
    if (!lock.start()) return
    setPending(true)
    setFeedback(undefined)
    try {
      await action()
      setFeedback({ message: done })
      onUpdate()
      reload()
      return true
    } catch (failure) {
      setFeedback({ message: supportError(failure), error: true })
    } finally {
      setPending(false)
      lock.finish()
    }
  }

  async function reply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim()) return
    if (await run(() => api.reply(scope, id, text.trim()), 'Mensagem enviada.')) setText('')
  }

  return (
    <div className={styles.content}>
      {feedback && (
        <Notice
          tone={feedback.error ? 'alert' : 'success'}
          role={feedback.error ? 'alert' : 'status'}
        >
          {feedback.message}
        </Notice>
      )}
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {!result && <Text role="status">Carregando chamado…</Text>}
      {ticket && (
        <>
          <div className={styles.actions}>
            <Heading level={2}>{ticket.titulo}</Heading>
            <TicketStatusBadge status={ticket.status} />
          </div>
          <Text size="sm" tone="secondary">
            {platform && ticket.condominio ? `${ticket.condominio.nome} · ` : ''}
            Aberto por {ticket.aberto_por.nome} em {dateTime.format(new Date(ticket.criado_em))}
            {ticket.encerrado_em
              ? ` · Encerrado em ${dateTime.format(new Date(ticket.encerrado_em))}`
              : ''}
          </Text>
          <Text className={styles.preserveLines}>{ticket.descricao}</Text>
          {ticket.anexos.length > 0 && (
            <div className={styles.actions}>
              {ticket.anexos.map((fileId, index) => (
                <AttachmentButton
                  key={fileId}
                  id={fileId}
                  label={`Baixar anexo ${index + 1}`}
                  api={api}
                />
              ))}
            </div>
          )}
          <Heading level={3}>Conversa</Heading>
          {!ticket.mensagens.length && (
            <Text tone="secondary">
              {platform ? 'Ninguém respondeu ainda.' : 'Aguardando a equipe da plataforma.'}
            </Text>
          )}
          {ticket.mensagens.map((message) => (
            <article className={styles.listItem} key={message.id}>
              <Text size="sm">
                <strong>{message.autor.nome}</strong> ·{' '}
                {message.autor.tipo === 'plataforma' ? 'Plataforma' : 'Administração'} ·{' '}
                {dateTime.format(new Date(message.em))}
              </Text>
              <Text className={styles.preserveLines}>{message.texto}</Text>
            </article>
          ))}
          {ticket.status === 'encerrado' ? (
            <Notice tone="primary">
              Este chamado foi encerrado.{' '}
              {!platform && 'Abra um novo chamado se precisar de ajuda.'}
            </Notice>
          ) : (
            <form className={styles.form} onSubmit={(event) => void reply(event)}>
              <FormField id={textId} label={platform ? 'Resposta' : 'Nova mensagem'} required>
                <textarea
                  id={textId}
                  className={fieldStyles.control}
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  rows={3}
                  required
                  maxLength={4000}
                  disabled={pending}
                />
              </FormField>
              <div className={styles.actions}>
                <Button type="submit" loading={pending} disabled={!text.trim()}>
                  Enviar mensagem
                </Button>
                {platform && !confirmClose && (
                  <Button
                    variant="secondary"
                    disabled={pending}
                    onClick={() => setConfirmClose(true)}
                  >
                    Encerrar chamado
                  </Button>
                )}
              </div>
              {platform && confirmClose && (
                <Card className={styles.content}>
                  <Text>Encerrar o chamado impede novas mensagens. Deseja continuar?</Text>
                  <div className={styles.actions}>
                    <Button
                      loading={pending}
                      onClick={() => void run(() => api.closeTicket(id), 'Chamado encerrado.')}
                    >
                      Confirmar encerramento
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={pending}
                      onClick={() => setConfirmClose(false)}
                    >
                      Cancelar
                    </Button>
                  </div>
                </Card>
              )}
            </form>
          )}
        </>
      )}
    </div>
  )
}

function AttachmentButton({ id, label, api }: { id: string; label: string; api: SupportClient }) {
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle')
  async function open() {
    setState('loading')
    try {
      const url = new URL(await api.download(id))
      if (url.protocol !== 'https:' && url.protocol !== 'http:') throw new Error('URL inválida')
      const link = document.createElement('a')
      link.href = url.href
      link.referrerPolicy = 'no-referrer'
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
