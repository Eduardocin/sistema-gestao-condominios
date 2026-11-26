import { useCallback, useId, useMemo, useRef, useState } from 'react'
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
  Table,
  Text,
  Toast,
  Upload,
} from '../../components'
import { FormField } from '../../components/FormField'
import fieldStyles from '../../components/FormField.module.css'
import { useAuth } from '../auth/context'
import { createAdminAreasClient } from './admin-areas-api'
import type { AdminArea, AdminAreasClient, AreaStatusFilter } from './admin-areas-api'
import { adminErrorMessage, isConflict } from './admin-errors'
import { AdminAreasShell } from './AdminAreasShell'
import {
  CAPACITY_MAX,
  FULL_HOURS,
  NAME_MAX,
  PHOTO_TYPES,
  RULES_MAX,
  buildAreaPayload,
  validateAreaForm,
} from './area-form'
import type { AreaFormErrors } from './area-form'
import { useAdminQuery } from './use-admin-query'
import styles from './AdminAreas.module.css'

type Editor = { mode: 'create' } | { mode: 'edit'; area: AdminArea }
type Toggle = { area: AdminArea; action: 'desativar' | 'reativar' }

const filterOptions: { value: AreaStatusFilter; label: string }[] = [
  { value: 'ativas', label: 'Ativas' },
  { value: 'desativadas', label: 'Desativadas' },
  { value: 'todas', label: 'Todas' },
]
const emptyMessages: Record<AreaStatusFilter, string> = {
  ativas: 'Nenhuma área ativa. Cadastre a primeira em "Nova área".',
  desativadas: 'Nenhuma área desativada.',
  todas: 'Nenhuma área cadastrada. Cadastre a primeira em "Nova área".',
}
const hourOptions = FULL_HOURS.map((hour) => ({ value: hour, label: hour }))

export function AdminAreasPage() {
  return (
    <AdminAreasShell activeKey="areas">
      <AreasContent />
    </AdminAreasShell>
  )
}

function AreasContent() {
  const { client } = useAuth()
  const api = useMemo(() => createAdminAreasClient(client.http), [client])
  const [filter, setFilter] = useState<AreaStatusFilter>('ativas')
  const [page, setPage] = useState(1)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [toggle, setToggle] = useState<Toggle | null>(null)
  const [toast, setToast] = useState('')
  const [error, setError] = useState('')
  // Enquanto uma ação está em andamento, o modal não fecha (Esc, fundo ou X).
  const [busy, setBusy] = useState(false)
  const { result, reload } = useAdminQuery(
    useCallback((signal) => api.areas(filter, page, signal), [api, filter, page]),
  )
  const list = result?.data
  const pages = list ? Math.max(1, Math.ceil(list.total / list.page_size)) : 1

  function finish(message: string) {
    setToast(message)
    setError('')
    reload()
  }

  return (
    <>
      <div>
        <Badge variant="primary">Administração</Badge>
        <Heading level={1}>Áreas comuns</Heading>
        <Text tone="secondary">
          Cadastre os espaços que os moradores podem reservar, com horário de funcionamento,
          capacidade e foto. Área desativada deixa de aceitar reservas novas.
        </Text>
      </div>
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      <Card>
        <div className={styles.header}>
          <Heading level={2} size="md">
            Áreas cadastradas
          </Heading>
          <Button
            onClick={() => {
              setError('')
              setEditor({ mode: 'create' })
            }}
          >
            Nova área
          </Button>
        </div>
        <div className={styles.filters}>
          <Select
            label="Situação"
            value={filter}
            options={filterOptions}
            onChange={(event) => {
              setFilter(event.target.value as AreaStatusFilter)
              setPage(1)
            }}
          />
        </div>
        {result?.error ? (
          <Notice tone="alert" role="alert">
            {result.error}
            <div className={styles.actions}>
              <Button size="sm" onClick={reload}>
                Tentar novamente
              </Button>
            </div>
          </Notice>
        ) : !list ? (
          <Text role="status">Carregando áreas comuns…</Text>
        ) : (
          <>
            <Table
              className={styles.areasTable}
              caption="Áreas comuns do condomínio"
              headers={['Nome', 'Horário', 'Capacidade', 'Situação', 'Ações']}
              emptyMessage={emptyMessages[filter]}
              rows={list.items.map((area) => [
                area.nome,
                `${area.abre_as} às ${area.fecha_as}`,
                `${area.capacidade} ${area.capacidade === 1 ? 'pessoa' : 'pessoas'}`,
                <Badge variant={area.ativa ? 'success' : 'neutral'}>
                  {area.ativa ? 'Ativa' : 'Desativada'}
                </Badge>,
                <div className={styles.actions}>
                  <Button
                    size="sm"
                    variant="secondary"
                    aria-label={`Editar ${area.nome}`}
                    onClick={() => {
                      setError('')
                      setEditor({ mode: 'edit', area })
                    }}
                  >
                    Editar
                  </Button>
                  <Button
                    size="sm"
                    variant={area.ativa ? 'alert' : 'secondary'}
                    aria-label={`${area.ativa ? 'Desativar' : 'Reativar'} ${area.nome}`}
                    onClick={() => {
                      setError('')
                      setToggle({ area, action: area.ativa ? 'desativar' : 'reativar' })
                    }}
                  >
                    {area.ativa ? 'Desativar' : 'Reativar'}
                  </Button>
                </div>,
              ])}
            />
            {list.total > 0 && (
              <div className={styles.pagination}>
                <Text size="sm">
                  Página {list.page} de {pages} · {list.total} {list.total === 1 ? 'área' : 'áreas'}
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
      <Modal
        isOpen={!!editor}
        title={editor?.mode === 'edit' ? 'Editar área comum' : 'Nova área comum'}
        onClose={() => {
          if (!busy) setEditor(null)
        }}
      >
        {editor && (
          <AreaEditor
            key={editor.mode === 'edit' ? editor.area.id : 'nova'}
            api={api}
            area={editor.mode === 'edit' ? editor.area : null}
            onBusy={setBusy}
            onCancel={() => setEditor(null)}
            onSaved={(message) => {
              setEditor(null)
              finish(message)
            }}
          />
        )}
      </Modal>
      <Modal
        isOpen={!!toggle}
        title={toggle?.action === 'desativar' ? 'Desativar área comum' : 'Reativar área comum'}
        onClose={() => {
          if (!busy) setToggle(null)
        }}
      >
        {toggle && (
          <ToggleConfirmation
            api={api}
            toggle={toggle}
            onBusy={setBusy}
            onCancel={() => setToggle(null)}
            onDone={(message) => {
              setToggle(null)
              finish(message)
            }}
            onStale={(message) => {
              // 409 de transição: a lista estava velha. Fecha e mostra o motivo na página.
              setToggle(null)
              setError(message)
              reload()
            }}
          />
        )}
      </Modal>
      <Toast message={toast} isVisible={!!toast} onClose={() => setToast('')} />
    </>
  )
}

function AreaEditor({
  api,
  area,
  onBusy,
  onCancel,
  onSaved,
}: {
  api: AdminAreasClient
  area: AdminArea | null
  onBusy: (busy: boolean) => void
  onCancel: () => void
  onSaved: (message: string) => void
}) {
  const rulesId = useId()
  const photoId = useId()
  const [photo, setPhoto] = useState<File | null>(null)
  const [errors, setErrors] = useState<AreaFormErrors>({})
  const [apiError, setApiError] = useState('')
  const [pending, setPending] = useState(false)
  // Guarda o upload já feito: se o PUT/POST falhar (ex.: nome duplicado), reenviar o
  // formulário reaproveita o arquivo em vez de subir a mesma foto de novo.
  const uploaded = useRef<{ file: File; id: string } | null>(null)
  const submitting = useRef(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    const data = new FormData(event.currentTarget)
    const result = validateAreaForm({
      nome: String(data.get('nome') ?? ''),
      regras: String(data.get('regras') ?? ''),
      abreAs: String(data.get('abre_as') ?? ''),
      fechaAs: String(data.get('fecha_as') ?? ''),
      capacidade: String(data.get('capacidade') ?? ''),
      foto: photo,
      fotoAtualId: area?.foto_arquivo_id,
    })
    setApiError('')
    if (!result.ok) {
      setErrors(result.errors)
      return
    }
    setErrors({})
    submitting.current = true
    setPending(true)
    onBusy(true)
    try {
      let photoFileId = area?.foto_arquivo_id ?? ''
      if (photo) {
        if (uploaded.current?.file !== photo)
          uploaded.current = { file: photo, id: await api.uploadPhoto(photo) }
        photoFileId = uploaded.current.id
      }
      const payload = buildAreaPayload(result.fields, photoFileId)
      if (area) await api.updateArea(area.id, payload)
      else await api.createArea(payload)
      onSaved(area ? 'Área atualizada.' : 'Área cadastrada.')
    } catch (failure) {
      setApiError(adminErrorMessage(failure, 'area'))
    } finally {
      submitting.current = false
      setPending(false)
      onBusy(false)
    }
  }

  const invalid = Object.keys(errors).length > 0
  return (
    <form className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
      <Input
        label="Nome"
        name="nome"
        required
        maxLength={NAME_MAX}
        defaultValue={area?.nome}
        error={errors.nome}
        disabled={pending}
      />
      <FormField
        id={rulesId}
        label="Regras de uso"
        hint={`Opcional, até ${RULES_MAX} caracteres.`}
        hintId={`${rulesId}-hint`}
        error={errors.regras}
        errorId={`${rulesId}-error`}
      >
        <textarea
          id={rulesId}
          name="regras"
          className={fieldStyles.control}
          rows={4}
          maxLength={RULES_MAX}
          defaultValue={area?.regras ?? ''}
          aria-invalid={errors.regras ? true : undefined}
          aria-describedby={[`${rulesId}-hint`, errors.regras && `${rulesId}-error`]
            .filter(Boolean)
            .join(' ')}
          disabled={pending}
        />
      </FormField>
      <div className={styles.hours}>
        <Select
          label="Abre às"
          name="abre_as"
          required
          options={hourOptions}
          defaultValue={area?.abre_as ?? '08:00'}
          error={errors.abre_as}
          disabled={pending}
        />
        <Select
          label="Fecha às"
          name="fecha_as"
          required
          options={hourOptions}
          defaultValue={area?.fecha_as ?? '22:00'}
          error={errors.fecha_as}
          hint="Reservas em blocos de 1 hora."
          disabled={pending}
        />
      </div>
      <Input
        label="Capacidade (pessoas)"
        name="capacidade"
        type="number"
        inputMode="numeric"
        required
        min={1}
        max={CAPACITY_MAX}
        step={1}
        defaultValue={area?.capacidade}
        error={errors.capacidade}
        disabled={pending}
      />
      <div className={styles.photoField}>
        <Text as="span" size="sm">
          <strong>Foto da área</strong>
          {area ? ' (opcional: sem nova foto, a atual é mantida)' : ' (obrigatória)'}
        </Text>
        {area && <CurrentPhoto api={api} area={area} />}
        <Upload
          label={area ? 'Trocar foto da área' : 'Escolher foto da área'}
          accept={PHOTO_TYPES.join(',')}
          disabled={pending}
          aria-invalid={errors.foto ? true : undefined}
          aria-describedby={`${photoId}-hint${errors.foto ? ` ${photoId}-error` : ''}`}
          onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
        />
        <Text id={`${photoId}-hint`} size="sm" tone="secondary">
          JPG, PNG ou WebP, até 5 MB.
        </Text>
        {errors.foto && (
          <Text id={`${photoId}-error`} size="sm" className={styles.fieldError}>
            {errors.foto}
          </Text>
        )}
      </div>
      {invalid && (
        <Notice tone="alert" role="alert">
          Revise os campos destacados.
        </Notice>
      )}
      {apiError && (
        <Notice tone="alert" role="alert">
          {apiError}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button type="submit" loading={pending}>
          {area ? 'Salvar alterações' : 'Cadastrar área'}
        </Button>
        <Button variant="secondary" disabled={pending} onClick={onCancel}>
          Cancelar
        </Button>
      </div>
    </form>
  )
}

function CurrentPhoto({ api, area }: { api: AdminAreasClient; area: AdminArea }) {
  const { result } = useAdminQuery(
    useCallback(
      (signal) => api.photoUrl(area.foto_arquivo_id, signal),
      [api, area.foto_arquivo_id],
    ),
  )
  if (result?.error)
    return (
      <Text size="sm" tone="secondary">
        Não foi possível exibir a foto atual. Ela continua salva.
      </Text>
    )
  if (!result?.data)
    return (
      <Text size="sm" tone="secondary" role="status">
        Carregando foto atual…
      </Text>
    )
  return <img className={styles.photo} src={result.data} alt={`Foto atual de ${area.nome}`} />
}

function ToggleConfirmation({
  api,
  toggle,
  onBusy,
  onCancel,
  onDone,
  onStale,
}: {
  api: AdminAreasClient
  toggle: Toggle
  onBusy: (busy: boolean) => void
  onCancel: () => void
  onDone: (message: string) => void
  onStale: (message: string) => void
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const deactivate = toggle.action === 'desativar'

  async function confirm() {
    if (submitting.current) return
    submitting.current = true
    setPending(true)
    onBusy(true)
    setError('')
    try {
      if (deactivate) await api.deactivateArea(toggle.area.id)
      else await api.reactivateArea(toggle.area.id)
      onDone(deactivate ? 'Área desativada.' : 'Área reativada.')
    } catch (failure) {
      const message = adminErrorMessage(failure, 'area')
      if (isConflict(failure)) onStale(message)
      else setError(message)
    } finally {
      submitting.current = false
      setPending(false)
      onBusy(false)
    }
  }

  return (
    <div className={styles.form}>
      <Text>
        {deactivate ? 'Desativar' : 'Reativar'} <strong>{toggle.area.nome}</strong>?
      </Text>
      <Text size="sm" tone="secondary">
        {deactivate
          ? 'A área deixa de aceitar reservas novas e some para os moradores. As reservas já feitas continuam ativas; cancele-as em Reservas, se precisar.'
          : 'A área volta a aparecer para os moradores e a aceitar reservas.'}
      </Text>
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      <div className={styles.actions}>
        <Button
          variant={deactivate ? 'alert' : 'primary'}
          loading={pending}
          onClick={() => void confirm()}
        >
          {deactivate ? 'Confirmar desativação' : 'Confirmar reativação'}
        </Button>
        <Button variant="secondary" disabled={pending} onClick={onCancel}>
          Voltar
        </Button>
      </div>
    </div>
  )
}
