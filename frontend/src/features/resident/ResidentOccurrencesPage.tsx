import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Badge, Button, Heading, Input, Modal, Notice, Text, Upload } from '../../components'
import { FormField } from '../../components/FormField'
import fieldStyles from '../../components/FormField.module.css'
import { CommunityLoadError, CommunityPageControls, ResidentCommunity } from './ResidentCommunity'
import type { CommunityUnit } from './ResidentCommunity'
import { useCommunityQuery } from './resident-community-state'
import styles from './ResidentWorkspace.module.css'
import { communityError } from './resident-community-api'
import type { Occurrence, ResidentCommunityClient } from './resident-community-api'

type UnitProps = { unit: CommunityUnit; api: ResidentCommunityClient }
type Dialog = { kind: 'create' } | { kind: 'detail'; id: string }
type Submission = { start: () => boolean; finish: () => void }

const supportedPhotos = ['image/jpeg', 'image/png', 'image/webp']
const maxBytes = 5 * 1024 * 1024
const dateTime = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'America/Sao_Paulo',
})
const interactionLabels: Record<Occurrence['interacoes'][number]['tipo'], string> = {
  resposta: 'Resposta',
  comentario: 'Comentário',
  resolucao: 'Resolução',
  reabertura: 'Reabertura',
}

export function ResidentOccurrencesPage() {
  return (
    <ResidentCommunity activeKey="occurrences" title="Minhas ocorrências">
      {(unit, api) => <UnitOccurrences unit={unit} api={api} />}
    </ResidentCommunity>
  )
}

function UnitOccurrences({ unit, api }: UnitProps) {
  const [page, setPage] = useState(1)
  const [dialog, setDialog] = useState<Dialog>()
  const [success, setSuccess] = useState('')
  const modalBusy = useRef(false)
  const { result, reload } = useCommunityQuery(
    useCallback((signal) => api.occurrences(unit.id, page, signal), [api, unit.id, page]),
  )
  const list = result?.data
  const close = () => {
    if (!modalBusy.current) setDialog(undefined)
  }
  const submission = {
    start() {
      if (modalBusy.current) return false
      modalBusy.current = true
      return true
    },
    finish() {
      modalBusy.current = false
    },
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
          Abrir ocorrência
        </Button>
      </div>
      {success && (
        <Notice tone="success" role="status">
          {success}
        </Notice>
      )}
      {!result && <Text role="status">Carregando ocorrências…</Text>}
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {list && !list.items.length && <Text>Nenhuma ocorrência encontrada para esta unidade.</Text>}
      {list?.items.map((item) => (
        <article className={styles.listItem} key={item.id}>
          <Heading level={3}>{item.titulo}</Heading>
          <Text size="sm" tone="secondary">
            Aberta em {dateTime.format(new Date(item.criada_em))}
          </Text>
          <div className={styles.actions}>
            <OccurrenceStatus status={item.status} />
            {item.aguardando_administracao && item.status === 'em_aberto' && (
              <Badge>Aguardando administração</Badge>
            )}
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
        title={dialog?.kind === 'create' ? 'Abrir ocorrência' : 'Detalhes da ocorrência'}
        onClose={close}
      >
        {dialog?.kind === 'create' && (
          <OccurrenceForm
            unit={unit}
            api={api}
            submission={submission}
            onClose={close}
            onCreated={() => {
              setDialog(undefined)
              setSuccess('Ocorrência registrada.')
              setPage(1)
              reload()
            }}
          />
        )}
        {dialog?.kind === 'detail' && (
          <OccurrenceDetails
            key={dialog.id}
            id={dialog.id}
            api={api}
            submission={submission}
            onUpdate={reload}
          />
        )}
      </Modal>
    </>
  )
}

function OccurrenceStatus({ status }: { status: Occurrence['status'] }) {
  return (
    <Badge variant={status === 'resolvida' ? 'success' : 'warning'}>
      {status === 'resolvida' ? 'Resolvida' : 'Em aberto'}
    </Badge>
  )
}

function OccurrenceForm({
  unit,
  api,
  submission,
  onClose,
  onCreated,
}: UnitProps & {
  submission: Submission
  onClose: () => void
  onCreated: () => void
}) {
  const [photos, setPhotos] = useState<File[]>([])
  const [uploadKey, setUploadKey] = useState(0)
  const [photoError, setPhotoError] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const uploaded = useRef(new Map<File, string>())
  const descriptionId = useId()

  function choose(files: File[]) {
    setPhotos(files)
    uploaded.current.clear()
    setPhotoError(
      files.length > 5
        ? 'Selecione até cinco fotos.'
        : files.some((photo) => !supportedPhotos.includes(photo.type) || photo.size > maxBytes)
          ? 'Use fotos JPG, PNG ou WebP de até 5 MB cada.'
          : '',
    )
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (photoError) return
    const form = new FormData(event.currentTarget)
    const title = String(form.get('titulo') ?? '').trim()
    const description = String(form.get('detalhe') ?? '').trim()
    if (!title || !description) {
      setError('Preencha o título e a descrição da ocorrência.')
      return
    }
    if (!submission.start()) return
    setError('')
    setPending(true)
    try {
      const ids: string[] = []
      for (const photo of photos) {
        const id = uploaded.current.get(photo) ?? (await api.uploadOccurrencePhoto(unit.id, photo))
        uploaded.current.set(photo, id)
        ids.push(id)
      }
      await api.openOccurrence(unit.id, title, description, ids)
      onCreated()
    } catch (failure) {
      setError(communityError(failure))
    } finally {
      setPending(false)
      submission.finish()
    }
  }

  return (
    <form className={styles.form} onSubmit={(event) => void submit(event)}>
      <Input label="Título" name="titulo" required maxLength={120} disabled={pending} />
      <FormField id={descriptionId} label="Descrição" required>
        <textarea
          id={descriptionId}
          className={fieldStyles.control}
          name="detalhe"
          required
          maxLength={4000}
          rows={4}
          disabled={pending}
        />
      </FormField>
      <Upload
        key={uploadKey}
        label="Anexar fotos"
        multiple
        accept={supportedPhotos.join(',')}
        disabled={pending}
        onChange={(event) => choose(Array.from(event.target.files ?? []))}
      />
      {photoError && (
        <Notice tone="alert" role="alert">
          {photoError}
        </Notice>
      )}
      {!photoError && photos.length > 0 && (
        <div className={styles.photoList}>
          {photos.map((photo, index) => (
            <PhotoPreview photo={photo} key={index} />
          ))}
        </div>
      )}
      {photos.length > 0 && (
        <div>
          <Button
            variant="secondary"
            size="sm"
            disabled={pending}
            onClick={() => {
              choose([])
              setUploadKey((value) => value + 1)
            }}
          >
            Retirar fotos
          </Button>
        </div>
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
        <Button type="submit" loading={pending} disabled={Boolean(photoError)}>
          Enviar ocorrência
        </Button>
      </div>
    </form>
  )
}

function PhotoPreview({ photo }: { photo: File }) {
  const [preview, setPreview] = useState<{ photo: File; url: string }>()
  useEffect(() => {
    const url = URL.createObjectURL(photo)
    const task = window.requestAnimationFrame(() => setPreview({ photo, url }))
    return () => {
      window.cancelAnimationFrame(task)
      URL.revokeObjectURL(url)
    }
  }, [photo])
  return (
    preview?.photo === photo && (
      <img className={styles.photoPreview} src={preview.url} alt={`Prévia de ${photo.name}`} />
    )
  )
}

function OccurrenceDetails({
  id,
  api,
  submission,
  onUpdate,
}: {
  id: string
  api: ResidentCommunityClient
  submission: Submission
  onUpdate: () => void
}) {
  const [text, setText] = useState('')
  const [pending, setPending] = useState(false)
  const [feedback, setFeedback] = useState<{ message: string; error?: boolean }>()
  const textId = useId()
  const { result, reload } = useCommunityQuery(
    useCallback((signal) => api.occurrence(id, signal), [api, id]),
  )
  const item = result?.data

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!item || !text.trim() || !submission.start()) return
    const reopening = item.status === 'resolvida'
    setPending(true)
    setFeedback(undefined)
    try {
      await api.interact(id, reopening ? 'reabertura' : 'comentarios', text.trim())
      setText('')
      setFeedback({ message: reopening ? 'Ocorrência reaberta.' : 'Comentário enviado.' })
      onUpdate()
      reload()
    } catch (failure) {
      setFeedback({ message: communityError(failure), error: true })
    } finally {
      setPending(false)
      submission.finish()
    }
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
      {!result && <Text role="status">Carregando ocorrência…</Text>}
      {item && (
        <>
          <div className={styles.actions}>
            <Heading level={2}>{item.titulo}</Heading>
            <OccurrenceStatus status={item.status} />
          </div>
          <Text className={styles.preserveLines}>{item.detalhe}</Text>
          <AttachmentLinks files={item.anexos} api={api} />
          <Heading level={3}>Histórico</Heading>
          {!item.interacoes.length && (
            <Text tone="secondary">Ainda não há mensagens nesta ocorrência.</Text>
          )}
          {item.interacoes.map((interaction) => (
            <article className={styles.listItem} key={interaction.id}>
              <Text size="sm">
                <strong>
                  {interactionLabels[interaction.tipo]} · {interaction.autor.nome}
                </strong>{' '}
                · {dateTime.format(new Date(interaction.em))}
              </Text>
              {interaction.texto && (
                <Text className={styles.preserveLines}>{interaction.texto}</Text>
              )}
              <AttachmentLinks files={interaction.anexos} api={api} />
            </article>
          ))}
          <form className={styles.form} onSubmit={(event) => void submit(event)}>
            <FormField
              id={textId}
              label={item.status === 'resolvida' ? 'Motivo da reabertura' : 'Comentário'}
              required
            >
              <textarea
                id={textId}
                className={fieldStyles.control}
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={3}
                required
                maxLength={2000}
                disabled={pending}
              />
            </FormField>
            <div>
              <Button type="submit" loading={pending} disabled={!text.trim()}>
                {item.status === 'resolvida' ? 'Reabrir ocorrência' : 'Enviar comentário'}
              </Button>
            </div>
          </form>
        </>
      )}
    </div>
  )
}

function AttachmentLinks({
  files,
  api,
}: {
  files: Occurrence['anexos']
  api: ResidentCommunityClient
}) {
  if (!files.length) return null
  return (
    <div className={styles.actions}>
      {files.map(({ arquivo_id }, index) => (
        <Attachment key={arquivo_id} id={arquivo_id} label={`Baixar anexo ${index + 1}`} api={api} />
      ))}
    </div>
  )
}

function Attachment({
  id,
  label,
  api,
}: {
  id: string
  label: string
  api: ResidentCommunityClient
}) {
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
