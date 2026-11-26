import { useCallback, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Badge, Button, Heading, Input, Modal, Notice, Text } from '../../components'
import { FormField } from '../../components/FormField'
import fieldStyles from '../../components/FormField.module.css'
import { CommunityLoadError, CommunityPageControls } from '../resident/ResidentCommunity'
import styles from '../resident/ResidentWorkspace.module.css'
import { supportError } from './suporte-api.ts'
import type { SupportClient } from './suporte-api.ts'
import { dateTime, useSupportQuery } from './support-state.ts'

/** Comunicados recebidos pela Administração (US-804, leitura). */
export function ReceivedAnnouncements({ api }: { api: SupportClient }) {
  const [page, setPage] = useState(1)
  const { result, reload } = useSupportQuery(
    useCallback((signal) => api.receivedAnnouncements(page, signal), [api, page]),
  )
  const list = result?.data
  return (
    <>
      {!result && <Text role="status">Carregando comunicados…</Text>}
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {list && !list.items.length && <Text>Nenhum comunicado da plataforma até agora.</Text>}
      {list?.items.map((item) => (
        <article className={styles.listItem} key={item.id}>
          <Heading level={3}>{item.titulo}</Heading>
          <Text size="sm" tone="secondary">
            Enviado em {dateTime.format(new Date(item.criado_em))}
          </Text>
          <Text className={styles.preserveLines}>{item.texto}</Text>
        </article>
      ))}
      {list && (
        <CommunityPageControls
          page={page}
          pages={Math.ceil(list.total / list.page_size)}
          onChange={setPage}
        />
      )}
    </>
  )
}

/** Envio e histórico de comunicados do ADM (US-804). */
export function SentAnnouncements({ api }: { api: SupportClient }) {
  const [page, setPage] = useState(1)
  const [dialog, setDialog] = useState<{ kind: 'create' } | { kind: 'detail'; id: string }>()
  const [success, setSuccess] = useState('')
  const busy = useRef(false)
  const { result, reload } = useSupportQuery(
    useCallback((signal) => api.platformAnnouncements(page, signal), [api, page]),
  )
  const list = result?.data
  const close = () => {
    if (!busy.current) setDialog(undefined)
  }

  return (
    <>
      <div className={styles.actions}>
        <Button
          onClick={() => {
            setSuccess('')
            setDialog({ kind: 'create' })
          }}
        >
          Novo comunicado
        </Button>
      </div>
      {success && (
        <Notice tone="success" role="status">
          {success}
        </Notice>
      )}
      {!result && <Text role="status">Carregando comunicados…</Text>}
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {list && !list.items.length && <Text>Nenhum comunicado enviado ainda.</Text>}
      {list?.items.map((item) => (
        <article className={styles.listItem} key={item.id}>
          <Heading level={3}>{item.titulo}</Heading>
          <Text size="sm" tone="secondary">
            Enviado por {item.enviado_por.nome} em {dateTime.format(new Date(item.criado_em))}
          </Text>
          <div className={styles.actions}>
            <Badge variant="primary">
              {item.total_destinatarios}{' '}
              {item.total_destinatarios === 1 ? 'condomínio' : 'condomínios'}
            </Badge>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setDialog({ kind: 'detail', id: item.id })}
            >
              Ver detalhes
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
        title={dialog?.kind === 'create' ? 'Novo comunicado' : 'Comunicado enviado'}
        onClose={close}
      >
        {dialog?.kind === 'create' && (
          <AnnouncementForm
            api={api}
            busyRef={busy}
            onClose={close}
            onSent={(total) => {
              setDialog(undefined)
              setSuccess(
                `Comunicado enviado a ${total} ${total === 1 ? 'condomínio' : 'condomínios'}.`,
              )
              setPage(1)
              reload()
            }}
          />
        )}
        {dialog?.kind === 'detail' && (
          <AnnouncementDetails key={dialog.id} id={dialog.id} api={api} />
        )}
      </Modal>
    </>
  )
}

function AnnouncementForm({
  api,
  busyRef,
  onClose,
  onSent,
}: {
  api: SupportClient
  busyRef: { current: boolean }
  onClose: () => void
  onSent: (total: number) => void
}) {
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const textId = useId()

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const title = String(form.get('titulo') ?? '').trim()
    const text = String(form.get('texto') ?? '').trim()
    if (!title || !text) {
      setError('Preencha o título e o texto do comunicado.')
      return
    }
    if (busyRef.current) return
    busyRef.current = true
    setError('')
    setPending(true)
    try {
      onSent((await api.sendAnnouncement(title, text)).total_destinatarios)
    } catch (failure) {
      setError(supportError(failure))
    } finally {
      setPending(false)
      busyRef.current = false
    }
  }

  return (
    <form className={styles.form} onSubmit={(event) => void submit(event)}>
      <Notice tone="warning">
        O comunicado vai para todos os condomínios ativos agora e não pode ser editado depois.
      </Notice>
      <Input label="Título" name="titulo" required maxLength={120} disabled={pending} />
      <FormField id={textId} label="Texto" required>
        <textarea
          id={textId}
          className={fieldStyles.control}
          name="texto"
          required
          maxLength={4000}
          rows={6}
          disabled={pending}
        />
      </FormField>
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button variant="secondary" disabled={pending} onClick={onClose}>
          Voltar
        </Button>
        <Button type="submit" loading={pending}>
          Enviar a todos os condomínios
        </Button>
      </div>
    </form>
  )
}

function AnnouncementDetails({ id, api }: { id: string; api: SupportClient }) {
  const { result, reload } = useSupportQuery(
    useCallback((signal) => api.platformAnnouncement(id, signal), [api, id]),
  )
  const item = result?.data
  return (
    <div className={styles.content}>
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {!result && <Text role="status">Carregando comunicado…</Text>}
      {item && (
        <>
          <Heading level={2}>{item.titulo}</Heading>
          <Text size="sm" tone="secondary">
            Enviado por {item.enviado_por.nome} em {dateTime.format(new Date(item.criado_em))}
          </Text>
          <Text className={styles.preserveLines}>{item.texto}</Text>
          <Heading level={3}>Condomínios destinatários ({item.destinatarios.length})</Heading>
          {!item.destinatarios.length && (
            <Text tone="secondary">Nenhum condomínio ativo na data do envio.</Text>
          )}
          <ul>
            {item.destinatarios.map((condominium) => (
              <li key={condominium.id}>{condominium.nome}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
